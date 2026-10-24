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


@pytest.mark.parametrize("change", ["unknown", "hours", "weeks", "empty"])
def test_invalid_business_constraints_never_persist(learner, change):
    output = draft()
    if change == "unknown":
        output["stages"][0]["course_codes"] = ["MADE-UP"]
    elif change == "hours":
        output["weekly_hours"] = 5
    elif change == "weeks":
        output["stages"][1]["start_week"] = 2
    else:
        output["stages"][0]["course_codes"] = []
    result = agent(output).execute_task(task(learner))
    assert result.reason == "invalid_curriculum"
    assert not LearningPlan.objects.filter(student=learner).exists()


def out_of_order():
    output = draft()  # CAT-02 needs CAT-01 in an earlier stage
    output["stages"][0]["course_codes"], output["stages"][1]["course_codes"] = ["CAT-02"], ["CAT-01"]
    return output


def test_curriculum_error_is_fed_back_once_and_the_corrected_draft_is_used(learner):
    consultant = PlanningAgent(make_runtime([out_of_order(), draft()]))
    result = consultant.execute_task(task(learner))
    assert result.status == AgentStatus.AWAITING_APPROVAL
    assert [s.courses.get().code for s in learning.plan_stages(learning.pending_plan(learner))] == ["CAT-01", "CAT-02"]
    rejected = next(s for s in consultant.runtime.trace if s.get("decision") == "invalid_curriculum")
    assert rejected["stage_courses"] == [["CAT-02"], ["CAT-01"]] and rejected["error"].endswith("CAT-02")
    assert "CAT-02" in consultant.runtime.adapter.calls[-1]["messages"][-1].content


def test_repeated_prerequisite_error_is_repaired_before_teacher_review(learner):
    consultant = PlanningAgent(make_runtime([out_of_order(), out_of_order()]))
    assert consultant.execute_task(task(learner)).status == AgentStatus.AWAITING_APPROVAL
    assert [s.courses.get().code for s in learning.plan_stages(learning.pending_plan(learner))] == ["CAT-01", "CAT-02"]
    assert [s["attempt"] for s in consultant.runtime.trace if s.get("decision") == "invalid_curriculum"] == [1, 2]
    assert any(s.get("decision") == "curriculum_repaired" for s in consultant.runtime.trace)


def test_missing_prerequisite_is_added_before_teacher_review(learner):
    output = draft()
    output["stages"] = [{**output["stages"][1], "start_week": 1, "end_week": 2}]
    consultant = PlanningAgent(make_runtime([output, output]))
    assert consultant.execute_task(task(learner)).status == AgentStatus.AWAITING_APPROVAL
    assert [s.courses.get().code for s in learning.plan_stages(learning.pending_plan(learner))] == ["CAT-01", "CAT-02"]


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
    User.objects.filter(groups__name="teacher").update(is_active=False)
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


def test_generate_plan_waits_for_a_draft_already_in_review(learner):
    """A later assessment (another task) does not fail while the first draft is with the teacher."""
    first = agent().execute_task(task(learner))
    later = replace(task(learner), task_id="later-assessment-task")
    result = PlanningAgent(make_runtime([])).execute_task(later)  # no LLM call
    assert result.status == AgentStatus.OK
    assert result.payload["result"]["plan"]["id"] == first.payload["subject_id"]
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
    dispatcher.drain(request)
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


def test_student_can_retry_plan_after_confirmed_assessment(learner, real_runtime):
    request = dispatcher.submit("request_plan", actor=learner, actor_role="student", student=learner, input={})
    assert request.status == "awaiting_approval", request.error
    assert learning.pending_plan(learner) is not None
    case = EscalationCase.objects.get(task__request=request)
    approve(case)
    assert learning.active_plan(learner) is not None
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
    User.objects.filter(groups__name="teacher").update(is_active=False)
    request = review_request(learner)
    case = EscalationCase.objects.get(task__request=request)
    assert case.subject_type == "business"
    assert str(case.assignee_id) == key("founder-alex")
    settings.INTAKE_TEACHER_EMAIL = "emily.walker@example.com"
    User.objects.filter(pk=key("teacher-emily")).update(is_active=True)
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


def teacher_candidate(name, *, available=True, subjects=None):
    from access_control.identity.models import TeacherProfile
    teacher = User.objects.create_user(username=name, email=name + "@example.com", name=name)
    teacher.groups.add(Group.objects.get(name="teacher"))
    TeacherProfile.objects.create(user=teacher, subject_areas=subjects or ["Academic Writing"], timezone="Australia/Sydney")
    if available:
        services.replace_availability(teacher, teacher, windows=[
            {"day": d, "start": "09:00", "end": "18:00"} for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        ], tz="Australia/Sydney")
    return teacher


def active_for(student, teacher):
    from agents.planning.agent import validate_curriculum
    stages = validate_curriculum(PlanDraft.model_validate(draft()), {c.code: c for c in learning.courses()}, 4)
    plan = services.create_plan("planning", student=student, teacher=teacher, stages=stages,
        based_on=learning.latest_confirmed_proficiency(student), weekly_hours=4, rationale="Existing approved plan")
    return services.activate_plan("planning", plan, approved_by=teacher)


