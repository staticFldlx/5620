
"""Execute Founder-approved runtime configuration updates."""

from django.db import transaction

from domain.governance.models import UpdateProposal
from domain.governance.selectors import agent_timeout_override
from domain.governance.services import (
    set_agent_timeout_override,
    record_proposal_execution,
    update_configuration_rollback_metadata,
)

from .correction import validate_correction


def execute_approved_configuration(proposal_id: str) -> dict:
    """Apply and verify an approved agent timeout update."""

    with transaction.atomic():

        # 1. Retrieve the proposal.
        proposal = UpdateProposal.objects.get(
            pk=proposal_id
        )

        # 2. Verify Founder approval.
        if proposal.change_type != "configuration":
            raise ValueError("Not a configuration proposal")

        if proposal.status != "approved":
            raise PermissionError("Founder approval required")

        if proposal.execution_status != "not_started":
            raise ValueError("Proposal already executed")

        # 3. Validate the requested action.
        payload = proposal.payload or {}

        if payload.get("action") != "update_agent_setting":
            raise ValueError("Unsupported action")

        if payload.get("setting") != "timeout_seconds":
            raise ValueError("Unsupported setting")

        correction = validate_correction({
            "agent_id": payload.get("agent_id"),
            "setting": payload.get("setting"),
            "new_value": payload.get("new_value"),
            "reason": proposal.rationale,
        })

        # 4. Read the previous configuration.
        previous_value = agent_timeout_override(
            correction.agent_id
        )

        # 5. Apply the approved configuration.
        set_agent_timeout_override(
            "tech_operations",
            correction.agent_id,
            correction.new_value,
        )

        # 6. Verify the saved configuration.
        saved_value = agent_timeout_override(
            correction.agent_id
        )

        if saved_value != correction.new_value:
            raise RuntimeError(
                "Configuration verification failed"
            )

        # 7. Persist rollback metadata.
        update_configuration_rollback_metadata(
            "tech_operations",
            proposal,
            previous_value=previous_value,
            applied_value=saved_value,
        )

        # 8. Record successful execution.
        record_proposal_execution(
            "tech_operations",
            proposal,
            execution_status="succeeded",
            verification=f"timeout_seconds={saved_value}",
        )

        # 9. Return execution result.
        return {
            "proposal_id": str(proposal.pk),
            "agent_id": correction.agent_id,
            "setting": correction.setting,
            "previous_value": previous_value,
            "new_value": saved_value,
            "execution_status": "succeeded",
            "verified": True,
        }
