"""Founder operations: business cases, technical incidents, agent supervision, proposals (UC09, UC10)."""

from ninja import Router
from ninja.errors import HttpError

from access_control.identity.permissions import require_role
from domain.common import AGENT_IDS, DomainError, Role
from domain.governance import selectors as governance
from domain.governance import services as gov
from domain.governance import views as gviews
from domain.governance.models import EscalationCase
from domain.governance.models import IncidentRecord
from domain.governance.models import UpdateProposal
from orchestration.escalation import escalation_manager
from orchestration.task_queue import dispatcher, registry
from orchestration.task_queue.contracts import CaseRecord, ProposalRecord
from agents.tech_operations.monitoring import collect_agent_health
from django.http import Http404
from agents.tech_operations.timeline import get_incident_timeline
from agents.tech_operations.reporting import generate_maintenance_report
from agents.tech_operations.student_records import (
    get_student_archive_eligibility,
)

from .. import lookups
from ..schemas import AgentDecisionIn, AgentDecisionOut, CaseDecisionIn, CaseDecisionOut, ProposalDecisionIn, ProposalDecisionOut

from uuid import UUID

from django.http import Http404
from domain.governance.models import AuditLog

from agents.tech_operations.student_records import (
    get_student_record_health,
)

from agents.tech_operations.configuration_workflow import (
    execute_configuration_workflow,
)
from agents.tech_operations.configuration_rollback import (
    create_rollback_proposal,
)

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


@router.get("/agents/health")
def get_agents_health(request):
    """
    Return operational health information for all monitored agents.

    Only the Human Founder/Operator can access this endpoint.
    No student records or private conversation data are returned.
    """
    _founder(request)

    agents = collect_agent_health()

    return {
        "total_agents": len(agents),
        "agents": agents,
    }


@router.get("/operations/audit-logs")
def get_operational_audit_logs(
    request,
    limit: int = 50,
    incident_id: str | None = None,
):
    """Return operational audit logs to the Founder only."""

    _founder(request)

    # Prevent excessively large responses.
    limit = max(1, min(limit, 100))

    logs = AuditLog.objects.all()

    if incident_id is not None:
        try:
            incident_uuid = UUID(incident_id)
        except (ValueError, AttributeError):
            raise Http404("Invalid incident ID")

        # Validate that the incident exists.
        incident = governance.incident(incident_uuid)

        if incident is None:
            raise Http404("Incident not found")

        logs = logs.filter(
            target_type="incidentrecord",
            target_id=str(incident.pk),
        )
    else:
        # Exclude noisy task/request events.
        logs = logs.exclude(
            action__startswith="task."
        ).exclude(
            action__startswith="request."
        ).exclude(
            action__startswith="notification."
        )

    logs = logs.order_by("-created_at")[:limit]

    return {
        "total": len(logs),
        "logs": [
            {
                "id": str(log.pk),
                "created_at": log.created_at.isoformat(),
                "actor": log.actor,
                "actor_role": log.actor_role,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "detail": log.detail,
            }
            for log in logs
        ],
    }

@router.get("/operations/incidents/{incident_id}/timeline")
def get_incident_audit_timeline(
    request,
    incident_id: str,
    limit: int = 100,
):
    """Founder-only incident audit timeline."""

    _founder(request)

    try:
        return get_incident_timeline(
            incident_id,
            limit=limit,
        )
    except (ValueError, IncidentRecord.DoesNotExist):
        raise Http404("Incident not found")


@router.get("/operations/maintenance-report")
def get_maintenance_report(request, days: int = 7):
    """Founder-only maintenance report."""

    _founder(request)

    return generate_maintenance_report(days=days)


@router.get(
    "/operations/students/{student_id}/record-health"
)
def get_student_record_health_api(
    request,
    student_id: str,
    history_limit: int = 20,
):
    """Founder-only student record maintenance summary."""

    _founder(request)

    try:
        UUID(student_id)
    except (ValueError, TypeError):
        raise HttpError(400, "Invalid student ID")

    if not 1 <= history_limit <= 100:
        raise HttpError(
            400,
            "history_limit must be between 1 and 100",
        )

    try:
        return get_student_record_health(
            student_id,
            history_limit=history_limit,
        )
    except LookupError:
        raise HttpError(404, "Student not found")


@router.get(
    "/operations/students/{student_id}/archive-eligibility"
)
def get_archive_eligibility_api(
    request,
    student_id: str,
):
    """Founder-only archive eligibility check."""

    _founder(request)

    try:
        UUID(student_id)
    except (ValueError, TypeError):
        raise HttpError(400, "Invalid student ID")

    try:
        return get_student_archive_eligibility(student_id)
    except LookupError:
        raise HttpError(404, "Student not found")


@router.post("/operations/configuration/{proposal_id}/execute")
def execute_configuration_api(request, proposal_id: str):
    """Founder-only approved configuration execution."""

    _founder(request)

    try:
        UUID(proposal_id)
    except (ValueError, TypeError):
        raise HttpError(400, "Invalid proposal ID")

    try:
        return execute_configuration_workflow(proposal_id)

    except LookupError:
        raise HttpError(404, "Proposal not found")

    except PermissionError:
        raise HttpError(403, "Founder approval required")

    except ValueError as exc:
        raise HttpError(409, str(exc))


@router.post("/operations/configuration/{proposal_id}/rollback")
def request_configuration_rollback_api(request, proposal_id: str):
    """Create a rollback proposal; do not execute it yet."""

    _founder(request)

    try:
        UUID(proposal_id)
    except (ValueError, TypeError):
        raise HttpError(400, "Invalid proposal ID")

    try:
        rollback = create_rollback_proposal(proposal_id)

    except UpdateProposal.DoesNotExist:
        raise HttpError(404, "Original proposal not found")

    except PermissionError:
        raise HttpError(403, "Original proposal not approved")

    except ValueError as exc:
        raise HttpError(409, str(exc))

    return {
        "proposal_id": str(rollback.pk),
        "status": rollback.status,
        "action": rollback.payload["action"],
        "original_proposal_id": proposal_id,
    }