def resolved_activation(student, *, action="approve"):
    from domain.governance import services as gov
    request = review_request(student)
    case = EscalationCase.objects.get(task__request=request)
    gov.resolve_case("escalation_manager", case, decision={"action": action, "note": "Reviewed curriculum"}, by=case.assignee)
    resumed = task(student, "activate_plan", case_id=str(case.pk), subject_id=case.subject_id,
        decision={**case.decision, "decided_by": str(case.resolved_by_id)})
    return case, resumed


@pytest.mark.parametrize("action", ["approve", "request_changes"])
def test_missing_latest_case_is_controlled_for_both_decisions(learner, real_runtime, monkeypatch, action):
    from domain.governance import selectors as governance
    _, resumed = resolved_activation(learner, action=action)
    monkeypatch.setattr(governance, "latest_case_for", lambda *args: None)
    assert agent().execute_task(resumed).reason == "invalid_human_decision"
    assert learning.pending_plan(learner).status == "pending_review"


@pytest.mark.parametrize("action", ["approve", "request_changes"])
def test_newer_case_supersedes_both_old_decisions(learner, real_runtime, action):
    from domain.governance import services as gov
    case, resumed = resolved_activation(learner, action=action)
    gov.create_case("escalation_manager", task=case.task, kind="approval", trigger="Review again",
        student=learner, subject_type="plan", subject_id=case.subject_id, assignee=case.assignee)
    assert agent().execute_task(resumed).reason == "invalid_human_decision"
    assert learning.active_plan(learner) is None


def test_null_stored_decision_is_controlled(learner, real_runtime):
    case, resumed = resolved_activation(learner)
    EscalationCase.objects.filter(pk=case.pk).update(decision=None)
    assert agent().execute_task(resumed).reason == "invalid_human_decision"


def test_wrong_teacher_cannot_approve_even_if_case_assigned_to_them(learner, real_runtime):
    case, resumed = resolved_activation(learner)
    other = teacher_candidate("unassigned-reviewer")
    EscalationCase.objects.filter(pk=case.pk).update(assignee=other, resolved_by=other)
    resumed = replace(resumed, payload={**resumed.payload, "decision": {**resumed.payload["decision"], "decided_by": str(other.pk)}})
    assert agent().execute_task(resumed).reason == "invalid_human_decision"


def test_outdated_plan_approval_cannot_replace_newer_active_plan(learner, real_runtime):
    case, resumed = resolved_activation(learner)
    old = learning.plan(case.subject_id)
    newer = services.create_plan("planning", student=learner, teacher=old.teacher, stages=[], version=old.version + 1,
        weekly_hours=4, rationale="Newer approved version")
    services.activate_plan("planning", newer, approved_by=old.teacher)
    assert agent().execute_task(resumed).reason == "stale_plan"
    assert learning.active_plan(learner).pk == newer.pk
    assert not learning.lessons_for_student(learner).exists()


def test_matching_skips_unavailable_current_teacher_and_tries_intake(learner):
    current = teacher_candidate("busy-current", available=False)
    active_for(learner, current)
    result = agent().execute_task(task(learner, "revise_plan", input={"reason": "Need available teacher"}))
    assert result.status == AgentStatus.AWAITING_APPROVAL
    assert str(learning.pending_plan(learner).teacher_id) == key("teacher-emily")


def test_extra_qualified_teacher_is_discovered_in_shared_catalogue(learner, settings):
    User.objects.filter(pk=key("teacher-emily")).update(is_active=False)
    candidate = teacher_candidate("qualified-outside-selectors")
    settings.INTAKE_TEACHER_EMAIL = "missing@example.com"
    result = agent().execute_task(task(learner))
    assert result.status == AgentStatus.AWAITING_APPROVAL
    assert learning.pending_plan(learner).teacher_id == candidate.pk


def test_replacement_without_existing_bookings_activates_new_teacher(learner, real_runtime):
    old_teacher = teacher_candidate("old-without-bookings")
    old = active_for(learner, old_teacher)
    request = dispatcher.submit("replace_teacher", actor=learner, actor_role="student", student=learner)
    assert request.status == "awaiting_approval", request.error
    pending = learning.pending_plan(learner)
    assert pending.teacher_id != old_teacher.pk
    approve(EscalationCase.objects.get(task__request=request))
    request.refresh_from_db()
    assert request.status == "completed", request.error
    assert learning.active_plan(learner).pk == pending.pk
    old.refresh_from_db()
    assert old.status == "superseded"
    assert all(lesson.teacher_id == pending.teacher_id for lesson in learning.lessons_for_student(learner))
    case = EscalationCase.objects.get(task__request=request)
    replay = task(learner, "activate_plan", case_id=str(case.pk), subject_id=case.subject_id,
        decision={**case.decision, "decided_by": str(case.resolved_by_id)})
    assert agent().execute_task(replay).status == AgentStatus.OK
    assert learning.lessons_for_student(learner).count() == 2


