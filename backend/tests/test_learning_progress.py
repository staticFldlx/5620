"""UC05 checkpoints, teacher corrections and conservative replanning, on isolated test data."""
from datetime import timedelta

import pytest
from django.utils import timezone

from access_control.gateway.presenters import student_record
from access_control.identity.models import User
from domain.learning import selectors as learning, services
from domain.learning.models import AssessmentSession, LearningPlan, Lesson, PlanStage
from domain.governance.models import EscalationCase, ServiceRequest
from orchestration.milestones import publish_ready_milestone
from orchestration.task_queue import dispatcher
from tests.conftest import key
from tests.test_planning import learner, active_for, assessment_to_planning

pytestmark = pytest.mark.django_db


@pytest.fixture
def progress_plan(learner):
    teacher = User.objects.get(pk=key("teacher-emily"))
    plan = active_for(learner, teacher)
    stages = list(plan.stages.all())
    for stage in stages:
        stage.milestone = "Demonstrate B2 reading and writing"
        stage.save(update_fields=["milestone"])
        Lesson.objects.create(student=learner, teacher=teacher, stage=stage, title=stage.title,
            status="confirmed", starts_at=timezone.now() - timedelta(days=2), ends_at=timezone.now() - timedelta(days=2, hours=-1))
    return plan


def attend(stage):
    stage.lessons.update(status="completed", attendance="attended")


def result(plan, *, level="B2", stage=None, status="confirmed", baseline="B2"):
    session = services.create_assessment_session("assessment", student=plan.student, type="milestone", status="completed",
        milestone_stage=stage, baseline_level=baseline, milestone_target_level="B2" if stage else "")
    return services.record_proficiency("assessment", session=session, overall_level=level, status=status, confidence=.9)


def drain_worker():
    for _ in range(60):
        if not dispatcher.run_next(): return
    raise AssertionError("Worker did not become idle")


def answer_all(request, text="yes"):
    drain_worker()
    for _ in range(9):
        request.refresh_from_db()
        session = AssessmentSession.objects.get(pk=request.result["session_id"])
        if session.status != "in_progress": return session
        item = next(i for i in session.items if i.get("answer") is None)
        dispatcher.reply(request, input={"item_id": item["item_id"], "answer": text})
        drain_worker()
    raise AssertionError("Assessment did not finish")


@pytest.mark.parametrize("mode", ["inline", "worker"])
def test_last_attended_lesson_releases_one_checkpoint_via_api(progress_plan, emily, settings, mode):
    settings.AGENT_TASK_EXECUTION = mode
    stage = progress_plan.stages.first()
    first = stage.lessons.get()
    second = Lesson.objects.create(student=progress_plan.student, teacher=progress_plan.teacher, stage=stage,
        title="Second lesson", starts_at=first.starts_at, ends_at=first.ends_at, status="confirmed")
    response = emily.patch(f"/lessons/{first.pk}", {"attendance": "attended", "feedback": "Complete"})
    assert response.status_code == 200, response.content
    stage.refresh_from_db()
    assert stage.milestone_request is None
    response = emily.patch(f"/lessons/{second.pk}", {"attendance": "attended", "feedback": "Complete"})
    assert response.status_code == 200, response.content
    stage.refresh_from_db()
    assert stage.milestone_request is not None
    req = stage.milestone_request
    assert req.status == ("awaiting_input" if mode == "inline" else "queued"), req.error
    drain_worker()
    sessions = AssessmentSession.objects.filter(milestone_stage=stage)
    assert sessions.count() == 1
    assert sessions.get().baseline_level == "B2"
    assert sessions.get().milestone_target_level == "B2"
    assert publish_ready_milestone(progress_plan.student, progress_plan.teacher).pk == req.pk
    assert emily.patch(f"/lessons/{second.pk}", {"feedback": "Updated feedback"}).status_code == 200
    assert sessions.count() == 1


def test_absence_future_and_later_stage_do_not_release(progress_plan, emily):
    first, later = list(progress_plan.stages.all())[:2]
    attend(later)
    assert publish_ready_milestone(progress_plan.student, progress_plan.teacher) is None
    first.lessons.update(status="completed", attendance="absent")
    assert publish_ready_milestone(progress_plan.student, progress_plan.teacher) is None
    lesson = first.lessons.get()
    lesson.starts_at = timezone.now() + timedelta(days=1)
    lesson.save(update_fields=["starts_at"])
    assert emily.patch(f"/lessons/{lesson.pk}", {"attendance": "attended"}).status_code == 409
    assert not AssessmentSession.objects.filter(milestone_stage=first).exists()


