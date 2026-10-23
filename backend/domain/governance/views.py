"""Read models for governance records, matching the frontend types (src/api/types.ts)."""

from __future__ import annotations

from typing import Any

from domain.common import AGENT_NAMES, iso

from .models import AgentState, AgentTask, AuditLog, EscalationCase, IncidentRecord, ServiceRequest, UpdateProposal

# The frontend fixture uses these public ids; internally the spec ids are used (A7).
PUBLIC_AGENT_IDS = {"planning": "consultant", "teaching_support": "assistant", "tech_operations": "technical"}
INTERNAL_AGENT_IDS = {public: internal for internal, public in PUBLIC_AGENT_IDS.items()}

# Internal state machines -> words the frontend already uses (A16).
ENVELOPE_STATUS = {
    ServiceRequest.Status.QUEUED: "queued",
    ServiceRequest.Status.RUNNING: "running",
    ServiceRequest.Status.AWAITING_INPUT: "awaiting_confirmation",
    ServiceRequest.Status.ESCALATED: "escalated",
    ServiceRequest.Status.AWAITING_APPROVAL: "pending_review",
    ServiceRequest.Status.COMPLETED: "completed",
    ServiceRequest.Status.FAILED: "failed",
}
TASK_STATUS = {
    AgentTask.Status.QUEUED: "queued",
    AgentTask.Status.RUNNING: "running",
    AgentTask.Status.SUCCEEDED: "completed",
    AgentTask.Status.NEEDS_INPUT: "awaiting_input",
    AgentTask.Status.ESCALATED: "escalated",
    AgentTask.Status.AWAITING_APPROVAL: "pending_review",
    AgentTask.Status.FAILED: "failed",
}


def public_agent_id(agent_id: str) -> str:
    return PUBLIC_AGENT_IDS.get(agent_id, agent_id)


def internal_agent_id(agent_id: str) -> str:
    return INTERNAL_AGENT_IDS.get(agent_id, agent_id)


def request_envelope(request: ServiceRequest) -> dict:
    status = ENVELOPE_STATUS.get(request.status, request.status)
    envelope = {"id": str(request.pk), "type": request.type, "status": status, "phase": request.phase or status, "result": request.result or {}}
    if request.error:
        envelope["error"] = request.error
    return envelope


def task_summary(task: AgentTask) -> str:
    result = task.result or {}
    return str(result.get("summary") or result.get("message") or task.reason or task.task_type)


def task_trace_view(task: AgentTask) -> dict:
    return {
        "id": str(task.pk),
        "task_type": task.task_type,
        "agent_id": public_agent_id(task.target_agent),
        "status": TASK_STATUS.get(task.status, task.status),
        "confidence": task.confidence,
        "reason": task.reason or None,
        "hops": task.hops,
        "attempts": task.attempts,
        "parent_id": str(task.parent_id) if task.parent_id else None,
        "started_at": iso(task.started_at),
        "finished_at": iso(task.finished_at),
        "trace": task.trace or [],
    }


def review_view(case: EscalationCase) -> dict:
    """Frontend `Review`: a learning case assigned to a teacher."""
    return {
        "id": str(case.pk),
        "kind": case.subject_type,
        "student_id": str(case.student_id) if case.student_id else "",
        "subject_id": case.subject_id,
        "status": "pending" if case.status == EscalationCase.Status.OPEN else "decided",
        "trigger": case.trigger,
        "decision": (case.decision or {}).get("action"),
    }


def _decision_text(decision: dict | None) -> str | None:
    if not decision:
        return None
    note = decision.get("note")
    return f"{decision.get('action')}: {note}" if note else str(decision.get("action"))


def business_case_view(case: EscalationCase) -> dict:
    return {
        "available_actions": (["widen_match", "request_teacher", "resolve"] if case.task and case.task.target_agent == "planning" and case.task.reason == "teacher_unavailable" else ["resolve", "request_teacher"]),
        "id": str(case.pk),
        "kind": "business",
        "status": "pending" if case.status == EscalationCase.Status.OPEN else "resolved",
        "subject": case.summary or case.trigger[:120],
        "trigger": case.trigger,
        "diagnosis": case.diagnosis,
        "evidence": list(case.evidence or []),
        "proposal_id": None,
        "decision": _decision_text(case.decision),
        "verification": None,
    }