def test_replacement_with_existing_future_bookings_is_blocked_without_writes(learner, real_runtime):
    request = review_request(learner)
    approve(EscalationCase.objects.get(task__request=request))
    old = learning.active_plan(learner)
    bookings = list(learning.lessons_for_student(learner).values("id", "teacher_id", "starts_at", "ends_at", "status"))
    request = dispatcher.submit("replace_teacher", actor=learner, actor_role="student", student=learner)
    assert request.status == "failed"
    assert request.error["code"] == "teacher_reassignment_unavailable"
    assert learning.active_plan(learner).pk == old.pk
    assert learning.pending_plan(learner) is None
    assert list(learning.lessons_for_student(learner).values("id", "teacher_id", "starts_at", "ends_at", "status")) == bookings


def test_replacement_failure_rolls_back_active_version_and_new_bookings(learner, real_runtime, monkeypatch):
    old = active_for(learner, teacher_candidate("replacement-rollback"))
    request = dispatcher.submit("replace_teacher", actor=learner, actor_role="student", student=learner)
    def broken(*args, **kwargs):
        raise DatabaseError("failed reassignment booking")
    monkeypatch.setattr(services, "book_lesson", broken)
    approve(EscalationCase.objects.get(task__request=request))
    request.refresh_from_db()
    assert request.error["code"] == "plan_update_failed"
    assert learning.active_plan(learner).pk == old.pk
    assert not learning.lessons_for_student(learner).exists()


def test_founder_widen_match_changes_subject_criteria(learner, real_runtime, alex):
    services.update_profile("coordinator", learner.learning_profile, learning_goal="Medical communication",
        structured_objective={"summary": "Medical communication", "focus_skills": ["Medical"]})
    request = review_request(learner)
    case = EscalationCase.objects.get(task__request=request)
    assert case.subject_type == "business"
    detail = alex.get(f"/cases/{case.pk}")
    assert "widen_match" in detail.json()["available_actions"]
    response = alex.post(f"/cases/{case.pk}/decision", {"action": "widen_match", "note": "Allow the intake teacher to review this broader goal."})
    assert response.status_code == 200
    assert response.json()["follow_up"]["status"] == "pending_review"
    request.refresh_from_db()
    assert request.status == "awaiting_approval", request.error
    assert "broader goal" in learning.pending_plan(learner).rationale


def test_founder_request_teacher_without_updated_data_does_not_loop(learner, real_runtime, settings):
    settings.INTAKE_TEACHER_EMAIL = "missing@example.com"
    User.objects.filter(groups__name="teacher").update(is_active=False)
    request = review_request(learner)
    case = EscalationCase.objects.get(task__request=request)
    escalation_manager.decide_business_case(case, action="request_teacher", note="Please recruit a teacher.", by=case.assignee)
    request.refresh_from_db()
    assert request.status == "failed"
    assert request.error["code"] == "teacher_catalogue_update_required"
    assert EscalationCase.objects.filter(task__request=request).count() == 1


def test_reply_slot_id_overrides_original_requested_time(learner, real_runtime):
    request = review_request(learner)
    approve(EscalationCase.objects.get(task__request=request))
    lesson = learning.lessons_for_student(learner).first()
    requested = lesson.starts_at + timedelta(days=1)
    alternative = requested + timedelta(hours=2)
    result = agent().execute_task(task(learner, "propose_slot",
        input={"lesson_id": str(lesson.pk), "slot": requested.isoformat()},
        reply={"slot_id": alternative.isoformat()}))
    assert result.status == AgentStatus.OK
    lesson.refresh_from_db()
    assert lesson.starts_at == alternative


def test_slot_request_reference_and_all_external_planning_contracts(learner, real_runtime):
    from orchestration.task_queue import contracts
    request = review_request(learner)
    approve(EscalationCase.objects.get(task__request=request))
    lesson = learning.lessons_for_student(learner).first()
    proposed = dispatcher.submit("reschedule", actor=learner, actor_role="student", student=learner,
        input={"lesson_id": str(lesson.pk), "slot": (lesson.starts_at + timedelta(days=1)).isoformat()})
    contracts.validate_result("reschedule", proposed.result, awaiting_input=True)
    from access_control.gateway import presenters
    assert presenters.plan_choice_record(learner) is None  # a lesson reschedule is answered on /s5, not the plan page
    confirmed = dispatcher.submit("confirm_slot", actor=learner, actor_role="student", student=learner,
        input={"slot_request_id": str(proposed.pk), "slot_id": proposed.result["slots"][0]["id"]})
    assert confirmed.status == "completed", confirmed.error
    contracts.validate_result("confirm_slot", confirmed.result)


def test_pending_review_contract_and_control_metadata_are_not_double_wrapped(learner, real_runtime):
    from orchestration.task_queue import contracts
    request = review_request(learner)
    case = EscalationCase.objects.get(task__request=request)
    stored = case.task.result
    assert stored["subject_id"] == str(learning.pending_plan(learner).pk)
    assert stored["resume"] == case.resume_task_type == "planning.activate_plan"
    assert case.subject_id == stored["subject_id"]
    contracts.validate_result("revise_plan", request.result)
    assert request.result["review_id"] == request.result["plan"]["review_id"] == str(case.pk)


