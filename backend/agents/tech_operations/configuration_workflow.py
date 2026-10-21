
"""Dispatch approved configuration changes and rollbacks."""

from domain.governance.selectors import proposal as get_proposal

from .configuration_executor import execute_approved_configuration
from .configuration_rollback import execute_approved_rollback


def execute_configuration_workflow(proposal_id: str) -> dict:
    """Execute an approved configuration proposal."""

    item = get_proposal(proposal_id)

    if item is None:
        raise LookupError("Proposal not found")

    if item.change_type != "configuration":
        raise ValueError("Not a configuration proposal")

    if item.status != "approved":
        raise PermissionError("Founder approval required")

    if item.execution_status != "not_started":
        raise ValueError("Proposal already executed")

    action = (item.payload or {}).get("action")

    if action == "update_agent_setting":
        return execute_approved_configuration(proposal_id)

    if action == "rollback_agent_setting":
        return execute_approved_rollback(proposal_id)

    raise ValueError("Unsupported configuration action")
