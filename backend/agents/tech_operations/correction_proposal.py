
"""Create controlled agent configuration update proposals."""

from django.db import transaction

from domain.governance.models import UpdateProposal
from domain.governance.services import create_proposal

from .correction import CorrectionRequest


def create_correction_proposal(
    correction: CorrectionRequest,
) -> tuple[UpdateProposal, bool]:
    """Create or reuse a pending configuration update proposal."""

    payload = {
        "action": "update_agent_setting",
        "agent_id": correction.agent_id,
        "setting": correction.setting,
        "new_value": correction.new_value,
    }

    with transaction.atomic():
        pending = UpdateProposal.objects.filter(
            change_type="configuration",
            status="pending",
        )

        for proposal in pending:
            existing = proposal.payload or {}

            if (
                existing.get("action") == payload["action"]
                and existing.get("agent_id") == payload["agent_id"]
                and existing.get("setting") == payload["setting"]
                and existing.get("new_value") == payload["new_value"]
            ):
                return proposal, False

        proposal = create_proposal(
            "tech_operations",
            change_type="configuration",
            title=(
                f"Update {correction.agent_id}: "
                f"{correction.setting}"
            )[:200],
            rationale=correction.reason[:2000],
            status="pending",
            payload=payload,
            # Display text only: execution replaces before/after with rollback metadata.
            before=f"Current {correction.setting} of {correction.agent_id}",
            after=f"{correction.setting} = {correction.new_value}",
            validation=(
                "Verify the new setting is applied "
                "and remains within the approved range."
            ),
            rollback=(
                "Restore the previous setting value "
                "if verification fails."
            ),
        )

        return proposal, True


def create_manual_proposal(
    note: str,
    *,
    title: str,
    before: str,
    after: str,
    validation: str,
    rollback: str,
) -> tuple[UpdateProposal, bool]:
    """A correction no executor can apply: approved, then made by a person."""

    proposal = create_proposal(
        "tech_operations",
        change_type="manual",
        title=title[:200],
        rationale=note[:2000],
        status="pending",
        payload={"action": "manual_change"},
        before=before,
        after=after,
        validation=validation,
        rollback=rollback,
    )

    return proposal, True
