"""Task Orchestrator (Fig 5) / Agent Task Queue (Fig 4).

Lifecycle of a request (spec 5.1-5.3):
  submit()  -> ServiceRequest + first AgentTask (queued)
  run_task() -> agent.execute_task() -> handle the AgentStatus:
     OK               next pipeline step, or finish (Coordinator consolidates, contract check)
     TRIGGER_REPLAN   like OK, but planning.revise_plan is inserted once per request
     NEEDS_INPUT      request waits; reply() hands the user's answer back to the same task type
     NEEDS_ESCALATION / AWAITING_APPROVAL   EscalationManager opens a case; nothing runs until a human decides
     FAILED           request fails with the agent's reason code
  An OK result whose confidence is below AGENT_CONFIDENCE_THRESHOLD is treated as NEEDS_ESCALATION:
  one escalation policy for every agent (spec 6.1, NFR-02).

AGENT_TASK_EXECUTION=inline runs the queue inside the HTTP request (default, the frontend reads
results synchronously); `worker` only enqueues and `manage.py run_agent_worker` executes.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from agents.runtime import AgentResult, AgentStatus, RequestContext, TaskInput
from domain.common import AGENT_NAMES, DomainError, trace_context
from domain.governance import selectors as governance
from domain.governance import services as gov
from domain.governance.models import AgentTask, ServiceRequest
from infrastructure.monitoring import log_event

from . import contracts, pipelines, registry
from .registry import AgentNotImplemented

ORCHESTRATOR = "task_queue"
TaskStatus = AgentTask.Status
RequestStatus = ServiceRequest.Status
PAUSED = (RequestStatus.AWAITING_INPUT, RequestStatus.ESCALATED, RequestStatus.AWAITING_APPROVAL)


def inline() -> bool:
    return settings.AGENT_TASK_EXECUTION == "inline"


# --- entry points -------------------------------------------------------------------------
def submit(request_type: str, *, actor: Any, actor_role: str, student: Any = None, input: dict | None = None, context_id: str = "") -> ServiceRequest:
    """Create a request and its first task. Preconditions are checked before anything is queued."""
    pipeline = pipelines.get(request_type)
    try:
        data = contracts.validate_input(request_type, input or {})
    except contracts.ContractError as exc:
        raise DomainError("invalid_input", str(exc), status=400) from exc
    if pipeline.precheck and student is not None:
        pipeline.precheck(student, data)
    request = gov.create_request(
        ORCHESTRATOR,
        type=request_type,
        requester=actor,
        actor_role=actor_role,
        student=student,
        context_id=context_id or "",
        input=data,
        remaining_steps=list(pipeline.steps[1:]),
    )
    with trace_context(request_id=str(request.pk)):
        if pipeline.steps:
            _enqueue(request, pipeline.steps[0], payload={"input": data, "context_id": context_id or ""})
    return _maybe_drain(request)


def reply(request: ServiceRequest, *, input: dict) -> ServiceRequest:
    """Hand the user's answer back to the task that asked (NEEDS_INPUT), without re-classifying."""
    if request.status != RequestStatus.AWAITING_INPUT:
        raise DomainError("request_not_awaiting_input", "This request is not waiting for an answer.")
    waiting = governance.awaiting_task(request)
    if waiting is None:
        raise DomainError("request_not_awaiting_input", "This request is not waiting for an answer.")
    with trace_context(request_id=str(request.pk)):
        gov.transition_task(ORCHESTRATOR, waiting, TaskStatus.SUCCEEDED)
        payload = {**waiting.payload, "reply": input, "previous": waiting.result}
        _enqueue(request, waiting.task_type, payload=payload, parent=waiting, hops=waiting.hops)
        gov.transition_request(ORCHESTRATOR, request, RequestStatus.QUEUED)
    return _maybe_drain(request)


