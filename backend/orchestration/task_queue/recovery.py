"""UC10 controlled retries. Only the orchestrator replays tasks; no private payload reaches the manager."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel

from agents.runtime.tools import ToolSpec
from domain.governance.models import AgentTask, IncidentRecord, RecoveryAttempt, UpdateProposal
from domain.governance import services as gov
from domain.learning import selectors as learning

SAFE_TASKS = {"teaching_support.lesson_briefing", "teaching_support.recommend_adjustments"}
TRANSIENT_REASONS = {"llm_unavailable", "task_timeout", "provider_timeout", "transient_timeout"}

class RecoveryInput(BaseModel):
    incident_id: str
    proposal_id: str | None = None


def _finish(incident, proposal, *, verified, message):
    status = "succeeded" if verified else "failed"
    gov.update_incident("tech_operations", incident, status="resolved" if verified else "escalated",
                        verification="retry_verified" if verified else "retry_failed")
    if proposal:
        gov.record_proposal_execution("tech_operations", proposal, execution_status=status,
                                      verification=incident.verification)
    gov.record_audit("tech_operations", "maintenance.report", incident,
                     detail={"summary": message, "verified": verified, "incident_status": incident.status})
    return {"incident_id": str(incident.pk), "execution_status": status, "verified": verified,
            "recovery_performed": verified, "incident_status": incident.status, "message": message}


def execute_retry(incident_id, proposal_id=None):
    from . import dispatcher
    proposal = None
    with transaction.atomic():
        incident = IncidentRecord.objects.select_for_update().get(pk=incident_id)
        if proposal_id:
            proposal = UpdateProposal.objects.select_for_update().get(pk=proposal_id)
            if proposal.status != "approved" or proposal.incident_id != incident.pk or proposal.payload.get("action") != "retry_request":
                raise PermissionError("A matching approved recovery proposal is required.")
            if proposal.execution_status != "not_started":
                return {"execution_status": proposal.execution_status, "verified": proposal.execution_status == "succeeded"}
        if incident.status in ("resolved", "closed"):
            return {"execution_status": "skipped", "verified": False, "message": "Incident is already closed; no task was replayed."}
        refs = [e.get("ref", "")[5:] for e in incident.evidence if isinstance(e, dict) and str(e.get("ref", "")).startswith("task:")]
        source = AgentTask.objects.select_for_update().filter(pk__in=refs).select_related("request__actor").order_by("-created_at").first()
        if source:
            previous = RecoveryAttempt.objects.filter(source_task=source).select_related("retry_task").first()
            if previous:
                verified = bool(previous.retry_task and previous.retry_task.status == "succeeded")
                return {"execution_status": "succeeded" if verified else "already_attempted", "verified": verified,
                        "recovery_performed": False, "message": "This task already received its controlled retry."}
        if (incident.status in ("resolved", "closed") or source is None or source.status != "failed"
            or source.task_type not in SAFE_TASKS or source.reason not in TRANSIENT_REASONS
            or source.target_agent not in incident.affected_components or source.request is None
            or source.request.status != "failed" or source.request.remaining_steps):
            return _finish(incident, proposal, verified=False,
                           message="No eligible read-only failed task. Founder follow-up is required; no task was replayed.")
        request = source.request
        if request.actor_role == "teacher" and (not request.actor or source.student_id not in learning.students_with_plan_teacher(request.actor)):
            return _finish(incident, proposal, verified=False, message="The original teacher no longer has access. No task was replayed.")
        # It starts as running so a background worker cannot claim it in parallel.
        retry = gov.create_task("task_queue", request=request, task_type=source.task_type,
                                target_agent=source.target_agent, student=source.student, payload=source.payload,
                                parent=source, status="running", started_at=timezone.now(),
                                deadline_at=timezone.now() + timedelta(seconds=120))
        gov.create_recovery_attempt("task_queue", incident=incident, source_task=source, retry_task=retry)
        gov.transition_request("task_queue", request, "running", error=None, completed_at=None)
        gov.update_incident("tech_operations", incident, status="recovering", recovery_action="retry_request")
        if proposal:
            gov.record_proposal_execution("tech_operations", proposal, execution_status="running")
    dispatcher.run_task(retry)
    retry.refresh_from_db()
    request.refresh_from_db()
    verified = retry.status == "succeeded" and request.status == "completed"
    return _finish(incident, proposal, verified=verified,
                   message="Controlled retry completed and its result was verified; incident closed." if verified
                   else "The controlled retry did not complete successfully. Incident escalated for Founder follow-up.")


def recovery_tool():
    return ToolSpec("recover_incident", "Run one validated read-only retry for a technical incident.",
                    RecoveryInput, execute_retry, "db", read_only=False)