def test_schedule_rechecks_student_preferences_at_every_stage(learner):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    # Sydney leaves DST between stage 1 and stage 2; UTC learner's hours do not move.
    services.update_profile("coordinator", learner.learning_profile, preferences={"timezone": "UTC",
        "availability": [{"day": "Sat", "start": "22:00", "end": "23:00"}]})
    first = datetime(2027, 3, 28, 9, tzinfo=ZoneInfo("Australia/Sydney"))
    from agents.planning.agent import slot_view
    consultant = agent()
    teacher = User.objects.get(pk=key("teacher-emily"))
    stages = [{"start_week": 1}, {"start_week": 3}]
    assert consultant._choose_schedule(teacher, learner, stages, [slot_view(first, first + timedelta(hours=1))]) is None


def test_second_stage_conflict_tries_another_schedule(learner):
    consultant = agent()
    teacher = User.objects.get(pk=key("teacher-emily"))
    slots = consultant._slots(teacher, learner, learner.learning_profile)
    from datetime import datetime
    first = datetime.fromisoformat(slots[0]["starts_at"])
    services.book_lesson("planning", teacher=teacher, student=learner, title="Stage two conflict",
        starts_at=first + timedelta(weeks=2), ends_at=first + timedelta(weeks=2, hours=1), status="confirmed")
    schedule = consultant._choose_schedule(teacher, learner, [{"start_week": 1}, {"start_week": 3}], slots)
    assert schedule is not None
    assert schedule[0]["starts_at"] != slots[0]["starts_at"]


def test_fake_selects_relevant_courses_and_prerequisite_closure(learner):
    request = review_request(learner)
    assert request.status == "awaiting_approval", request.error
    codes = [s.courses.get().code for s in learning.plan_stages(learning.pending_plan(learner))]
    assert codes == ["CAT-01", "CAT-02"]


@pytest.mark.parametrize("kind", ["empty", "unsuitable", "cycle", "large"])
def test_fake_handles_catalogue_edge_cases_without_invalid_week_ranges(kind):
    import json
    from agents.planning.fake import script
    from agents.runtime import Message
    courses = []
    if kind == "unsuitable":
        courses = [{"code": "X", "title": "Unrelated", "skill": "Speaking", "level": "B2", "prerequisites": []}]
    if kind == "cycle":
        courses = [{"code": "X", "title": "Writing", "skill": "Writing", "level": "B2", "prerequisites": ["X"]}]
    if kind == "large":
        courses = [{"code": f"W-{i:03}", "title": "Writing", "skill": "Writing", "level": "B2", "prerequisites": []} for i in range(70)]
    context = {"catalogue": {"courses": courses}, "profile": {"weekly_hours": 4, "focus_skills": ["Writing"],
        "goal_summary": "Writing", "goal_text": "Writing", "target_level": "C1"},
        "assessment": {"weaknesses": ["Writing"], "level": "B2", "gap": "Writing"}}
    output = script(None)[0](messages=[Message(role="user", content=json.dumps(context))])
    if kind == "large":
        assert len(PlanDraft.model_validate(output).stages) == 52
        assert output["stages"][-1]["end_week"] == 104
    else:
        assert output["stages"] == []


def assessment_to_planning(student, record):
    """Exercise the real second pipeline step with a persisted confirmed assessment."""
    from domain.governance import services as gov
    request = gov.create_request("task_queue", type="start_assessment", requester=student,
        actor_role="student", student=student, input={"kind": "initial"})
    upstream = gov.create_task("task_queue", request=request, task_type="assessment.conduct_assessment",
        target_agent="assessment", student=student, payload={"input": {}})
    gov.transition_task("task_queue", upstream, "succeeded", result={"result": {"session_id": str(record.session_id)}})
    queued = gov.create_task("task_queue", request=request, task_type="planning.generate_plan", target_agent="planning",
        student=student, parent=upstream, payload={"input": request.input, "upstream": upstream.result["result"], "upstream_data": upstream.result})
    dispatcher.run_task(queued)
    dispatcher.drain(request)
    request.refresh_from_db()
    return request


def test_initial_assessment_pipeline_preserves_session_contract_when_paused(learner, real_runtime):
    from orchestration.task_queue import contracts
    record = learning.latest_confirmed_proficiency(learner)
    request = assessment_to_planning(learner, record)
    assert request.status == "awaiting_approval", request.error
    contracts.validate_result("start_assessment", request.result)
    assert request.result["session_id"] == str(record.session_id)
    approve(EscalationCase.objects.get(task__request=request))
    request.refresh_from_db()
    assert request.status == "completed", request.error
    contracts.validate_result("start_assessment", request.result)