def resume_after_decision(
    *,
    origin: AgentTask | None,
    resume_task_type: str,
    decision: dict,
    by: Any,
    student: Any = None,
    reference: str = "",
    subject_id: str = "",
) -> ServiceRequest | None:
    """Continue the flow a human decision unblocked (called by the EscalationManager).

    The resume task joins the paused request when there is one; otherwise it starts a
    `decision_follow_up` request. Without a resume task the paused request simply completes.
    """
    request = origin.request if origin is not None else None
    if not resume_task_type:
        if request is not None and request.status in PAUSED:
            with trace_context(request_id=str(request.pk)):
                gov.transition_request(ORCHESTRATOR, request, RequestStatus.COMPLETED, phase="decided")
        return request
    payload = {
        **(origin.payload if origin else {}),
        "decision": {**decision, "decided_by": str(by.pk)},
        "case_id": reference,
        "subject_id": subject_id,
    }
    if request is None or request.status not in PAUSED:
        request = gov.create_request(
            ORCHESTRATOR,
            type="decision_follow_up",
            requester=by,
            actor_role=_role(by),
            student=student,
            context_id=reference,
            input={"case_id": reference, "decision": decision},
        )
    with trace_context(request_id=str(request.pk)):
        _enqueue(request, resume_task_type, payload=payload, parent=origin, hops=origin.hops if origin else 0)
        gov.transition_request(ORCHESTRATOR, request, RequestStatus.QUEUED)
    return _maybe_drain(request)


def start_follow_up(request_type: str, *, actor: Any, payload: dict, student: Any = None) -> ServiceRequest:
    """Internal request started by a human decision (e.g. Founder asks for an agent correction)."""
    return submit(request_type, actor=actor, actor_role=_role(actor), student=student, input=payload)


# --- execution ------------------------------------------------------------------------------
def drain(request: ServiceRequest, *, max_tasks: int = 50) -> None:
    for _ in range(max_tasks):
        task = governance.next_queued_task(request)
        if task is None:
            return
        run_task(task)


def run_next() -> bool:
    """Worker step: run the oldest queued task of any request. Returns False when idle."""
    task = governance.next_queued_task()
    if task is None:
        return False
    run_task(task)
    return True


def run_task(task: AgentTask) -> None:
    request = task.request
    with trace_context(request_id=str(request.pk) if request else None, task_id=str(task.pk)):
        now = timezone.now()
        gov.transition_task(
            ORCHESTRATOR,
            task,
            TaskStatus.RUNNING,
            started_at=now,
            deadline_at=now + timedelta(seconds=settings.TASK_TIMEOUT_SECONDS),
            attempts=task.attempts + 1,
        )
        if request is not None and request.status != RequestStatus.RUNNING:
            gov.transition_request(ORCHESTRATOR, request, RequestStatus.RUNNING)

        agent_id = task.target_agent
        state = governance.agent_state(agent_id)
        if state is not None and state.status == "paused":
            return _fail(task, "agent_paused", f"{AGENT_NAMES.get(agent_id, agent_id)} is paused by the Founder.")
        try:
            agent_cls = registry.load_agent_class(agent_id)
        except AgentNotImplemented:
            return _fail(task, "agent_not_implemented", f"The {agent_id} agent is not implemented yet ({task.task_type}).")
        except Exception as exc:
            log_event("agent_import_failed", level=logging.ERROR, exc_info=True, agent=agent_id)
            return _fail(task, "unhandled_exception", f"{type(exc).__name__}: {exc}")
        if task.task_type not in agent_cls.task_types:
            return _fail(task, "unknown_task_type", f"{agent_id} does not handle {task.task_type}.")

        task_input = _task_input(task)
        runtime = registry.build_runtime(agent_cls, task_input)
        try:
            result = agent_cls(runtime).execute_task(task_input)
        except Exception as exc:  # spec 5.2: the Orchestrator is the safety net, agents never swallow errors
            log_event("agent_exception", level=logging.ERROR, exc_info=True, task_type=task.task_type)
            return _fail(task, "unhandled_exception", f"{type(exc).__name__}: {exc}", trace=runtime.trace)
        if not isinstance(result, AgentResult):
            return _fail(task, "invalid_agent_result", "execute_task must return an AgentResult.", trace=runtime.trace)
        _handle(task, result, runtime.trace)


