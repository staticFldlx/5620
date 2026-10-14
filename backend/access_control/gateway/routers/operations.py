"""Founder operations: business cases, technical incidents, agent supervision, proposals (UC09, UC10)."""

from ninja import Router

from access_control.identity.permissions import require_role
from domain.common import AGENT_IDS, DomainError, Role
from domain.governance import selectors as governance
from domain.governance import services as gov
from domain.governance import views as gviews
from domain.governance.models import EscalationCase
from orchestration.escalation import escalation_manager
from orchestration.task_queue import dispatcher, registry
from orchestration.task_queue.contracts import CaseRecord, ProposalRecord

from .. import lookups
from ..schemas import AgentDecisionIn, AgentDecisionOut, CaseDecisionIn, CaseDecisionOut, ProposalDecisionIn, ProposalDecisionOut

router = Router(tags=["operations"])


def _founder(request):
    require_role(request.auth, Role.FOUNDER)
    return request.auth


def _envelope(follow_up):
    return gviews.request_envelope(follow_up) if follow_up is not None else None


@router.get("/cases/{case_id}", response=CaseRecord)
def get_case(request, case_id: str):
    _founder(request)
    pk = lookups.parse_uuid(case_id)
    incident = governance.incident(pk) if pk else None
    if incident is not None:
        return gviews.incident_case_view(incident)
    case = governance.case(pk) if pk else None
    if case is None or case.subject_type != EscalationCase.Subject.BUSINESS:
        raise lookups.not_found("Case")
    return gviews.business_case_view(case)


@router.post("/cases/{case_id}/decision", response=CaseDecisionOut)
def decide_case(request, case_id: str, body: CaseDecisionIn):
    """Unresolved business exception (UC09). Technical changes go through proposals instead."""
    user = _founder(request)
    pk = lookups.parse_uuid(case_id)
    if pk is not None and governance.incident(pk) is not None:
        raise DomainError("use_proposal_decision", "Technical incidents are changed through an update proposal.")
    case = lookups.get_or_404(governance.case, case_id, "Case")
    if case.subject_type != EscalationCase.Subject.BUSINESS:
        raise lookups.not_found("Case")
    follow_up = escalation_manager.decide_business_case(case, action=body.action, note=body.note, by=user)
    case.refresh_from_db()
    return {**gviews.business_case_view(case), "follow_up": _envelope(follow_up)}


@router.post("/agents/{agent_id}/decision", response=AgentDecisionOut)
def decide_agent(request, agent_id: str, body: AgentDecisionIn):
    """UC09 5a: pause an agent (its tasks fail with agent_paused) or ask for a correction."""
    user = _founder(request)
    internal = gviews.internal_agent_id(agent_id)
    if internal not in AGENT_IDS:
        raise lookups.not_found("Agent")
    if not body.note.strip():
        raise DomainError("note_required", "Explain the decision in the note.", status=400)
    follow_up = None
    if body.action == "pause":
        gov.set_agent_state(user, internal, status="paused", note=body.note)
        status = "paused"
    elif body.action == "resume":
        gov.set_agent_state(user, internal, status="healthy", note=body.note)
        status = "resumed"
    elif body.action == "request_correction":
        gov.request_agent_correction(user, internal, note=body.note, case_id=body.case_id)
        follow_up = dispatcher.start_follow_up("agent_correction", actor=user, payload={"agent_id": internal, "note": body.note, "case_id": body.case_id})
        status = "requested"
    else:
        raise DomainError("invalid_action", "action must be pause, resume or request_correction.", status=400)
    agent = gviews.agent_view(
        internal, state=governance.agent_state(internal), latest=governance.latest_task_for_agent(internal), implemented=registry.is_implemented(internal)
    )
    return {"agent": agent, "status": status, "follow_up": _envelope(follow_up)}


@router.get("/proposals/{proposal_id}", response=ProposalRecord)
def get_proposal(request, proposal_id: str):
    _founder(request)
    return gviews.proposal_view(lookups.get_or_404(governance.proposal, proposal_id, "Proposal"))


@router.post("/proposals/{proposal_id}/decision", response=ProposalDecisionOut)
def decide_proposal(request, proposal_id: str, body: ProposalDecisionIn):
    """Founder approval (AR12, C7). Approval does not mean execution: tech_operations executes and verifies."""
    user = _founder(request)
    proposal = lookups.get_or_404(governance.proposal, proposal_id, "Proposal")
    if body.action not in ("approve", "reject"):
        raise DomainError("invalid_action", "action must be approve or reject.", status=400)
    follow_up = escalation_manager.decide_proposal(proposal, approve=body.action == "approve", note=body.note, by=user, version=body.version)
    return {**gviews.proposal_view(governance.proposal(proposal.pk)), "follow_up": _envelope(follow_up)}
