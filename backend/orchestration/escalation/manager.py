"""EscalationManager (Fig 6c: evaluate, createCase, routeCase + resolve).

Every escalation and approval goes through this single class, so all agents share one
confidence threshold and one routing rule (spec 6.1, NFR-02, NFR-04, AR13).

Routing rule (spec 5.4, with the agreed deviation A17):
  * learning subjects (assessment, plan, question) -> the student's teacher (active or pending plan);
    a student without a teacher -> the intake teacher (settings.INTAKE_TEACHER_EMAIL); else the Founder
  * business exceptions, proposals, payload["route_to"] == "founder" -> the Founder
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from agents.runtime import AgentResult, AgentStatus
from domain.common import DomainError
from domain.governance import selectors as governance
from domain.governance import services as gov
from domain.governance.models import AgentTask, EscalationCase, UpdateProposal
from domain.learning import selectors as learning

from .notify import notify_assignee

ESCALATION_MANAGER = "escalation_manager"
LEARNING_SUBJECTS = ("assessment", "plan", "question")
DEFAULT_SUBJECT = {
    "assessment": "assessment",
    "planning": "plan",
    "teaching_support": "question",
    "coordinator": "business",
    "tech_operations": "proposal",
}
REVIEW_ACTIONS = {
    "plan": {"approve", "request_changes"},
    "assessment": {"confirm_result", "request_changes"},
    "question": {"answer", "request_changes"},
}
# Founder business-case actions: contract.json values plus the values the frontend buttons send (A12).
CASE_ACTIONS = {
    "widen_match": "widen_match",
    "request_teacher": "request_teacher",
    "resolve": "resolve",
    "request_followup": "request_teacher",
    "approve_resolution": "resolve",
}


class EscalationManager:
    def evaluate(self, result: AgentResult) -> bool:
        """True when the result needs a human: the agent asked for it, or confidence is below the threshold."""
        return result.status in (AgentStatus.NEEDS_ESCALATION, AgentStatus.AWAITING_APPROVAL) or self.is_below_threshold(result.confidence)

    def is_below_threshold(self, confidence: float | None) -> bool:
        return confidence is not None and confidence < settings.AGENT_CONFIDENCE_THRESHOLD

    def create_case(self, task: AgentTask, *, kind: str) -> EscalationCase:
        """Open a case from the control keys of the agent's payload (see docs/shared-conventions.md)."""
        control = task.result or {}  # the AgentResult.payload the agent returned
        subject_type = control.get("subject_type") or DEFAULT_SUBJECT.get(task.target_agent, "business")
        case = gov.create_case(
            ESCALATION_MANAGER,
            task=task,
            kind=kind,
            trigger=str(control.get("trigger") or task.reason or "Escalated by agent"),
            confidence=task.confidence,
            assignee=self.assignee_for(subject_type, task.student, control.get("route_to")),
            resume_task_type=str(control.get("resume") or ""),
            student=task.student,
            subject_type=subject_type,
            subject_id=str(control.get("subject_id") or ""),
            summary=str(control.get("summary") or "")[:200],
            diagnosis=str(control.get("diagnosis") or ""),
            evidence=list(control.get("evidence") or []),
        )
        self.route_case(case)
        return case

    def assignee_for(self, subject_type: str, student: Any, route_to: str | None = None) -> Any:
        if route_to != "founder" and subject_type in LEARNING_SUBJECTS:
            teacher = learning.current_teacher(student) if student is not None else None
            teacher = teacher or governance.teacher_by_email(settings.INTAKE_TEACHER_EMAIL)
            if teacher is not None:
                return teacher
        return governance.first_founder()

    def route_case(self, case: EscalationCase) -> None:
        if case.assignee is not None:
            notify_assignee(case)

    def resolve(self, case: EscalationCase, decision: dict, by: Any):
        """Record the human decision, then continue the paused flow (resume task or close the request)."""
        from orchestration.task_queue import dispatcher

        gov.resolve_case(ESCALATION_MANAGER, case, decision=decision, by=by)
        return dispatcher.resume_after_decision(
            origin=case.task,
            resume_task_type=case.resume_task_type,
            decision=decision,
            by=by,
            student=case.student,
            reference=str(case.pk),
            subject_id=case.subject_id,
        )

    # --- decisions from the API ---------------------------------------------------------------
    def decide_review(self, case: EscalationCase, *, action: str, note: str, by: Any, corrected_level: str | None = None):
        allowed = REVIEW_ACTIONS.get(case.subject_type, set())
        if action not in allowed:
            raise DomainError("invalid_action", f"{action} is not valid for a {case.subject_type} review.", status=400)
        if not note.strip():
            raise DomainError("note_required", "A decision note is required.", status=400)
        decision = {"action": action, "note": note}
        if corrected_level:
            decision["corrected_level"] = corrected_level  # teacher override; the note is the evidence
        return self.resolve(case, decision, by)

    def decide_business_case(self, case: EscalationCase, *, action: str, note: str, by: Any):
        normalised = CASE_ACTIONS.get(action)
        if normalised is None:
            raise DomainError("invalid_action", f"Unknown case action: {action}", status=400)
        if not note.strip():
            raise DomainError("note_required", "A decision note is required.", status=400)
        return self.resolve(case, {"action": normalised, "note": note, "requested_action": action}, by)

    def decide_proposal(self, proposal: UpdateProposal, *, approve: bool, note: str, by: Any, version: int | None = None):
        """Approval is version-bound; execution and verification are separate events done by tech_operations."""
        from orchestration.task_queue import dispatcher

        if version is not None and version != proposal.version:
            raise DomainError("proposal_version_mismatch", "The proposal changed after you reviewed it. Reload and review again.")
        if not approve and not note.strip():
            raise DomainError("note_required", "A reason is required to reject a proposal.", status=400)
        gov.record_proposal_decision(ESCALATION_MANAGER, proposal, approved=approve, note=note, by=by)
        decision = {"action": "approve" if approve else "reject", "note": note, "proposal_id": str(proposal.pk), "version": proposal.version}
        case = governance.open_approval_case_for(EscalationCase.Subject.PROPOSAL, proposal.pk)
        if case is not None:
            gov.resolve_case(ESCALATION_MANAGER, case, decision=decision, by=by)
        if not approve:
            # Nothing runs; a request paused on this approval (e.g. agent_correction) ends here.
            if case is None or case.task is None:
                return None
            return dispatcher.resume_after_decision(origin=case.task, resume_task_type="", decision=decision, by=by)
        # Execution is tech_operations' job; a proposal created outside a task (seed data) gets its own follow-up.
        return dispatcher.resume_after_decision(
            origin=case.task if case is not None else None,
            resume_task_type=(case.resume_task_type if case is not None else "") or "tech_operations.execute_proposal",
            decision=decision,
            by=by,
            reference=str(case.pk if case is not None else proposal.pk),
            subject_id=str(proposal.pk),
        )


escalation_manager = EscalationManager()
