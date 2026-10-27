"""GovernanceDomain writes. First argument is always the actor (see domain.common)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db import models, transaction
from django.utils import timezone

from domain.common import AGENT_IDS, AGENT_NAMES, COMPONENT_NAMES, DomainError, check_writer, current_trace, role_of, save_fields, writes
from infrastructure.monitoring import log_event

from .models import RecoveryAttempt, AgentState, AgentTask, AuditLog, EscalationCase, IncidentRecord, Notification, ServiceRequest, UpdateProposal


# --- Audit Service (NFR-07) ---------------------------------------------------
def record_audit(
    actor: Any,
    action: str,
    target: Any = None,
    *,
    request_id: str | None = None,
    task: Any = None,
    detail: dict | None = None,
    model: str = "",
    tokens: dict | None = None,
    latency_ms: int | None = None,
) -> AuditLog | None:
    """Append one audit entry and emit the same event as a JSON log line."""
    trace = current_trace()
    if trace.get("audit_suppressed"):
        return None
    if isinstance(actor, str):
        actor_id = actor
        actor_role = "agent" if actor in AGENT_IDS else "component"
        actor_name = AGENT_NAMES.get(actor) or COMPONENT_NAMES.get(actor, actor)
    else:
        actor_id = str(actor.pk)
        actor_role = role_of(actor) or "unknown"
        actor_name = getattr(actor, "name", "") or actor.get_username()
    if isinstance(target, models.Model):
        target_type, target_id = target._meta.model_name, str(target.pk)
    elif isinstance(target, tuple):
        target_type, target_id = str(target[0]), str(target[1])
    else:
        target_type, target_id = "", str(target or "")
    task_id = str(task.pk) if isinstance(task, models.Model) else str(task or trace.get("task_id") or "")
    entry = AuditLog.objects.create(
        actor=actor_id,
        actor_role=actor_role,
        actor_name=actor_name,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=str(request_id or trace.get("request_id") or ""),
        task_id=task_id,
        detail=detail or {},
        model=model,
        tokens=tokens,
        latency_ms=latency_ms,
    )
    log_event(
        "audit",
        audit_id=str(entry.pk),
        actor=actor_id,
        actor_role=actor_role,
        action=action,
        target=f"{target_type}:{target_id}" if target_type else target_id,
        request_id=entry.request_id,
        task_id=task_id,
        detail=detail or {},
    )
    return entry


_save = save_fields


# --- Task Orchestrator writes (actor "task_queue") ------------------------------
@writes(ServiceRequest, "request.created")
def create_request(actor: Any, *, requester: Any, **fields: Any) -> ServiceRequest:
    """`actor` is the writing component (task_queue); `requester` is the user who made the request."""
    return ServiceRequest.objects.create(actor=requester, **fields)


def transition_request(actor: Any, request: ServiceRequest, status: str, **fields: Any) -> ServiceRequest:
    if status in (ServiceRequest.Status.COMPLETED, ServiceRequest.Status.FAILED):
        fields.setdefault("completed_at", timezone.now())
    detail = {"type": request.type, "status": status}
    if fields.get("error"):
        detail["error"] = fields["error"].get("code")
    return _save(actor, request, f"request.{status}", {"status": status, **fields}, detail)


def update_request(actor: Any, request: ServiceRequest, **fields: Any) -> ServiceRequest:
    """Bookkeeping fields only (remaining_steps, hops, replans); not a state change, not audited separately."""
    check_writer(actor, ServiceRequest)
    for name, value in fields.items():
        setattr(request, name, value)
    request.save(update_fields=[*fields, "updated_at"])
    return request


@writes(AgentTask, "task.queued")
def create_task(actor: Any, **fields: Any) -> AgentTask:
    return AgentTask.objects.create(**fields)


def transition_task(actor: Any, task: AgentTask, status: str, **fields: Any) -> AgentTask:
    if status not in (AgentTask.Status.QUEUED, AgentTask.Status.RUNNING):
        fields.setdefault("finished_at", timezone.now())
    detail = {"task_type": task.task_type, "status": status}
    for key in ("reason", "confidence"):
        if fields.get(key) not in (None, ""):
            detail[key] = fields[key]
    return _save(actor, task, f"task.{status}", {"status": status, **fields}, detail)


# --- Escalation Manager writes (actor "escalation_manager") ---------------------
@writes(EscalationCase, "escalation.created")
def create_case(actor: Any, **fields: Any) -> EscalationCase:
    return EscalationCase.objects.create(**fields)


@transaction.atomic
def resolve_case(actor: Any, case: EscalationCase, *, decision: dict, by: Any) -> EscalationCase:
    EscalationCase.objects.select_for_update().get(pk=case.pk)
    case.refresh_from_db()
    if case.status != EscalationCase.Status.OPEN:
        raise DomainError("case_not_open", "This case has already been decided.")
    return _save(
        actor,
        case,
        "escalation.resolved",
        {
            "status": EscalationCase.Status.RESOLVED,
            "decision": decision,
            "outcome": str(decision.get("action", "")),
            "resolved_at": timezone.now(),
            "resolved_by": by,
        },
        {
            "subject_type": case.subject_type,
            "action": decision.get("action"),
            "by": str(getattr(by, "pk", by)),
            "summary": f"{decision.get('action')} by {getattr(by, 'name', by)}",
        },
    )


@writes(Notification, "notification.created")
def notify(actor: Any, *, recipient: Any, kind: str, ref: str) -> Notification:
    return Notification.objects.create(recipient=recipient, kind=kind, ref=ref)


def record_proposal_decision(actor: Any, proposal: UpdateProposal, *, approved: bool, note: str, by: Any) -> UpdateProposal:
    if proposal.status != "pending":
        raise DomainError("proposal_not_pending", "This proposal has already been decided.")
    return _save(
        actor,
        proposal,
        "proposal.approved" if approved else "proposal.rejected",
        {"status": "approved" if approved else "rejected", "decided_by": by, "decided_at": timezone.now(), "decision_note": note},
        {"version": proposal.version, "summary": f"{'approve' if approved else 'reject'} by {getattr(by, 'name', by)}"},
    )


# --- Technical Manager writes (actor "tech_operations") --------------------------
@writes(IncidentRecord, "incident.created")
def create_incident(actor: Any, **fields: Any) -> IncidentRecord:
    return IncidentRecord.objects.create(**fields)


def update_incident(actor: Any, incident: IncidentRecord, **fields: Any) -> IncidentRecord:
    return _save(actor, incident, "incident.updated", fields, {"status": fields.get("status", incident.status)})


@writes(UpdateProposal, "proposal.created")
def create_proposal(actor: Any, **fields: Any) -> UpdateProposal:
    return UpdateProposal.objects.create(**fields)


def record_proposal_execution(actor: Any, proposal: UpdateProposal, *, execution_status: str, verification: str | None = None) -> UpdateProposal:
    """Execution and verification are separate audit events from approval (state rule)."""
    if proposal.status != "approved":
        raise DomainError("proposal_not_approved", "Only an approved proposal can be executed.")
    action = "proposal.verified" if verification else f"proposal.execution_{execution_status}"
    return _save(actor, proposal, action, {"execution_status": execution_status, "verification": verification}, {"version": proposal.version})


# --- Agent supervision (Founder, UC09 5a) ---------------------------------------
def set_agent_state(actor: Any, agent_id: str, *, status: str, note: str = "") -> AgentState:
    if agent_id not in AGENT_IDS:
        raise DomainError("unknown_agent", f"Unknown agent: {agent_id}", status=404)
    state = AgentState.objects.filter(agent_id=agent_id).first() or AgentState(agent_id=agent_id)
    return _save(actor, state, f"agent.{status}", {"status": status, "note": note}, {"agent_id": agent_id})


def request_agent_correction(actor: Any, agent_id: str, *, note: str, case_id: str | None = None) -> None:
    check_writer(actor, AgentState)
    record_audit(actor, "agent.correction_requested", ("agent", agent_id), detail={"note": note, "case_id": case_id})


def touch(obj: models.Model, when: datetime) -> None:
    """Seeding helper: backdate created_at/updated_at (management commands only)."""
    type(obj).objects.filter(pk=obj.pk).update(created_at=when, updated_at=when)


def set_agent_timeout_override(
    actor,
    agent_id: str,
    timeout_seconds: int | None,
):
    """Persist an approved timeout override.

    Approval must be verified by the calling executor.
    """

    from .models import AgentRuntimeOverride

    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("Invalid agent ID")

    if timeout_seconds is not None:
        if (
            type(timeout_seconds) is not int
            or not 5 <= timeout_seconds <= 120
        ):
            raise ValueError("Invalid timeout value")

    override, _ = AgentRuntimeOverride.objects.update_or_create(
        agent_id=agent_id,
        defaults={
            "timeout_seconds": timeout_seconds,
        },
    )

    return override


def update_configuration_rollback_metadata(
    actor,
    proposal,
    *,
    previous_value,
    applied_value,
):
    """Persist rollback metadata for a configuration proposal."""

    if proposal.status != "approved":
        raise ValueError("Proposal must be approved")

    if proposal.change_type != "configuration":
        raise ValueError("Not a configuration proposal")

    return _save(
        actor,
        proposal,
        "proposal.rollback_metadata_saved",
        {
            "before": (
                "default"
                if previous_value is None
                else str(previous_value)
            ),
            "after": str(applied_value),
        },
        {
            "setting": "timeout_seconds",
            "rollback_available": True,
        },
    )


@transaction.atomic
def request_case_followup(actor, case, *, teacher, note, by):
    case = EscalationCase.objects.select_for_update().get(pk=case.pk)
    if case.status != "open":
        raise DomainError("case_not_open", "This case has already been decided.")
    existing = EscalationCase.objects.filter(subject_type="business", subject_id=str(case.pk), status="open").first()
    if existing:
        raise DomainError("followup_pending", "A teacher is already following up this case.")
    child = create_case(actor, kind="review", subject_type="business", subject_id=str(case.pk),
                        student=case.student, assignee=teacher, summary=case.summary,
                        trigger=note, diagnosis=case.diagnosis, evidence=case.evidence)
    _save(actor, case, "escalation.followup_requested", {
        "outcome": "followup_pending",
        "decision": {"action": "request_followup", "note": note, "followup_id": str(child.pk)},
    }, {"summary": f"Follow-up requested from {teacher.name}", "by": str(by.pk)})
    return child


@transaction.atomic
def record_followup_response(actor, child, *, decision, by):
    parent = EscalationCase.objects.select_for_update().filter(pk=child.subject_id, subject_type="business").first()
    if parent is None:
        raise DomainError("followup_not_found", "The original exception could not be found.")
    resolve_case(actor, child, decision=decision, by=by)
    _save(actor, parent, "escalation.followup_received", {
        "outcome": "followup_received",
        "evidence": [*parent.evidence, {"ref": str(child.pk), "summary": f"Teacher follow-up ({by.name}): {decision['note']}"}],
        "decision": {"action": "followup_received", "note": decision["note"]},
    }, {"summary": "Teacher follow-up received; Founder resolution still required."})
    if parent.assignee:
        notify(actor, recipient=parent.assignee, kind="followup_received", ref=str(parent.pk))


@writes(RecoveryAttempt, "recovery.attempt_created")
def create_recovery_attempt(actor, **fields):
    return RecoveryAttempt.objects.create(**fields)
