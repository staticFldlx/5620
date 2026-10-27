"""Controlled recovery execution for AI Technical Manager."""

from django.db import transaction

from domain.governance.models import (
    AgentState,
    UpdateProposal,
)
from domain.governance.services import (
    set_agent_state,
    update_incident,
    record_proposal_execution,
)


def execute_approved_recovery(proposal_id: str, runtime) -> dict:
    proposal = UpdateProposal.objects.get(pk=proposal_id)
    if proposal.change_type != "recovery" or proposal.status != "approved":
        raise PermissionError("Founder approval required")
    if not proposal.incident_id:
        raise ValueError("Recovery proposal has no incident")
    result = runtime.call_tool("recover_incident", {"incident_id": str(proposal.incident_id), "proposal_id": str(proposal.pk)})
    if "error" in result:
        raise ValueError(result["error"])
    return result


def resume_approved_agent(proposal_id: str) -> dict:
    """Resume a paused agent after Founder approval."""

    with transaction.atomic():
        proposal = UpdateProposal.objects.get(pk=proposal_id)

        # 1. Verify proposal type and approval.
        if proposal.change_type != "recovery":
            raise ValueError("Not a recovery proposal")

        if proposal.status != "approved":
            raise PermissionError("Founder approval required")

        if proposal.execution_status != "not_started":
            raise ValueError("Recovery already processed")

        # 2. Validate the requested action.
        payload = proposal.payload or {}

        if payload.get("action") != "resume_agent":
            raise ValueError("Unsupported recovery action")

        agent_id = payload.get("agent_id")

        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("Missing agent_id")

        # 3. Verify the linked incident.
        incident = proposal.incident

        if incident is None:
            raise ValueError("Recovery proposal has no incident")

        if agent_id not in incident.affected_components:
            raise ValueError(
                "Agent is not associated with this incident"
            )

        # 4. Verify the agent is paused.
        current = AgentState.objects.filter(
            agent_id=agent_id
        ).first()

        if current is None or current.status != "paused":
            raise ValueError("Agent is not paused")

        # 5. Perform the approved recovery.
        set_agent_state(
            "tech_operations",
            agent_id,
            status="healthy",
            note=f"Founder-approved recovery: {proposal.pk}",
        )

        # 6. Verify the state change.
        updated = AgentState.objects.get(agent_id=agent_id)
        verified = updated.status == "healthy"

        execution_status = (
            "succeeded" if verified else "failed"
        )

        # 7. Record execution and verification.
        record_proposal_execution(
            "tech_operations",
            proposal,
            execution_status=execution_status,
            verification=(
                "agent_state_healthy"
                if verified
                else "agent_state_verification_failed"
            ),
        )

        # 8. Update incident, but do not close it.
        update_incident(
            "tech_operations",
            incident,
            status="recovery_pending_verification"
            if verified else "escalated",
            verification=(
                "agent_resumed"
                if verified
                else "recovery_failed"
            ),
        )

        return {
            "proposal_id": str(proposal.pk),
            "incident_id": str(incident.pk),
            "agent_id": agent_id,
            "action": "resume_agent",
            "recovery_performed": True,
            "verified": verified,
            "execution_status": execution_status,
            "incident_status": (
                "recovery_pending_verification"
                if verified else "escalated"
            ),
        }


def verify_pending_recoveries():
    from domain.governance.models import AgentTask, IncidentRecord
    from domain.governance.services import record_audit
    for incident in IncidentRecord.objects.filter(status="recovery_pending_verification"):
        latest = AgentTask.objects.filter(target_agent__in=incident.affected_components, started_at__gt=incident.updated_at).order_by("-started_at").first()
        if latest is None or latest.status in ("queued", "running"):
            continue
        verified = latest.status == "succeeded"
        update_incident("tech_operations", incident, status="resolved" if verified else "escalated",
                        verification="fresh_task_verified" if verified else "fresh_task_failed")
        record_audit("tech_operations", "maintenance.report", incident,
                     detail={"summary": "Post-recovery task verified; incident closed." if verified else "Post-recovery task failed; Founder follow-up required.", "verified": verified})