@pytest.mark.parametrize("mode", ["inline", "worker"])
def test_teacher_corrects_pending_checkpoint_then_advances_once(progress_plan, emily, settings, mode):
    settings.AGENT_TASK_EXECUTION = mode
    stage = progress_plan.stages.first()
    attend(stage)
    request = publish_ready_milestone(progress_plan.student, progress_plan.teacher)
    session = answer_all(request)
    assert session.status == "awaiting_review"
    progress_plan.refresh_from_db()
    assert progress_plan.stage_index == 0
    case = EscalationCase.objects.get(subject_id=session.proficiency.pk)
    response = emily.post(f"/reviews/{case.pk}/decision", {"action": "confirm_result", "note": "Class evidence demonstrates B2", "corrected_level": "B2"})
    assert response.status_code == 200, response.content
    drain_worker()
    progress_plan.refresh_from_db(); stage.refresh_from_db(); session.proficiency.refresh_from_db()
    assert session.proficiency.overall_level == "B2"
    assert progress_plan.stage_index == 1
    assert stage.status == "completed"
    assert progress_plan.stages.get(stage_number=2).status == "current"
    assert learning.pending_plan(progress_plan.student) is None
    assert LearningPlan.objects.filter(student=progress_plan.student).count() == 1
    again = services.apply_progress_assessment(progress_plan, session.proficiency)
    assert not again["advanced"]
    progress_plan.refresh_from_db()
    assert progress_plan.stage_index == 1
    assert "Stage 1 completed" in student_record(progress_plan.student)["plan"]["progress_message"]


def test_final_checkpoint_remains_visible_as_completed(progress_plan):
    for stage in progress_plan.stages.all():
        attend(stage)
        decision = services.apply_progress_assessment(progress_plan, result(progress_plan, stage=stage))
        assert decision["advanced"] and not decision["revise"]
    progress_plan.refresh_from_db()
    assert progress_plan.status == "completed"
    assert not progress_plan.stages.exclude(status="completed").exists()
    view = student_record(progress_plan.student)
    assert view["plan"]["status"] == "completed"
    assert "All plan stages" in view["plan"]["progress_message"]
    assert publish_ready_milestone(progress_plan.student, progress_plan.teacher) is None
    late = assessment_to_planning(progress_plan.student, result(progress_plan))
    assert late.status == "completed", late.error
    assert LearningPlan.objects.filter(student=progress_plan.student).count() == 1


@pytest.mark.parametrize("level", ["B2", "C1"])
def test_on_track_assessment_keeps_plan_and_version(progress_plan, level):
    request = assessment_to_planning(progress_plan.student, result(progress_plan, level=level))
    assert request.status == "completed", request.error
    progress_plan.refresh_from_db()
    assert progress_plan.status == "active" and progress_plan.stage_index == 0
    assert LearningPlan.objects.filter(student=progress_plan.student).count() == 1
    assert "on track" in student_record(progress_plan.student)["plan"]["progress_message"]


@pytest.mark.parametrize("linked", [False, True])
def test_deviation_requests_one_revision_preserving_active_plan(progress_plan, linked):
    stage = progress_plan.stages.first()
    attend(stage)
    record = result(progress_plan, level="B1", stage=stage if linked else None)
    request = assessment_to_planning(progress_plan.student, record)
    assert request.status == "awaiting_approval", request.error
    assert request.replans == 1
    assert learning.active_plan(progress_plan.student).pk == progress_plan.pk
    assert learning.pending_plan(progress_plan.student).based_on_id == record.pk
    assert progress_plan.stages.get(pk=stage.pk).status != "completed"
    assessment_to_planning(progress_plan.student, result(progress_plan, level="A2"))
    assert LearningPlan.objects.filter(student=progress_plan.student, status="pending_review").count() == 1


def test_rejected_checkpoint_retry_is_explicit(progress_plan, emily):
    stage = progress_plan.stages.first(); attend(stage)
    request = publish_ready_milestone(progress_plan.student, progress_plan.teacher)
    session = answer_all(request)
    case = EscalationCase.objects.get(subject_id=session.proficiency.pk)
    response = emily.post(f"/reviews/{case.pk}/decision", {"action": "request_changes", "note": "Please retake with complete answers"})
    assert response.status_code == 200, response.content
    request.refresh_from_db()
    assert request.status == "failed", request.error
    assert publish_ready_milestone(progress_plan.student, progress_plan.teacher).pk == request.pk
    retried = publish_ready_milestone(progress_plan.student, progress_plan.student, retry_rejected=True)
    assert retried.pk != request.pk and retried.status == "awaiting_input", retried.error
    assert AssessmentSession.objects.filter(milestone_stage=stage).count() == 2