def test_student_picks_plan_time_when_availability_does_not_overlap(learner, real_runtime, client):
    from access_control.gateway import presenters
    from access_control.identity.permissions import assigned_student_ids
    from tests.conftest import Api
    teacher = User.objects.get(pk=key("teacher-emily"))
    services.update_profile("coordinator", learner.learning_profile, preferences={"availability": []})
    request = assessment_to_planning(learner, learning.latest_confirmed_proficiency(learner))
    assert request.status == "awaiting_input", request.error
    choice = presenters.plan_choice_record(learner)
    assert choice["request_id"] == str(request.pk) and choice["request_type"] == "start_assessment" and choice["slots"]
    assert learner.pk in assigned_student_ids(teacher)  # the draft already names Emily
    learner.set_password("longenough")
    learner.save()
    student = Api(client).login("planning@example.com", "longenough")
    assert student.get("/workspace").json()["plan_choice"]["request_id"] == str(request.pk)
    response = student.post("/requests", {"type": "start_assessment", "context_id": choice["request_id"],
        "input": {"slot": choice["slots"][0]["id"]}})
    assert response.status_code == 200, response.content
    plan = learning.pending_plan(learner)
    assert plan is not None and plan.teacher_id == teacher.pk
    assert presenters.plan_choice_record(learner) is None
    assert EscalationCase.objects.filter(task__request=request, assignee=teacher, status="open").exists()


def test_automatic_replan_uses_shared_dispatcher_and_keeps_assessment_contract(learner, real_runtime):
    teacher = User.objects.get(pk=key("teacher-emily"))
    old = active_for(learner, teacher)
    session = services.create_assessment_session("assessment", student=learner, type="milestone", status="completed")
    new_record = services.record_proficiency("assessment", session=session, overall_level="B1", weak_areas=["Writing"],
        status="confirmed", confidence=0.9, gap_to_goal="Writing still needs support")
    request = assessment_to_planning(learner, new_record)
    assert request.status == "awaiting_approval", request.error
    assert request.replans == 1
    assert list(request.tasks.values_list("task_type", flat=True)) == [
        "assessment.conduct_assessment", "planning.generate_plan", "planning.revise_plan"]
    assert learning.active_plan(learner).pk == old.pk
    assert learning.pending_plan(learner).based_on_id == new_record.pk
    approve(EscalationCase.objects.get(task__request=request))
    request.refresh_from_db()
    assert request.status == "completed", request.error
    assert request.result["session_id"] == str(session.pk)


@pytest.mark.parametrize("action", ["approve", "request_changes"])
def test_teacher_review_api_runs_real_resumption(learner, real_runtime, emily, action):
    request = review_request(learner)
    case = EscalationCase.objects.get(task__request=request)
    response = emily.post(f"/reviews/{case.pk}/decision", {"action": action, "note": "Teacher reviewed this plan"})
    assert response.status_code == 200, response.content
    assert response.json()["follow_up"]["status"] == ("completed" if action == "approve" else "pending_review")
    assert bool(learning.active_plan(learner)) == (action == "approve")


def test_manual_teacher_revision_and_correction_can_activate(learner, real_runtime):
    original = active_for(learner, User.objects.get(pk=key("teacher-emily")))
    request = dispatcher.submit("revise_plan", actor=original.teacher, actor_role="teacher", student=learner,
        input={"reason": "Teacher reviewed progress", "requested_change": "Add remedial paragraphs"})
    case = EscalationCase.objects.get(task__request=request)
    escalation_manager.decide_review(case, action="request_changes", note="Add more remediation", by=case.assignee)
    corrected = learning.pending_plan(learner)
    assert corrected.status == "pending_review"
    approve(EscalationCase.objects.get(student=learner, status="open"))
    request.refresh_from_db()
    assert request.status == "completed", request.error
    assert learning.active_plan(learner).pk == corrected.pk
    original.refresh_from_db()
    assert original.status == "superseded"


def test_upstream_recommendation_and_evidence_reach_model_and_review(learner, monkeypatch):
    import json
    active_for(learner, User.objects.get(pk=key("teacher-emily")))
    consultant = agent()
    result = consultant.execute_task(task(learner, "revise_plan", upstream={"recommendation": "Add evidence practice"},
        upstream_data={"evidence": [{"ref": "progress-1", "summary": "Two weak paragraphs"}]}))
    assert result.status == AgentStatus.AWAITING_APPROVAL
    context = json.loads(consultant.runtime.adapter.calls[0]["messages"][0].content)
    assert context["upstream_recommendation"]["recommendation"] == "Add evidence practice"
    assert result.payload["evidence"][-1] == {"ref": "progress-1", "summary": "Two weak paragraphs"}


def test_changed_preferences_do_not_silently_reuse_unconfirmed_draft_slots(learner, real_runtime):
    case, resumed = resolved_activation(learner)
    services.update_profile("coordinator", learner.learning_profile, preferences={"availability": []})
    result = agent().execute_task(resumed)
    assert result.status == AgentStatus.NEEDS_INPUT
    assert learning.active_plan(learner) is None


@pytest.mark.parametrize("status", ["pending_review", "changes_requested"])
def test_pending_selector_excludes_versions_replaced_by_active_plan(learner, status):
    teacher = User.objects.get(pk=key("teacher-emily"))
    old = services.create_plan("planning", student=learner, teacher=teacher, stages=[], version=1,
        status=status, weekly_hours=4, rationale="Historical draft")
    current = services.create_plan("planning", student=learner, teacher=teacher, stages=[], version=2,
        previous_version=old, weekly_hours=4, rationale="Approved replacement")
    services.activate_plan("planning", current, approved_by=teacher)
    assert learning.pending_plan(learner) is None
    old.refresh_from_db()
    assert old.status == status  # Selecting the current draft must not rewrite history.
    assert learning.plan(old.pk) is not None


