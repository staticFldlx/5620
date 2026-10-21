"""Planning business rules and integration with the real dispatcher/review manager."""
from dataclasses import replace
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError
from django.utils import timezone

from access_control.identity.models import User
from agents.planning.agent import PlanningAgent
from agents.planning.schemas import PlanDraft
from agents.runtime import AgentStatus, RequestContext, TaskInput
from agents.runtime.testing import make_runtime
from domain.governance.models import EscalationCase
from domain.learning import selectors as learning, services
from domain.learning.models import Course, LearningPlan, PlanStage
from orchestration.escalation.manager import escalation_manager
from orchestration.task_queue import dispatcher
from tests.conftest import key

pytestmark = pytest.mark.django_db


@pytest.fixture
def learner():
    student = User.objects.create_user(username="planning-student", email="planning@example.com", name="Learner")
    student.groups.add(Group.objects.get(name="student"))
    teacher = User.objects.get(pk=key("teacher-emily"))
    services.replace_availability(teacher, teacher, windows=[
        {"day": d, "start": "09:00", "end": "18:00"} for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    ], tz="Australia/Sydney")
    services.create_profile("coordinator", student=student, learning_goal="Write academic arguments",
        structured_objective={"summary": "Write evidence-based arguments", "focus_skills": ["Writing"], "target_level": "C1"},
        preferences={"weekly_hours": 4, "timezone": "Australia/Sydney", "availability": [
            {"day": d, "start": "09:00", "end": "18:00"} for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        ]})
    session = services.create_assessment_session("assessment", student=student, type="initial", status="completed")
    services.record_proficiency("assessment", session=session, overall_level="B2", weak_areas=["Writing"],
        gap_to_goal="Needs evidence links", status="confirmed", confidence=0.9)
    return student


def draft():
    return {"weekly_hours": 4, "rationale": "Build foundations before evidence-based writing to address the confirmed writing gap.",
        "stages": [
            {"title": "Academic foundations", "topics": ["Paragraph structure"], "milestone": "Identify the claim in three paragraphs",
             "start_week": 1, "end_week": 2, "course_codes": ["CAT-01"]},
            {"title": "Evidence links", "topics": ["Evidence and commentary"], "milestone": "Write an argument with three supported claims",
             "start_week": 3, "end_week": 4, "course_codes": ["CAT-02"]},
        ]}


def task(student, name="generate_plan", **payload):
    return TaskInput("planning-task", "planning." + name, str(student.pk), {"input": {}, **payload},
        RequestContext("planning-request", str(student.pk), "student"))


def agent(output=None):
    return PlanningAgent(make_runtime([draft() if output is None else output]))


def test_generation_is_personalised_grounded_and_pending(learner):
    consultant = agent()
    result = consultant.execute_task(task(learner))
    assert result.status == AgentStatus.AWAITING_APPROVAL
    plan = learning.pending_plan(learner)
    assert plan.status == "pending_review" and plan.approved_at is None
    assert plan.teacher_id == key("teacher-emily") or str(plan.teacher_id) == key("teacher-emily")
    assert plan.based_on.status == "confirmed"
    assert [s.courses.get().code for s in learning.plan_stages(plan)] == ["CAT-01", "CAT-02"]
    assert result.payload["resume"] == "planning.activate_plan"
    assert not learning.lessons_for_student(learner).exists()
    assert any(s.get("name") == "planning_catalogue" for s in consultant.runtime.trace)
    assert learning.history(learner).get().payload["proposed_slots"]


@pytest.mark.parametrize("change", ["unknown", "prerequisite", "hours", "weeks", "empty"])
def test_invalid_business_constraints_never_persist(learner, change):
    output = draft()
    if change == "unknown":
        output["stages"][0]["course_codes"] = ["MADE-UP"]
    elif change == "prerequisite":
        output["stages"] = [output["stages"][1]]
        output["stages"][0]["start_week"] = 1
    elif change == "hours":
        output["weekly_hours"] = 5
    elif change == "weeks":
        output["stages"][1]["start_week"] = 2
    else:
        output["stages"][0]["course_codes"] = []
    result = agent(output).execute_task(task(learner))
    assert result.reason == "invalid_curriculum"
    assert not LearningPlan.objects.filter(student=learner).exists()


def test_invalid_llm_json_is_retried_and_rejected(learner):
    consultant = PlanningAgent(make_runtime(["invalid", "still invalid"]))
    assert consultant.execute_task(task(learner)).reason == "invalid_llm_output"
    assert not learning.pending_plan(learner)


def test_missing_profile_and_confirmed_assessment(learner):
    learner.learning_profile.delete()
    assert agent().execute_task(task(learner)).reason == "profile_missing"


def test_pending_assessment_cannot_be_used(learner):
    assessment = learning.latest_confirmed_proficiency(learner)
    services.update_proficiency("assessment", assessment, status="pending_review")
    assert agent().execute_task(task(learner)).reason == "assessment_missing"