def incident_case_view(incident: IncidentRecord) -> dict:
    proposal = incident.proposals.order_by("-created_at").first()
    decision = None
    if proposal and proposal.status != "pending":
        decision = f"{proposal.status}: {proposal.decision_note}" if proposal.decision_note else proposal.status
    elif incident.recovery_action and incident.status == "resolved":
        decision = f"{incident.recovery_action} (Technical Manager)"
    return {
        "id": str(incident.pk),
        "kind": "technical",
        "status": incident.status,
        "subject": incident.subject,
        "trigger": incident.trigger,
        "diagnosis": incident.diagnosis,
        "evidence": list(incident.evidence or []),
        "proposal_id": str(proposal.pk) if proposal else None,
        "decision": decision,
        "verification": incident.verification,
    }


def proposal_view(proposal: UpdateProposal) -> dict:
    decision = None
    if proposal.status != "pending":
        action = "approve" if proposal.status == "approved" else "reject"
        decision = f"{action}: {proposal.decision_note}" if proposal.decision_note else action
    return {
        "id": str(proposal.pk),
        "type": proposal.change_type,
        "title": proposal.title,
        "case_id": str(proposal.incident_id) if proposal.incident_id else None,
        "status": proposal.status,
        "evidence": list(proposal.evidence_refs or []),
        "before": proposal.before,
        "after": proposal.after,
        "validation": proposal.validation,
        "rollback": proposal.rollback,
        "decision": decision,
        "execution": {"status": proposal.execution_status, "verification": proposal.verification},
        "version": proposal.version,
    }


def agent_view(agent_id: str, *, state: AgentState | None, latest: AgentTask | None, implemented: bool) -> dict:
    if state is not None and state.status != "healthy":
        status = state.status
    else:
        status = "healthy" if implemented else "not_implemented"
    latest_task = (
        {
            "id": str(latest.pk),
            "status": TASK_STATUS.get(latest.status, latest.status),
            "confidence": latest.confidence,
            "started_at": iso(latest.started_at or latest.created_at),
            "output_summary": task_summary(latest),
        }
        if latest
        else {"id": "", "status": "idle", "confidence": None, "started_at": None, "output_summary": "No tasks yet."}
    )
    return {"id": public_agent_id(agent_id), "name": AGENT_NAMES.get(agent_id, agent_id), "status": status, "latest_task": latest_task}


def log_view(task: AgentTask) -> dict:
    escalated = task.status in (AgentTask.Status.ESCALATED, AgentTask.Status.AWAITING_APPROVAL)
    severity = "error" if task.status == AgentTask.Status.FAILED else "warning" if escalated else "info"
    return {
        "id": str(task.pk),
        "time": iso(task.finished_at or task.started_at or task.created_at),
        "agent_id": public_agent_id(task.target_agent),
        "event": task_summary(task),
        "severity": severity,
        "task_status": TASK_STATUS.get(task.status, task.status),
        "confidence": task.confidence,
        "escalated": escalated,
    }


def warning_view(task: AgentTask) -> dict:
    return {
        "id": str(task.pk),
        "agent_id": public_agent_id(task.target_agent),
        "status": "open",
        "trigger": task.reason or "task_failed",
        "output_summary": task_summary(task),
        "created_at": iso(task.created_at),
    }


def audit_view(entry: AuditLog) -> dict:
    if entry.actor_role in ("agent", "component"):
        actor_role = entry.actor_name
    else:
        actor_role = entry.actor_role.title()
    detail = entry.detail or {}
    result = detail.get("summary") or detail.get("note") or detail.get("status") or detail.get("action") or ""
    return {
        "id": str(entry.pk),
        "time": iso(entry.created_at),
        "actor_role": actor_role,
        "actor_name": entry.actor_name,
        "subject_id": entry.target_id,
        "action": entry.action,
        "result": str(result),
    }
