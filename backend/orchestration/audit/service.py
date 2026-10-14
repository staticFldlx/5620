"""Audit Service (NFR-07), interface from spec 5.5.

Three kinds of events are recorded automatically: Orchestrator task/request state changes,
every domain service write, and every EscalationManager decision. Agents do not need to call
this; use it only for additional events worth auditing.
"""

from domain.governance.services import record_audit


def record(actor, action, target=None, *, request_id=None, task=None, detail=None):
    return record_audit(actor, action, target, request_id=request_id, task=task, detail=detail)