def test_no_teacher_routes_to_founder(learner, settings):
    settings.INTAKE_TEACHER_EMAIL = "missing@example.com"
    result = agent().execute_task(task(learner))
    assert result.reason == "teacher_unavailable"
    assert result.payload["route_to"] == "founder"
    assert result.payload["resume"] == "planning.generate_plan"


def test_no_catalogue_escalates_after_widening(learner):
    Course.objects.all().delete()
    result = agent().execute_task(task(learner))
    assert result.reason == "catalogue_insufficient"


def test_no_overlap_returns_conflict_checked_alternatives(learner):
    services.update_profile("coordinator", learner.learning_profile, preferences={"availability": []})
    result = agent().execute_task(task(learner))
    assert result.status == AgentStatus.NEEDS_INPUT
    assert result.payload["result"]["slots"]
    assert not learning.pending_plan(learner)


def test_retry_reuses_draft(learner):
    first = agent().execute_task(task(learner))
    second = agent().execute_task(task(learner))
    assert first.payload["subject_id"] == second.payload["subject_id"]
    assert LearningPlan.objects.filter(student=learner).count() == 1


def test_forged_approval_is_rejected(learner):
    result = agent().execute_task(task(learner))
    resumed = task(learner, "activate_plan", subject_id=result.payload["subject_id"],
        decision={"action": "approve", "note": "Forged", "decided_by": key("teacher-emily")})
    assert agent().execute_task(resumed).reason == "invalid_human_decision"
    assert learning.active_plan(learner) is None


@pytest.fixture
def real_runtime(monkeypatch):
    from orchestration.task_queue import registry
    monkeypatch.setattr(registry, "build_runtime", lambda cls, task: make_runtime([draft()]))


def review_request(learner):
    # Initial creation is normally the second step of start_assessment.
    from domain.governance import services as gov
    request = gov.create_request("task_queue", type="decision_follow_up", requester=learner,
        actor_role="student", student=learner, input={})
    queued = gov.create_task("task_queue", request=request, task_type="planning.generate_plan", target_agent="planning",
        student=learner, payload={"input": {}})
    dispatcher.run_task(queued)
    request.refresh_from_db()
    return request


def approve(case):
    return escalation_manager.decide_review(case, action="approve", note="Approved after reviewing the curriculum.", by=case.assignee)


def test_real_dispatcher_review_activation_and_duplicate_decision(learner, real_runtime):
    request = review_request(learner)
    assert request.status == "awaiting_approval"
    case = EscalationCase.objects.get(task__request=request)
    assert str(case.assignee_id) == key("teacher-emily")
    approve(case)
    plan = learning.active_plan(learner)
    assert plan is not None and plan.approved_by_id == case.assignee_id
    assert learning.lessons_for_student(learner).count() == 2
    request.refresh_from_db()
    assert request.status == "completed", request.error
    case.refresh_from_db()
    repeated = task(learner, "activate_plan", case_id=str(case.pk), subject_id=str(plan.pk),
        decision={**case.decision, "decided_by": str(case.resolved_by_id)})
    assert agent().execute_task(repeated).status == AgentStatus.OK
    assert learning.lessons_for_student(learner).count() == 2


def test_teacher_changes_generate_new_review_not_activation(learner, real_runtime):
    request = review_request(learner)
    case = EscalationCase.objects.get(task__request=request)
    escalation_manager.decide_review(case, action="request_changes", note="Slow down and add remedial writing.", by=case.assignee)
    assert learning.active_plan(learner) is None
    plans = list(LearningPlan.objects.filter(student=learner).order_by("version"))
    assert [p.status for p in plans] == ["changes_requested", "pending_review"]
    assert plans[1].previous_version_id == plans[0].pk
    assert "Slow down" in plans[1].rationale
    assert EscalationCase.objects.filter(student=learner, status="open").count() == 1


def test_revision_preserves_active_version_until_approval(learner, real_runtime):
    request = review_request(learner)
    approve(EscalationCase.objects.get(task__request=request))
    old = learning.active_plan(learner)
    request = dispatcher.submit("revise_plan", actor=learner, actor_role="student", student=learner,
        input={"reason": "Need slower pace", "requested_change": "More writing practice"})
    assert request.status == "awaiting_approval", request.error
    assert learning.active_plan(learner).pk == old.pk
    approve(EscalationCase.objects.get(task__request=request))
    old.refresh_from_db()
    assert old.status == "superseded"
    assert learning.active_plan(learner).previous_version_id == old.pk


def test_failed_create_rolls_back_all_stages(learner, monkeypatch):
    original = services.create_plan
    def broken(*args, **kwargs):
        original(*args, **kwargs)
        raise DatabaseError("simulated storage failure")
    monkeypatch.setattr(services, "create_plan", broken)
    result = agent().execute_task(task(learner))
    assert result.reason == "plan_update_failed"
    assert not LearningPlan.objects.filter(student=learner).exists()
    assert not PlanStage.objects.filter(plan__student=learner).exists()


def test_other_students_cannot_read_or_modify(learner):
    request = task(learner)
    request = replace(request, ctx=replace(request.ctx, actor_id=key("student-ivy")))
    assert agent().execute_task(request).reason == "forbidden"


