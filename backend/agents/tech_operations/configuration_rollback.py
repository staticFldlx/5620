
"""Controlled rollback proposals for agent configuration."""

from domain.governance.services import create_proposal
from django.db import transaction

from domain.governance.models import UpdateProposal
from domain.governance.selectors import agent_timeout_override
from domain.governance.services import (
    set_agent_timeout_override,
    record_proposal_execution,
)


def create_rollback_proposal(
    original_proposal_id: str,
) -> UpdateProposal:
    """Request rollback of an executed configuration update."""

    original = UpdateProposal.objects.get(
        pk=original_proposal_id
    )

    if original.change_type != "configuration":
        raise ValueError("Not a configuration proposal")

    if original.status != "approved":
        raise PermissionError("Original update was not approved")

    if original.execution_status != "succeeded":
        raise ValueError("Original update has not succeeded")

    payload = original.payload or {}

    if payload.get("action") != "update_agent_setting":
        raise ValueError("Unsupported original action")

    if payload.get("setting") != "timeout_seconds":
        raise ValueError("Unsupported rollback setting")

    if not original.after:
        raise ValueError("Missing rollback metadata")

    previous_value = (
        None
        if original.before == "default"
        else int(original.before)
    )

    rollback = create_proposal(
        "tech_operations",
        change_type="configuration",
        title=f"Rollback: {original.title}"[:200],
        rationale=(
            f"Restore the previous timeout setting for "
            f"{payload['agent_id']}."
        ),
        status="pending",
        payload={
            "action": "rollback_agent_setting",
            "agent_id": payload["agent_id"],
            "setting": "timeout_seconds",
            "restore_value": previous_value,
            "original_proposal_id": str(original.pk),
        },
        validation="Verify the previous timeout setting is restored.",
        rollback="Escalate to Founder if restoration fails.",
    )

    return rollback


from django.db import transaction

from domain.governance.selectors import agent_timeout_override
from domain.governance.services import (
    set_agent_timeout_override,
    record_proposal_execution,
)



def execute_approved_rollback(
    rollback_proposal_id: str,
) -> dict:
    """Execute a Founder-approved rollback with stale-state protection."""

    with transaction.atomic():
        proposal = UpdateProposal.objects.get(
            pk=rollback_proposal_id
        )

        # 1. Verify Founder approval.
        if proposal.change_type != "configuration":
            raise ValueError("Not a configuration proposal")

        if proposal.status != "approved":
            raise PermissionError("Founder approval required")

        if proposal.execution_status != "not_started":
            raise ValueError("Rollback already processed")

        payload = proposal.payload or {}

        if payload.get("action") != "rollback_agent_setting":
            raise ValueError("Not a rollback proposal")

        if payload.get("setting") != "timeout_seconds":
            raise ValueError("Unsupported rollback setting")

        # 2. Validate the original proposal.
        original_id = payload.get("original_proposal_id")

        if not original_id:
            raise ValueError("Missing original proposal ID")

        original = UpdateProposal.objects.get(pk=original_id)

        if original.change_type != "configuration":
            raise ValueError("Invalid original proposal type")

        if original.status != "approved":
            raise PermissionError("Original proposal was not approved")

        if original.execution_status != "succeeded":
            raise ValueError("Original update was not executed")

        original_payload = original.payload or {}

        if original_payload.get("action") != "update_agent_setting":
            raise ValueError("Invalid original action")

        if original_payload.get("setting") != "timeout_seconds":
            raise ValueError("Invalid original setting")

        # 3. Ensure rollback targets the original agent.
        agent_id = original_payload.get("agent_id")

        if payload.get("agent_id") != agent_id:
            raise ValueError("Rollback agent mismatch")

        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("Missing agent ID")

        # 4. Verify rollback metadata.
        if not original.after:
            raise ValueError("Original update has no rollback metadata")

        expected_current = int(original.after)

        restore_value = (
            None
            if original.before == "default"
            else int(original.before)
        )

        if payload.get("restore_value") != restore_value:
            raise ValueError("Rollback restore value mismatch")

        # 5. Prevent stale rollback.
        current_value = agent_timeout_override(agent_id)

        if current_value != expected_current:
            raise ValueError(
                "Stale rollback: agent configuration has changed"
            )

        # 6. Restore previous configuration.
        set_agent_timeout_override(
            "tech_operations",
            agent_id,
            restore_value,
        )

        # 7. Verify restored value.
        saved_value = agent_timeout_override(agent_id)

        if saved_value != restore_value:
            raise RuntimeError("Rollback verification failed")

        # 8. Record execution.
        record_proposal_execution(
            "tech_operations",
            proposal,
            execution_status="succeeded",
            verification="rollback_verified",
        )

        return {
            "proposal_id": str(proposal.pk),
            "original_proposal_id": str(original.pk),
            "agent_id": agent_id,
            "previous_value": expected_current,
            "restored_value": saved_value,
            "execution_status": "succeeded",
            "verified": True,
        }
