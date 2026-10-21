
"""Founder approval requests for technical recovery."""

from django.db import transaction

from domain.governance.models import (
    IncidentRecord,
    UpdateProposal,
)
from domain.governance.services import create_proposal


ALLOWED_RECOVERY_ACTIONS = (
    "retry_request",
    "request_founder_review",
    "resume_agent",
)


def request_recovery_approval(
    incident_id: str,
    *,
    action: str,
    rationale: str,
    agent_id: str | None = None,
) -> tuple[UpdateProposal, bool]:
    """Create or reuse a pending recovery proposal."""

    incident = IncidentRecord.objects.get(pk=incident_id)

    # 1. Validate recovery action.
    if action not in ALLOWED_RECOVERY_ACTIONS:
        raise ValueError(
            "Unsupported recovery recommendation"
        )

    # 2. Validate the target agent for resume actions.
    if action == "resume_agent":
        if not agent_id:
            raise ValueError(
                "Agent ID required for resume"
            )

        if agent_id not in incident.affected_components:
            raise ValueError(
                "Agent is not associated with this incident"
            )

    # 3. Create or reuse a pending proposal.
    with transaction.atomic():

        existing_proposals = UpdateProposal.objects.filter(
            incident=incident,
            change_type="recovery",
            status="pending",
        )

        for existing in existing_proposals:
            payload = existing.payload or {}

            if (
                payload.get("action") == action
                and payload.get("agent_id") == agent_id
            ):
                return existing, False

        # 4. Create a new proposal.
        proposal = create_proposal(
            "tech_operations",
            change_type="recovery",
            title=(
                f"Recovery review: {incident.subject}"
            )[:200],
            rationale=rationale[:2000],
            status="pending",
            incident=incident,
            payload={
                "action": action,
                "incident_id": str(incident.pk),
                "agent_id": agent_id,
            },
            evidence_refs=[str(incident.pk)],
            validation=(
                "Verify agent health after the approved action."
            ),
            rollback=(
                "Stop the recovery attempt and "
                "escalate to Founder."
            ),
        )

        return proposal, True
