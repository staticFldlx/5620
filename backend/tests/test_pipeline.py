"""Task Orchestrator + EscalationManager integration (inline mode) with test-double agents."""

from datetime import timedelta

import pytest
from django.utils import timezone

from access_control.identity.models import User
from agents.runtime import AgentResult, AgentStatus
from domain.governance import services as gov
from domain.governance.models import AgentTask, EscalationCase, ServiceRequest
from domain.learning import selectors as learning
from domain.learning import services as learning_services
from domain.learning.views import interaction_view, plan_view
from orchestration.escalation import escalation_manager
from orchestration.task_queue import dispatcher
from tests.conftest import key

pytestmark = pytest.mark.django_db


def user(name: str) -> User:
    return User.objects.get(pk=key(name))


def ok(result: dict, confidence: float | None = 0.9, **control) -> AgentResult:
    return AgentResult(AgentStatus.OK, {"result": result, **control}, confidence=confidence)


def explain_handler(confidence: float):
    def handler(task, runtime):
        student = User.objects.get(pk=task.student_id)
        entry = learning_services.append_history(
            "teaching_support",
            student=student,
            kind="explain",
            payload={"question": task.payload["input"]["question"], "answer": "Use a because bridge.", "source_refs": []},
            confidence=confidence,
            escalated=confidence < 0.7,
        )
        control = {"subject_type": "question", "subject_id": str(entry.pk), "trigger": "Insufficient source evidence"}
        return ok({"interaction": interaction_view(entry)}, confidence=confidence, **control)

    return handler


def submit(request_type: str, actor_name: str = "student-ivy", student_name: str | None = "student-ivy", **input):
    actor = user(actor_name)
    role = "teacher" if actor_name.startswith("teacher") else "student"
    return dispatcher.submit(request_type, actor=actor, actor_role=role, student=user(student_name) if student_name else None, input=input)


def test_ok_result_completes_and_matches_the_contract(stubs):
    stubs["teaching_support.answer_question"] = explain_handler(0.9)
    request = submit("explain", question="How do I link evidence?")
    assert request.status == ServiceRequest.Status.COMPLETED
    assert request.result["interaction"]["question"] == "How do I link evidence?"
    task = request.tasks.get()
    assert task.status == AgentTask.Status.SUCCEEDED and task.confidence == 0.9


def test_missing_agent_fails_with_agent_not_implemented(settings):
    settings.AGENT_REGISTRY = {**settings.AGENT_REGISTRY, "teaching_support": "agents.missing.agent.MissingAgent"}
    request = submit("explain", question="?")
    assert request.status == ServiceRequest.Status.FAILED
    assert request.error["code"] == "agent_not_implemented"


def test_result_that_breaks_the_contract_fails_the_request(stubs):
    stubs["teaching_support.answer_question"] = lambda task, rt: ok({"answer": "missing interaction"})
    request = submit("explain", question="?")
    assert request.error["code"] == "invalid_result"


def test_low_confidence_ok_is_escalated_to_the_students_teacher(stubs):
    stubs["teaching_support.answer_question"] = explain_handler(0.41)
    request = submit("explain", question="May I cite an unpublished recording?")
    assert request.status == ServiceRequest.Status.ESCALATED
    case = EscalationCase.objects.get(task__request=request)
    assert case.assignee == user("teacher-emily") and case.subject_type == "question"
    assert case.trigger == "Insufficient source evidence" and case.confidence == 0.41
    assert request.result["review_id"] == str(case.pk)
    # the teacher answers; no resume task, so the request completes and the answer is overlaid
    escalation_manager.decide_review(case, action="answer", note="Ask the lecturer for permission first.", by=user("teacher-emily"))
    request.refresh_from_db()
    assert request.status == ServiceRequest.Status.COMPLETED
    entry = learning.history_entry(case.subject_id)
    case.refresh_from_db()
    view = interaction_view(entry, case=case)
    assert view["answer"] == "Ask the lecturer for permission first." and view["status"] == "completed"