def recover_stuck(now=None) -> int:
    """Re-queue or fail running tasks past their deadline (spec 8.5). Also cleans up after a crash."""
    count = 0
    for task in governance.stuck_tasks(now):
        with trace_context(request_id=str(task.request_id) if task.request_id else None, task_id=str(task.pk)):
            if task.attempts < settings.TASK_MAX_ATTEMPTS:
                gov.transition_task(ORCHESTRATOR, task, TaskStatus.QUEUED, reason="task_timeout_retry")
            else:
                _fail(task, "task_timeout", "The task did not finish in time.")
        count += 1
    return count


# --- status handling ----------------------------------------------------------------------------
def _handle(task: AgentTask, result: AgentResult, runtime_trace: list) -> None:
    from orchestration.escalation.manager import escalation_manager

    status = result.status
    payload = dict(result.payload or {})
    reason = result.reason or ""
    if status == AgentStatus.OK and escalation_manager.is_below_threshold(result.confidence):
        status, reason = AgentStatus.NEEDS_ESCALATION, reason or "low_confidence"
    record = {"result": payload, "confidence": result.confidence, "reason": reason, "trace": [*runtime_trace, *result.trace]}
    request = task.request

    if status in (AgentStatus.OK, AgentStatus.TRIGGER_REPLAN):
        gov.transition_task(ORCHESTRATOR, task, TaskStatus.SUCCEEDED, **record)
        if status == AgentStatus.TRIGGER_REPLAN and request is not None:
            _insert_replan(request)
        _advance(task)
    elif status == AgentStatus.NEEDS_INPUT:
        gov.transition_task(ORCHESTRATOR, task, TaskStatus.NEEDS_INPUT, **record)
        _pause(task, RequestStatus.AWAITING_INPUT)
    elif status in (AgentStatus.NEEDS_ESCALATION, AgentStatus.AWAITING_APPROVAL):
        approval = status == AgentStatus.AWAITING_APPROVAL
        record["reason"] = reason or ("approval_required" if approval else "escalation_requested")
        gov.transition_task(ORCHESTRATOR, task, TaskStatus.AWAITING_APPROVAL if approval else TaskStatus.ESCALATED, **record)
        case = escalation_manager.create_case(task, kind="approval" if approval else "review")
        _pause(task, RequestStatus.AWAITING_APPROVAL if approval else RequestStatus.ESCALATED, case=case)
    else:
        message = str(payload.get("message") or reason or "The agent could not complete the task.")
        gov.transition_task(ORCHESTRATOR, task, TaskStatus.FAILED, **{**record, "reason": reason or "agent_failed"})
        _fail_request(request, reason or "agent_failed", message)


def _insert_replan(request: ServiceRequest) -> None:
    if request.replans >= 1:
        gov.record_audit(ORCHESTRATOR, "request.replan_suppressed", request)
        return
    gov.update_request(ORCHESTRATOR, request, remaining_steps=[pipelines.REPLAN_TASK, *request.remaining_steps], replans=request.replans + 1)
    gov.record_audit(ORCHESTRATOR, "request.replan_triggered", request)


def _advance(task: AgentTask) -> None:
    request = task.request
    if request is None:
        return
    remaining = list(request.remaining_steps)
    if not remaining:
        return _finish(request, task)
    if request.hops + 1 > settings.MAX_HOPS_PER_REQUEST:
        return _fail_request(request, "max_hops_exceeded", "The request needed too many agent hand-offs.")
    next_type = remaining.pop(0)
    gov.update_request(ORCHESTRATOR, request, remaining_steps=remaining, hops=request.hops + 1)
    _enqueue(
        request,
        next_type,
        payload={"input": request.input, "context_id": request.context_id, "upstream": task.result.get("result", {}), "upstream_data": task.result},
        parent=task,
        hops=task.hops + 1,
    )


def _finish(request: ServiceRequest, last: AgentTask) -> None:
    result = _consolidate(request, RequestStatus.COMPLETED, last)
    if result is None:
        return
    try:
        contracts.validate_result(request.type, result)
    except contracts.ContractError as exc:
        return _fail_request(request, "invalid_result", f"Result does not match the {request.type} contract: {exc}")
    phase = str((last.result or {}).get("phase") or "completed")
    gov.transition_request(ORCHESTRATOR, request, RequestStatus.COMPLETED, result=result, phase=phase, error=None)