def test_unconfirmed_unattended_historical_and_foreign_results_cannot_advance(progress_plan):
    stage = progress_plan.stages.first()
    pending = result(progress_plan, stage=stage, status="pending_review")
    attend(stage)
    assert not services.apply_progress_assessment(progress_plan, pending)["advanced"]
    other = LearningPlan.objects.get(student_id=key("student-ivy"), status="active")
    foreign = result(other)
    assert not services.apply_progress_assessment(progress_plan, foreign)["advanced"]
    stage.lessons.update(attendance="absent")
    confirmed = result(progress_plan, stage=stage)
    assert not services.apply_progress_assessment(progress_plan, confirmed)["advanced"]
    attend(stage)
    assert services.apply_progress_assessment(progress_plan, result(progress_plan, stage=stage))["advanced"]
    late = services.apply_progress_assessment(progress_plan, result(progress_plan, level="A1", stage=stage))
    assert not late["revise"] and not late["advanced"]
    progress_plan.refresh_from_db()
    assert progress_plan.stage_index == 1


def test_confirmed_checkpoint_advances_while_revision_pending(progress_plan):
    from tests.test_planning import draft
    services.create_plan("planning", student=progress_plan.student, teacher=progress_plan.teacher,
        based_on=progress_plan.based_on, version=2, weekly_hours=4, rationale="Pending change", stages=[{k: v for k, v in stage.items() if k != "course_codes"} for stage in draft()["stages"]])
    stage = progress_plan.stages.first(); attend(stage)
    request = assessment_to_planning(progress_plan.student, result(progress_plan, stage=stage))
    assert request.status == "completed", request.error
    progress_plan.refresh_from_db()
    assert progress_plan.stage_index == 1
    assert LearningPlan.objects.filter(student=progress_plan.student).count() == 2


def test_next_ready_stage_is_automatically_published_after_progression(progress_plan):
    first, second = list(progress_plan.stages.all())
    attend(first); attend(second)
    request = assessment_to_planning(progress_plan.student, result(progress_plan, stage=first))
    assert request.status == "completed", request.error
    second.refresh_from_db()
    assert second.milestone_request.status == "awaiting_input"
    assert AssessmentSession.objects.filter(milestone_stage=second).count() == 1


def test_older_plan_checkpoint_does_not_change_new_active_plan(progress_plan):
    stage = progress_plan.stages.first(); attend(stage)
    record = result(progress_plan, stage=stage, level="A1")
    replacement = active_for(progress_plan.student, progress_plan.teacher)
    decision = services.apply_progress_assessment(replacement, record)
    assert not decision["revise"] and not decision["advanced"]
    replacement.refresh_from_db()
    assert replacement.stage_index == 0 and replacement.status == "active"


def test_completed_plan_does_not_show_superseded_pending_predecessor(progress_plan):
    LearningPlan.objects.create(student=progress_plan.student, teacher=progress_plan.teacher,
        version=0, status="changes_requested", rationale="Old corrections")
    for stage in progress_plan.stages.all():
        attend(stage)
        services.apply_progress_assessment(progress_plan, result(progress_plan, stage=stage))
    assert student_record(progress_plan.student)["pending_plan"] is None


def test_stage_target_uses_milestone_then_course_then_baseline(progress_plan):
    stage = progress_plan.stages.first()
    assert learning.stage_target_level(stage) == "B2"
    stage.milestone = "Reach B1 then B2 proficiency"
    assert learning.stage_target_level(stage) == "B2"
    stage.milestone = "Identify a claim and evidence"
    assert learning.stage_target_level(stage) in learning.CEFR_LEVELS
    stage.courses.clear()
    assert learning.stage_target_level(stage) == "B2"


def test_cancelled_lesson_is_excluded_but_empty_stage_cannot_complete(progress_plan):
    stage = progress_plan.stages.first()
    stage.lessons.update(status="cancelled")
    assert not learning.stage_lessons_attended(stage)
    existing = stage.lessons.first()
    Lesson.objects.create(student=progress_plan.student, teacher=progress_plan.teacher, stage=stage,
        title="Replacement lesson", starts_at=existing.starts_at, ends_at=existing.ends_at,
        attendance="attended", status="completed")
    assert learning.stage_lessons_attended(stage)