def test_student_without_teacher_goes_to_intake_teacher(stubs, settings):
    from access_control.identity import services as identity

    newcomer = identity.register_student(name="New", email="new@example.com", password="password1")
    assert escalation_manager.assignee_for("assessment", newcomer) == user("teacher-emily")
    settings.INTAKE_TEACHER_EMAIL = ""
    assert escalation_manager.assignee_for("assessment", newcomer) == user("founder-alex")
    assert escalation_manager.assignee_for("business", user("student-ivy")) == user("founder-alex")


def plan_revision(task, runtime):
    student = User.objects.get(pk=task.student_id)
    active = learning.active_plan(student)
    stages = [{"title": s.title, "topics": s.topics, "milestone": s.milestone, "status": s.status} for s in learning.plan_stages(active)]
    draft = learning_services.create_plan(
        "planning",
        student=student,
        stages=stages,
        teacher=active.teacher,
        version=active.version + 1,
        previous_version=active,
        status="pending_review",
        weekly_hours=active.weekly_hours,
        rationale=task.payload["input"]["reason"],
    )
    payload = {"result": {"plan": plan_view(draft)}, "subject_type": "plan", "subject_id": str(draft.pk), "resume": "planning.activate_plan"}
    return AgentResult(AgentStatus.AWAITING_APPROVAL, payload, confidence=0.86, reason="major_revision")


def activate(task, runtime):
    decision = task.payload["decision"]
    plan = learning.plan(task.payload["subject_id"])
    if decision["action"] == "approve":
        learning_services.activate_plan("planning", plan, approved_by=User.objects.get(pk=decision["decided_by"]))
    else:
        learning_services.update_plan("planning", plan, status="changes_requested")
    return ok({"plan": plan_view(learning.plan(plan.pk))}, confidence=None)


def test_approval_pauses_then_teacher_approval_resumes_the_same_request(stubs):
    sophia = user("student-sophia")
    # give Sophia an active plan first (approve the fixture's pending one)
    learning_services.activate_plan("planning", learning.pending_plan(sophia), approved_by=user("teacher-emily"))
    stubs["planning.revise_plan"] = plan_revision
    stubs["planning.activate_plan"] = activate
    request = submit("revise_plan", actor_name="student-sophia", student_name="student-sophia", reason="More speaking")
    assert request.status == ServiceRequest.Status.AWAITING_APPROVAL
    case = EscalationCase.objects.get(task__request=request)
    assert case.kind == "approval" and case.assignee == user("teacher-emily")
    assert request.result["plan"]["review_id"] == str(case.pk)
    escalation_manager.decide_review(case, action="approve", note="Matches the goal", by=user("teacher-emily"))
    request.refresh_from_db()
    assert request.status == ServiceRequest.Status.COMPLETED
    assert learning.active_plan(sophia).rationale == "More speaking"
    assert request.tasks.count() == 2


def test_review_actions_are_checked_per_subject(stubs):
    case = EscalationCase.objects.get(pk=key("RV-021"))
    from domain.common import DomainError

    with pytest.raises(DomainError):
        escalation_manager.decide_review(case, action="answer", note="x", by=user("teacher-emily"))
    with pytest.raises(DomainError):
        escalation_manager.decide_review(case, action="approve", note="  ", by=user("teacher-emily"))


def test_needs_input_waits_and_reply_resumes_with_previous_state(stubs):
    def collect(task, runtime):
        if "reply" not in task.payload:
            return AgentResult(AgentStatus.NEEDS_INPUT, {"result": {"question": "Which exam?"}, "phase": "follow_up_question", "asked": 1})
        assert task.payload["previous"]["asked"] == 1
        return ok({"summary": f"Prepare for {task.payload['reply']['answer']}", "focus_skills": ["Writing"]}, confidence=None)

    stubs["coordinator.collect_goal"] = collect
    request = submit("collect_goal", goal_text="I need English for an exam")
    assert (request.status, request.phase, request.result) == ("awaiting_input", "follow_up_question", {"question": "Which exam?"})
    request = dispatcher.reply(request, input={"answer": "IELTS"})
    assert request.status == ServiceRequest.Status.COMPLETED
    assert request.result["summary"] == "Prepare for IELTS"