@pytest.mark.parametrize("status", ["pending_review", "changes_requested"])
def test_pending_selector_keeps_newer_drafts_and_blocks_duplicate_revision(learner, status):
    from domain.common import DomainError
    teacher = User.objects.get(pk=key("teacher-emily"))
    current = active_for(learner, teacher)
    newer = services.create_plan("planning", student=learner, teacher=teacher, stages=[], version=current.version + 1,
        previous_version=current, status=status, weekly_hours=4, rationale="Unfinished revision")
    assert learning.pending_plan(learner).pk == newer.pk
    with pytest.raises(DomainError) as error:
        dispatcher.submit("revise_plan", actor=learner, actor_role="student", student=learner,
            input={"reason": "Duplicate revision"})
    assert error.value.code == "plan_review_pending"
    assert learning.active_plan(learner).pk == current.pk


@pytest.mark.parametrize("status", ["pending_review", "changes_requested"])
def test_pending_selector_keeps_first_plan_without_active_version(learner, status):
    initial = services.create_plan("planning", student=learner, teacher=User.objects.get(pk=key("teacher-emily")),
        stages=[], version=1, status=status, weekly_hours=4, rationale="First plan")
    assert learning.active_plan(learner) is None
    assert learning.pending_plan(learner).pk == initial.pk


@pytest.mark.parametrize("mode", ["inline", "worker"])
def test_corrected_plan_activation_allows_next_revision_through_api(learner, real_runtime, emily, settings, mode):
    from django.test import Client
    from domain.governance.models import ServiceRequest
    from tests.conftest import Api
    settings.AGENT_TASK_EXECUTION = mode
    learner.set_password("demo1238")
    learner.save(update_fields=["password"])
    student_api = Api(Client()).login(learner.email)

    def decide(case, action, note):
        response = emily.post(f"/reviews/{case.pk}/decision", {"action": action, "note": note})
        assert response.status_code == 200, response.content
        follow_up = response.json().get("follow_up")
        if follow_up and follow_up["status"] in ("queued", "running"):
            dispatcher.drain(ServiceRequest.objects.get(pk=follow_up["id"]))
        return response

    initial_request = review_request(learner)
    original_case = EscalationCase.objects.get(task__request=initial_request)
    decide(original_case, "request_changes", "Add clearer writing practice.")
    corrected = learning.pending_plan(learner)
    assert corrected.version == 2
    corrected_case = EscalationCase.objects.get(student=learner, subject_id=str(corrected.pk), status="open")
    decide(corrected_case, "approve", "The corrected plan is approved.")
    assert learning.active_plan(learner).pk == corrected.pk

    before = student_api.get("/workspace").json()["students"][str(learner.pk)]
    assert before["plan"]["version"] == 2
    assert before["pending_plan"] is None
    assert not EscalationCase.objects.filter(student=learner, status="open").exists()

    response = student_api.post("/requests", {"type": "revise_plan", "input": {"reason": "More guided reading within my weekly budget."}})
    assert response.status_code == 200, response.content
    assert response.json()["status"] == ("queued" if mode == "worker" else "pending_review")
    revision_request = ServiceRequest.objects.get(pk=response.json()["id"])
    dispatcher.drain(revision_request)
    revision_request.refresh_from_db()
    assert revision_request.status == "awaiting_approval", revision_request.error
    newer = learning.pending_plan(learner)
    assert newer.version == 3 and newer.previous_version_id == corrected.pk
    assert learning.active_plan(learner).pk == corrected.pk
    pending_workspace = student_api.get("/workspace").json()["students"][str(learner.pk)]
    assert pending_workspace["pending_plan"]["version"] == 3

    repeated = student_api.post("/requests", {"type": "revise_plan", "input": {"reason": "Another revision too soon"}})
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "plan_review_pending"
    assert LearningPlan.objects.filter(student=learner).count() == 3

    decide(EscalationCase.objects.get(task__request=revision_request), "approve", "Approve version three.")
    assert learning.active_plan(learner).pk == newer.pk
    assert learning.pending_plan(learner) is None
    corrected.refresh_from_db()
    assert corrected.status == "superseded"
    historical = LearningPlan.objects.get(student=learner, version=1)
    assert historical.status == "changes_requested"
    original_case.refresh_from_db()
    assert original_case.status == "resolved" and original_case.decision["action"] == "request_changes"


@pytest.fixture
def student_revision(learner, real_runtime):
    from django.test import Client
    from tests.conftest import Api
    learner.set_password("demo1238")
    learner.save(update_fields=["password"])
    api = Api(Client()).login(learner.email)
    initial = review_request(learner)
    approve(EscalationCase.objects.get(task__request=initial))
    current = learning.active_plan(learner)
    request = dispatcher.submit("revise_plan", actor=learner, actor_role="student", student=learner,
        input={"reason": "More reading practice, keeping my existing weekly hours."})
    plan = learning.pending_plan(learner)
    case = EscalationCase.objects.get(subject_id=str(plan.pk), status="open")
    return api, current, plan, case, request


