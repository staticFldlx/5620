from ninja import Router

from access_control.identity.permissions import Forbidden, can_access_student, require_role
from domain.common import DomainError, Role
from domain.governance import selectors as governance
from domain.governance.models import ServiceRequest
from domain.governance.views import request_envelope, task_trace_view
from domain.learning import selectors as learning
from orchestration.task_queue import dispatcher, pipelines
from orchestration.task_queue.contracts import EnvelopeRecord

from .. import lookups
from ..errors import ApiError
from ..schemas import RequestIn

router = Router(tags=["requests"])


def respond(service_request: ServiceRequest) -> dict:
    """A request that already failed synchronously is returned as HTTP 422 so the page shows the reason (A5)."""
    envelope = request_envelope(service_request)
    if service_request.status == ServiceRequest.Status.FAILED:
        error = service_request.error or {}
        raise ApiError(error.get("code", "request_failed"), error.get("message", "The request failed."), status=422, extra={"request": envelope})
    return envelope


def _student_for(user, role: str, pipeline: pipelines.Pipeline, body: RequestIn):
    scope = pipeline.student_scope
    if scope == "none":
        return None
    if scope == "lesson":
        lesson = lookups.get_or_404(learning.lesson, body.input.get("lesson_id") or body.context_id, "Lesson")
        lookups.require_owner(lesson.teacher_id == user.pk, "You do not teach this lesson.")
        return lesson.student
    if role == Role.STUDENT:
        if body.student_id and body.student_id != str(user.pk):
            raise Forbidden("forbidden_student_access", "Students can only make requests for themselves.")
        return user
    if not body.student_id:
        raise DomainError("student_id_required", "Choose a student for this request.", status=400)
    return lookups.accessible_student(user, body.student_id)


def _waiting_request(user, body: RequestIn) -> ServiceRequest | None:
    """B3: a request whose context_id is a request awaiting input is a reply to it."""
    pk = lookups.parse_uuid(body.context_id)
    waiting = governance.service_request(pk) if pk else None
    if waiting is None or waiting.status != ServiceRequest.Status.AWAITING_INPUT or waiting.type != body.type:
        return None
    lookups.require_owner(waiting.actor_id == user.pk, "Only the person who made the request can answer it.")
    return waiting


def _goal_follow_up(user, body: RequestIn) -> ServiceRequest | None:
    """A goal answer must never be mistaken for a new goal request.

    Retrying a reply after the first response completed is idempotent. A stale
    question gives a useful error instead of `goal_text: Field required`.
    """
    if body.type != "collect_goal" or "answer" not in body.input:
        return None
    pk = lookups.parse_uuid(body.context_id)
    previous = governance.service_request(pk) if pk else None
    if previous is None or previous.type != body.type:
        raise DomainError("follow_up_expired", "This question is no longer available. Organise your goal again.", status=409)
    lookups.require_owner(previous.actor_id == user.pk, "Only the person who made the request can answer it.")
    if previous.status == ServiceRequest.Status.AWAITING_INPUT:
        return dispatcher.reply(previous, input=body.input)
    if previous.status in (ServiceRequest.Status.QUEUED, ServiceRequest.Status.RUNNING, ServiceRequest.Status.COMPLETED):
        return previous
    raise DomainError("follow_up_expired", "This question is no longer available. Organise your goal again.", status=409)


@router.post("/requests", response=EnvelopeRecord)
def create_request(request, body: RequestIn):
    user = request.auth
    role = require_role(user, Role.STUDENT, Role.TEACHER)
    goal_follow_up = _goal_follow_up(user, body)
    if goal_follow_up is not None:
        return respond(goal_follow_up)
    waiting = _waiting_request(user, body)
    if waiting is not None:
        return respond(dispatcher.reply(waiting, input=body.input))
    pipeline = pipelines.get(body.type)
    if not pipeline.public:
        raise DomainError("unknown_request_type", f"Unknown request type: {body.type}", status=400)
    if role not in pipeline.roles:
        raise Forbidden("forbidden_request_type", f"{body.type} is not available to the {role} role.")
    student = _student_for(user, role, pipeline, body)
    created = dispatcher.submit(body.type, actor=user, actor_role=role, student=student, input=body.input, context_id=body.context_id or "")
    return respond(created)


def _readable_request(user, request_id: str) -> ServiceRequest:
    found = lookups.get_or_404(governance.service_request, request_id, "Request")
    if found.actor_id == user.pk or (found.student is not None and can_access_student(user, found.student)):
        return found
    raise Forbidden()


@router.get("/requests/{request_id}", response=EnvelopeRecord)
def get_request(request, request_id: str):
    return request_envelope(_readable_request(request.auth, request_id))


@router.get("/requests/{request_id}/trace")
def get_trace(request, request_id: str):
    """Optional (spec 6.2): every task with tool calls, confidence and escalation reasons."""
    user = request.auth
    role = require_role(user, Role.FOUNDER, Role.STUDENT, Role.TEACHER)
    found = lookups.get_or_404(governance.service_request, request_id, "Request")
    lookups.require_owner(role == Role.FOUNDER or found.actor_id == user.pk)
    return {"request": request_envelope(found), "tasks": [task_trace_view(t) for t in governance.tasks_for(found)]}