def test_reschedule_requires_confirmation_and_rechecks_conflicts(learner, real_runtime):
    request = review_request(learner)
    approve(EscalationCase.objects.get(task__request=request))
    lesson = learning.lessons_for_student(learner).first()
    start = lesson.starts_at + timedelta(days=1)
    proposal = agent().execute_task(task(learner, "propose_slot", input={"lesson_id": str(lesson.pk), "slot": start.isoformat()}))
    assert proposal.status == AgentStatus.NEEDS_INPUT
    lesson.refresh_from_db()
    assert lesson.starts_at != start
    services.book_lesson("planning", teacher=lesson.teacher, student=learner, starts_at=start,
        ends_at=start + timedelta(hours=1), title="New conflicting booking", status="confirmed")
    result = agent().execute_task(task(learner, "book_slot", input={"lesson_id": str(lesson.pk), "slot": start.isoformat()}))
    assert result.reason == "slot_conflict"
    result = agent().execute_task(task(learner, "book_slot", input={"lesson_id": str(lesson.pk), "slot": (start + timedelta(hours=2)).isoformat()}))
    assert result.status == AgentStatus.OK


def test_draft_schema_rejects_nonfinite_hours():
    from pydantic import ValidationError
    output = draft()
    output["weekly_hours"] = float("inf")
    with pytest.raises(ValidationError):
        PlanDraft.model_validate(output)


def test_llm_outage_is_reported_without_saving(learner):
    consultant = PlanningAgent(make_runtime([]))
    assert consultant.execute_task(task(learner)).reason == "llm_unavailable"
    assert not learning.pending_plan(learner)


def test_unassigned_teacher_cannot_revise(learner):
    request = task(learner, "revise_plan", input={"reason": "Manual teacher change"})
    request = replace(request, ctx=replace(request.ctx, actor_id=key("teacher-emily"), actor_role="teacher"))
    assert agent().execute_task(request).reason == "forbidden"


def test_failed_activation_rolls_back_plan_and_booking(learner, real_runtime, monkeypatch):
    request = review_request(learner)
    case = EscalationCase.objects.get(task__request=request)
    def broken(*args, **kwargs):
        raise DatabaseError("simulated lesson write failure")
    monkeypatch.setattr(services, "book_lesson", broken)
    approve(case)
    request.refresh_from_db()
    assert request.status == "failed"
    assert request.error["code"] == "plan_update_failed"
    assert learning.pending_plan(learner).status == "pending_review"
    assert learning.active_plan(learner) is None
    assert not learning.lessons_for_student(learner).exists()


def test_alternative_confirmation_continues_generation_and_review(learner, real_runtime):
    services.update_profile("coordinator", learner.learning_profile, preferences={"availability": []})
    request = review_request(learner)
    assert request.status == "awaiting_input"
    waiting = request.tasks.get()
    selected = waiting.result["result"]["slots"][0]
    dispatcher.reply(request, input={"slot_id": selected["id"]})
    request.refresh_from_db()
    assert request.status == "awaiting_approval", request.error
    approve(EscalationCase.objects.get(task__request=request))
    assert learning.active_plan(learner)


def test_founder_case_continues_after_teacher_becomes_available(learner, real_runtime, settings):
    settings.INTAKE_TEACHER_EMAIL = "missing@example.com"
    request = review_request(learner)
    case = EscalationCase.objects.get(task__request=request)
    assert case.subject_type == "business"
    assert str(case.assignee_id) == key("founder-alex")
    settings.INTAKE_TEACHER_EMAIL = "emily.walker@example.com"
    escalation_manager.decide_business_case(case, action="request_teacher", note="A suitable intake teacher is now available.", by=case.assignee)
    request.refresh_from_db()
    assert request.status == "awaiting_approval", request.error


def test_real_fake_provider_hook_can_generate_without_test_runtime_patch(learner):
    request = review_request(learner)
    assert request.status == "awaiting_approval", request.error
    assert learning.pending_plan(learner).stages.exists()


def test_changed_prerequisites_prevent_activation(learner, real_runtime):
    request = review_request(learner)
    Course.objects.get(code="CAT-01").prerequisites.add(Course.objects.get(code="WORK-1"))
    approve(EscalationCase.objects.get(task__request=request))
    request.refresh_from_db()
    assert request.status == "failed"
    assert learning.active_plan(learner) is None


def test_failed_revision_preserves_active_version(learner, real_runtime, monkeypatch):
    request = review_request(learner)
    approve(EscalationCase.objects.get(task__request=request))
    original = learning.active_plan(learner)
    def broken(*args, **kwargs):
        raise DatabaseError("write failed")
    monkeypatch.setattr(services, "create_plan", broken)
    request = dispatcher.submit("revise_plan", actor=learner, actor_role="student", student=learner,
        input={"reason": "More remedial practice"})
    assert request.status == "failed"
    assert learning.active_plan(learner).pk == original.pk
    assert LearningPlan.objects.filter(student=learner).count() == 1
