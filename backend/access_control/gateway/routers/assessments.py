from ninja import Router, Status

from access_control.identity.permissions import Forbidden, ensure_student_access, require_role
from domain.common import DomainError, Role
from domain.governance import selectors as governance
from domain.governance.models import ServiceRequest
from domain.governance.views import request_envelope
from domain.learning import selectors as learning
from domain.learning.models import AssessmentSession
from domain.learning.views import session_view
from orchestration.task_queue import dispatcher
from orchestration.task_queue.contracts import AssessmentSessionRecord, EnvelopeRecord

from .. import lookups, presenters
from ..schemas import AnswerIn, AssessmentIn
from .requests import respond

router = Router(tags=["assessments"])
KINDS = set(AssessmentSession.Type.values)


def _session_response(service_request: ServiceRequest):
    """Session JSON once the assessment agent has created it; 202 + envelope while queued (worker mode)."""
    if service_request.status in (ServiceRequest.Status.QUEUED, ServiceRequest.Status.RUNNING):
        return Status(202, request_envelope(service_request))
    session = learning.assessment_session(lookups.parse_uuid((service_request.result or {}).get("session_id")))
    if session is None:
        respond(service_request)
        return Status(202, request_envelope(service_request))
    # A downstream planning failure must not hide the completed assessment.
    return Status(200, {**session_view(session), "follow_up": request_envelope(service_request)})


@router.post("/assessments", response={200: AssessmentSessionRecord, 202: EnvelopeRecord})
def start_assessment(request, body: AssessmentIn):
    """initial / milestone by the student; directed by an assigned teacher (UC02, UC05, UC06)."""
    user = request.auth
    role = require_role(user, Role.STUDENT, Role.TEACHER)
    if body.kind not in KINDS:
        raise DomainError("invalid_kind", "kind must be initial, milestone or directed.", status=400)
    if (role == Role.TEACHER) != (body.kind == "directed"):
        raise Forbidden("forbidden_assessment_kind", "Directed assessments are requested by teachers; students start initial or milestone ones.")
    student = lookups.accessible_student(user, body.student_id)
    if body.kind == "milestone":
        from orchestration.milestones import publish_ready_milestone
        milestone = publish_ready_milestone(student, user, retry_rejected=True)
        if milestone is not None:
            return _session_response(milestone)
    created = dispatcher.submit("start_assessment", actor=user, actor_role=role, student=student, input={"kind": body.kind, "focus": body.focus or ""})
    return _session_response(created)


def _session(user, assessment_id: str) -> AssessmentSession:
    pk = lookups.parse_uuid(assessment_id)
    session = learning.assessment_session(pk) if pk else None
    if session is None and pk is not None:  # a ProficiencyRecord id also resolves to its session
        record = learning.proficiency(pk)
        session = record.session if record else None
    if session is None:
        raise lookups.not_found("Assessment")
    ensure_student_access(user, session.student)
    return session


@router.get("/assessments/{assessment_id}", response=AssessmentSessionRecord)
def get_assessment(request, assessment_id: str):
    require_role(request.auth, Role.STUDENT, Role.TEACHER)
    return presenters.assessment_record(_session(request.auth, assessment_id))


@router.post("/assessments/{assessment_id}/answers", response={200: AssessmentSessionRecord, 202: EnvelopeRecord})
def answer_assessment(request, assessment_id: str, body: AnswerIn):
    user = request.auth
    require_role(user, Role.STUDENT)
    session = _session(user, assessment_id)
    if not body.answer.strip():
        raise DomainError("answer_required", "Please enter an answer.", status=400)
    if any(item.get("item_id") == body.item_id and item.get("answer") is not None for item in session.items or []):
        related = governance.request_for_assessment(session.pk)
        return _session_response(related) if related else Status(200, session_view(session))  # duplicate submission is idempotent
    waiting = governance.request_awaiting_session(session.pk)
    if waiting is None:
        raise DomainError("assessment_not_awaiting_answer", "This assessment is not waiting for an answer.")
    return _session_response(dispatcher.reply(waiting, input={"item_id": body.item_id, "answer": body.answer}))