def _pause(task: AgentTask, status: str, *, case: Any = None) -> None:
    request = task.request
    if request is None:
        return
    result = _consolidate(request, status, task)
    if result is None:
        return
    if case is not None and isinstance(result, dict):
        result.setdefault("review_id", str(case.pk))
        plan = result.get("plan")
        if isinstance(plan, dict) and not plan.get("review_id"):
            plan["review_id"] = str(case.pk)
    try:
        contracts.validate_result(request.type, result, awaiting_input=status == RequestStatus.AWAITING_INPUT)
    except contracts.ContractError as exc:
        return _fail_request(request, "invalid_result", f"Result does not match the {request.type} contract: {exc}")
    phase = str((task.result or {}).get("phase") or {RequestStatus.AWAITING_INPUT: "awaiting_input"}.get(status, status))
    gov.transition_request(ORCHESTRATOR, request, status, result=result, phase=phase)


def _consolidate(request: ServiceRequest, status: str, last: AgentTask) -> dict | None:
    """Coordinator.consolidate_response() when implemented; otherwise the user-facing parts
    (payload["result"]) of every non-failed task in the request, merged in order."""
    default: dict = {}
    for done in governance.tasks_for(request):
        if done.status != TaskStatus.FAILED and done.status != TaskStatus.QUEUED:
            default.update((done.result or {}).get("result") or {})
    try:
        coordinator_cls = registry.load_agent_class("coordinator")
    except AgentNotImplemented:
        return default
    except Exception as exc:
        _fail_request(request, "unhandled_exception", f"Coordinator import failed: {exc}")
        return None
    consolidate = getattr(coordinator_cls, "consolidate_response", None)
    if consolidate is None:
        return default
    task_input = _task_input(last)
    try:
        coordinator = coordinator_cls(registry.build_runtime(coordinator_cls, task_input))
        results = [t.result for t in governance.tasks_for(request) if t.status != TaskStatus.FAILED]
        return coordinator.consolidate_response(request_type=request.type, status=str(status), results=results)
    except Exception as exc:
        log_event("consolidate_failed", level=logging.ERROR, exc_info=True, request_type=request.type)
        _fail_request(request, "unhandled_exception", f"consolidate_response failed: {exc}")
        return None


def _fail(task: AgentTask, code: str, message: str, *, trace: list | None = None) -> None:
    gov.transition_task(ORCHESTRATOR, task, TaskStatus.FAILED, reason=code, result={"message": message}, trace=trace or task.trace)
    _fail_request(task.request, code, message)


def _fail_request(request: ServiceRequest | None, code: str, message: str) -> None:
    if request is None or request.status == RequestStatus.FAILED:
        return
    for leftover in request.tasks.filter(status=TaskStatus.QUEUED):
        gov.transition_task(ORCHESTRATOR, leftover, TaskStatus.FAILED, reason="request_failed")
    gov.transition_request(ORCHESTRATOR, request, RequestStatus.FAILED, error={"code": code, "message": message}, phase="failed")


# --- helpers ----------------------------------------------------------------------------------------
def _enqueue(request: ServiceRequest, task_type: str, *, payload: dict, parent: AgentTask | None = None, hops: int = 0) -> AgentTask:
    return gov.create_task(
        ORCHESTRATOR,
        request=request,
        task_type=task_type,
        target_agent=pipelines.target_agent(task_type),
        student=request.student,
        payload=payload,
        parent=parent,
        hops=hops,
    )


def _maybe_drain(request: ServiceRequest) -> ServiceRequest:
    if inline():
        drain(request)
    request.refresh_from_db()
    return request


def _task_input(task: AgentTask) -> TaskInput:
    request = task.request
    return TaskInput(
        task_id=str(task.pk),
        task_type=task.task_type,
        student_id=str(task.student_id) if task.student_id else None,
        payload=task.payload or {},
        ctx=RequestContext(
            request_id=str(request.pk) if request else "",
            actor_id=str(request.actor_id) if request and request.actor_id else "system",
            actor_role=(request.actor_role if request else "system") or "system",
            hops=task.hops,
        ),
    )


def _role(user: Any) -> str:
    from domain.common import role_of

    return role_of(user) or "system"