@pytest.mark.parametrize("mode", ["inline", "worker"])
def test_student_withdraws_revision_then_submits_again(student_revision, learner, emily, settings, mode):
    from domain.common import DomainError
    api, current, plan, case, request = student_revision
    settings.AGENT_TASK_EXECUTION = mode
    record = api.get("/workspace").json()["students"][str(learner.pk)]
    details = record["pending_plan"]["revision_request"]
    assert details["reason"] == request.input["reason"]
    assert details["can_withdraw"] and details["submitted_at"]
    assert api.post("/requests", {"type": "revise_plan", "input": {"reason": "Duplicate"}}).status_code == 409
    lessons_before = list(learning.lessons_for_student(learner).values("id", "status", "starts_at", "ends_at"))
    response = api.post(f"/plans/{plan.pk}/withdraw")
    assert list(learning.lessons_for_student(learner).values("id", "status", "starts_at", "ends_at")) == lessons_before
    assert response.status_code == 200, response.content
    assert response.json() == {"withdrawn": True}
    assert learning.active_plan(learner).pk == current.pk
    assert learning.pending_plan(learner) is None
    plan.refresh_from_db()
    request.refresh_from_db()
    assert plan.status == "withdrawn"
    assert request.status == "completed" and request.phase == "withdrawn"
    assert request.remaining_steps == []
    # An already-open teacher tab holds this stale model instance.
    with pytest.raises(DomainError) as error:
        escalation_manager.decide_review(case, action="approve", note="Stale approval", by=case.assignee)
    assert error.value.code == "case_not_open"
    assert emily.post(f"/reviews/{case.pk}/decision", {"action": "approve", "note": "Stale approval"}).status_code == 409
    assert api.post(f"/plans/{plan.pk}/withdraw").status_code == 409
    assert learning.history(learner, kinds=("plan_revision_withdrawn",)).count() == 1
    next_request = dispatcher.submit("revise_plan", actor=learner, actor_role="student", student=learner,
        input={"reason": "A revised request after withdrawal"})
    dispatcher.drain(next_request)
    assert learning.pending_plan(learner).version == plan.version + 1
    assert learning.active_plan(learner).pk == current.pk


def test_withdrawal_cannot_touch_other_student_or_approved_plan(student_revision, learner, ivy, emily):
    api, current, plan, case, request = student_revision
    assert ivy.post(f"/plans/{plan.pk}/withdraw").status_code == 403
    assert emily.post(f"/plans/{plan.pk}/withdraw").status_code == 403
    assert api.post(f"/plans/{current.pk}/withdraw").status_code == 409
    approve(case)
    assert api.post(f"/plans/{plan.pk}/withdraw").status_code == 409
    assert learning.active_plan(learner).pk == plan.pk


def test_corrected_student_revision_can_be_withdrawn_without_old_draft_reappearing(student_revision, learner):
    api, current, plan, case, request = student_revision
    escalation_manager.decide_review(case, action="request_changes", note="Clarify the milestones", by=case.assignee)
    corrected = learning.pending_plan(learner)
    assert corrected.version == plan.version + 1
    details = api.get("/workspace").json()["students"][str(learner.pk)]["pending_plan"]["revision_request"]
    assert details["can_withdraw"] and details["reason"] == request.input["reason"]
    assert api.post(f"/plans/{corrected.pk}/withdraw").status_code == 200
    assert learning.pending_plan(learner) is None
    assert learning.active_plan(learner).pk == current.pk
    plan.refresh_from_db()
    assert plan.status == "withdrawn"
    case.refresh_from_db()
    assert case.decision["action"] == "request_changes"  # decision history remains intact


def test_initial_plan_cannot_be_withdrawn(learner, real_runtime):
    from orchestration.escalation.plan_revisions import withdraw_revision
    from domain.common import DomainError
    review_request(learner)
    plan = learning.pending_plan(learner)
    with pytest.raises(DomainError) as error:
        withdraw_revision(plan, by=learner)
    assert error.value.code == "revision_not_withdrawable"
    assert learning.pending_plan(learner).pk == plan.pk


def test_withdrawal_failure_rolls_back_every_change(student_revision, learner, monkeypatch):
    from orchestration.escalation.plan_revisions import withdraw_revision
    api, current, plan, case, request = student_revision
    def fail(*args, **kwargs):
        raise RuntimeError("Simulated history failure")
    monkeypatch.setattr(services, "append_history", fail)
    with pytest.raises(RuntimeError):
        withdraw_revision(plan, by=learner)
    case.refresh_from_db()
    plan.refresh_from_db()
    request.refresh_from_db()
    assert case.status == "open" and case.decision is None
    assert plan.status == "pending_review" and request.status == "awaiting_approval"
    assert learning.active_plan(learner).pk == current.pk