def test_trigger_replan_inserts_one_revision_and_hops_are_limited(stubs, settings):
    stubs["assessment.conduct_assessment"] = lambda task, rt: ok({"session_id": "s-1"}, confidence=0.9)
    stubs["planning.generate_plan"] = lambda task, rt: AgentResult(AgentStatus.TRIGGER_REPLAN, {"result": {}}, reason="milestone_deviation")
    stubs["planning.revise_plan"] = lambda task, rt: ok({}, confidence=None)
    request = submit("start_assessment", kind="milestone")
    assert request.status == ServiceRequest.Status.COMPLETED
    assert list(request.tasks.values_list("task_type", flat=True)) == [
        "assessment.conduct_assessment",
        "planning.generate_plan",
        "planning.revise_plan",
    ]
    assert request.replans == 1

    settings.MAX_HOPS_PER_REQUEST = 1
    request = submit("start_assessment", kind="milestone")
    assert request.error["code"] == "max_hops_exceeded"


def test_paused_agent_and_unhandled_exception_fail_the_task(stubs):
    def crash(task, runtime):
        raise ValueError("bug")

    stubs["teaching_support.answer_question"] = crash
    request = submit("explain", question="?")
    assert request.error["code"] == "unhandled_exception"
    gov.set_agent_state(user("founder-alex"), "teaching_support", status="paused", note="abnormal output")
    request = submit("explain", question="?")
    assert request.error["code"] == "agent_paused"


def test_worker_mode_queues_and_worker_runs(stubs, settings):
    settings.AGENT_TASK_EXECUTION = "worker"
    stubs["teaching_support.answer_question"] = explain_handler(0.9)
    request = submit("explain", question="queued?")
    assert request.status == ServiceRequest.Status.QUEUED
    assert dispatcher.run_next() is True
    request.refresh_from_db()
    assert request.status == ServiceRequest.Status.COMPLETED


def test_stuck_tasks_are_retried_then_failed(stubs, settings):
    settings.AGENT_TASK_EXECUTION = "worker"
    request = submit("explain", question="slow")
    task = request.tasks.get()
    past = timezone.now() - timedelta(minutes=5)
    gov.transition_task("task_queue", task, AgentTask.Status.RUNNING, started_at=past, deadline_at=past, attempts=1)
    assert dispatcher.recover_stuck() == 1
    task.refresh_from_db()
    assert task.status == AgentTask.Status.QUEUED
    gov.transition_task("task_queue", task, AgentTask.Status.RUNNING, deadline_at=past, attempts=2)
    dispatcher.recover_stuck()
    request.refresh_from_db()
    assert request.error["code"] == "task_timeout"


def test_coordinator_consolidate_response_shapes_the_final_reply(stubs):
    from tests import stub_agents

    stubs["teaching_support.answer_question"] = explain_handler(0.9)
    stub_agents.CoordinatorStub.consolidate_response = lambda self, request_type, status, results: {**results[-1]["result"], "note": "consolidated"}
    try:
        request = submit("explain", question="?")
    finally:
        del stub_agents.CoordinatorStub.consolidate_response
    assert request.result["note"] == "consolidated"


def test_proposal_approval_is_version_bound_and_starts_execution(stubs):
    from domain.common import DomainError
    from domain.governance.models import UpdateProposal

    proposal = UpdateProposal.objects.get(pk=key("UP-08"))
    with pytest.raises(DomainError):
        escalation_manager.decide_proposal(proposal, approve=True, note="", by=user("founder-alex"), version=99)
    stubs["tech_operations.execute_proposal"] = lambda task, rt: ok({"executed": task.payload["decision"]["proposal_id"]}, confidence=None)
    follow_up = escalation_manager.decide_proposal(proposal, approve=True, note="go", by=user("founder-alex"), version=1)
    proposal.refresh_from_db()
    assert proposal.status == "approved" and proposal.decided_by == user("founder-alex")
    assert follow_up.status == ServiceRequest.Status.COMPLETED and follow_up.result["executed"] == str(proposal.pk)