def test_student_cannot_withdraw_teacher_initiated_revision(student_revision, learner):
    api, current, plan, case, request = student_revision
    assert api.post(f"/plans/{plan.pk}/withdraw").status_code == 200
    teacher = current.teacher
    dispatcher.submit("revise_plan", actor=teacher, actor_role="teacher", student=learner,
        input={"reason": "Teacher initiated improvement"})
    proposed = learning.pending_plan(learner)
    details = api.get("/workspace").json()["students"][str(learner.pk)]["pending_plan"]["revision_request"]
    assert not details["can_withdraw"]
    assert api.post(f"/plans/{proposed.pk}/withdraw").status_code == 409
    assert learning.pending_plan(learner).pk == proposed.pk


@pytest.fixture
def scheduled_learner(learner, real_runtime):
    request = review_request(learner)
    approve(EscalationCase.objects.get(task__request=request))
    return learning.lessons_for_student(learner).first()


@pytest.mark.parametrize("mode", ["inline", "worker"])
def test_empty_time_finds_slots_and_confirm_uses_selected_offer(learner, scheduled_learner, settings, mode):
    settings.AGENT_TASK_EXECUTION = mode
    lesson = scheduled_learner
    before = lesson.starts_at
    request = dispatcher.submit("reschedule", actor=learner, actor_role="student", student=learner,
        input={"lesson_id": str(lesson.pk)})
    dispatcher.drain(request); request.refresh_from_db()
    assert request.status == "awaiting_input", request.error
    assert request.result["requested_available"] is False
    assert request.result["teacher_availability"]
    slots = request.result["slots"]
    assert slots and all(s["starts_at"] != before.isoformat() for s in slots)
    lesson.refresh_from_db(); assert lesson.starts_at == before
    selected = slots[-1]
    confirmation = dispatcher.submit("confirm_slot", actor=learner, actor_role="student", student=learner,
        input={"lesson_id": str(lesson.pk), "slot_request_id": str(request.pk), "slot_id": selected["id"]})
    dispatcher.drain(confirmation); confirmation.refresh_from_db()
    assert confirmation.status == "completed", confirmation.error
    from datetime import datetime
    lesson.refresh_from_db()
    assert lesson.starts_at == datetime.fromisoformat(selected["starts_at"])


def test_unavailable_time_returns_reason_and_options_and_valid_time_is_accepted(learner, scheduled_learner):
    from datetime import datetime
    lesson = scheduled_learner
    from zoneinfo import ZoneInfo
    invalid = (timezone.now().astimezone(ZoneInfo("Australia/Sydney")) + timedelta(days=2)).replace(hour=0).isoformat()
    # Invalid ISO input also produces a useful choice instead of crashing.
    for value in [invalid, "not-a-date"]:
        request = dispatcher.submit("reschedule", actor=learner, actor_role="student", student=learner,
            input={"lesson_id": str(lesson.pk), "slot": value})
        assert request.status == "awaiting_input", request.error
        assert request.result["requested_available"] is False and request.result["slots"]
        assert request.result["message"]
    offered = request.result["slots"][0]["starts_at"]
    checked = dispatcher.submit("reschedule", actor=learner, actor_role="student", student=learner,
        input={"lesson_id": str(lesson.pk), "slot": offered})
    assert checked.result["requested_available"] is True
    assert len(checked.result["slots"]) == 1
    assert datetime.fromisoformat(checked.result["proposed_slot"]) == datetime.fromisoformat(offered)


def test_no_available_times_is_explained_without_moving_lesson(learner, scheduled_learner):
    from domain.learning.models import AvailabilitySlot
    lesson = scheduled_learner; before = lesson.starts_at
    AvailabilitySlot.objects.filter(teacher=lesson.teacher).delete()
    request = dispatcher.submit("reschedule", actor=learner, actor_role="student", student=learner,
        input={"lesson_id": str(lesson.pk)})
    assert request.status == "awaiting_input", request.error
    assert request.result["slots"] == []
    assert "Contact your teacher" in request.result["message"]
    lesson.refresh_from_db(); assert lesson.starts_at == before


def test_final_confirmation_rechecks_new_booking_conflict(learner, scheduled_learner):
    from datetime import datetime
    lesson = scheduled_learner; before = lesson.starts_at
    request = dispatcher.submit("reschedule", actor=learner, actor_role="student", student=learner,
        input={"lesson_id": str(lesson.pk)})
    selected = next(s for s in request.result["slots"] if datetime.fromisoformat(s["starts_at"]) >= lesson.ends_at)
    services.book_lesson("planning", teacher=lesson.teacher, student=learner, title="New booking",
        starts_at=datetime.fromisoformat(selected["starts_at"]), ends_at=datetime.fromisoformat(selected["ends_at"]), status="confirmed")
    confirmation = dispatcher.submit("confirm_slot", actor=learner, actor_role="student", student=learner,
        input={"lesson_id": str(lesson.pk), "slot_request_id": str(request.pk), "slot_id": selected["id"]})
    assert confirmation.status == "failed" and confirmation.error["code"] == "slot_conflict"
    lesson.refresh_from_db(); assert lesson.starts_at == before
