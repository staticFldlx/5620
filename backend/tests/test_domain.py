"""Domain services: writer ownership, automatic audit, append-only records, NFR-03 checks."""

from datetime import datetime, timedelta, timezone

import pytest

from access_control.identity.models import User
from domain.common import DomainError, WriterNotAllowed
from domain.governance.models import AuditLog
from domain.learning import selectors as learning
from domain.learning import services
from domain.learning.models import LearningHistoryEntry, LearningPlan
from tests.conftest import key

pytestmark = pytest.mark.django_db


def user(name: str) -> User:
    return User.objects.get(pk=key(name))


def test_writer_check_rejects_wrong_agent_and_wrong_role():
    ivy = user("student-ivy")
    with pytest.raises(WriterNotAllowed):
        services.create_assessment_session("teaching_support", student=ivy, type="initial")
    with pytest.raises(WriterNotAllowed):
        services.create_assessment_session(ivy, student=ivy, type="initial")  # a student cannot write assessment results
    session = services.create_assessment_session("assessment", student=ivy, type="initial")
    assert session.status == "in_progress"


def test_service_writes_are_audited_with_trace_context():
    from domain.common import trace_context

    ivy = user("student-ivy")
    with trace_context(request_id="req-1", task_id="task-1"):
        session = services.create_assessment_session("assessment", student=ivy, type="initial")
    entry = AuditLog.objects.get(target_id=str(session.pk))
    assert (entry.actor, entry.action, entry.request_id, entry.task_id) == ("assessment", "assessment_session.created", "req-1", "task-1")


def test_audit_log_is_append_only():
    entry = AuditLog.objects.first()
    entry.action = "changed"
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()
    with pytest.raises(PermissionError):
        AuditLog.objects.all().delete()
    with pytest.raises(PermissionError):
        AuditLog.objects.update(action="x")


def test_history_is_append_only_and_owned_by_the_writing_agent():
    ivy = user("student-ivy")
    entry = services.append_history("teaching_support", student=ivy, kind="explain", payload={"question": "q"})
    assert entry.source_agent == "teaching_support"
    entry.kind = "other"
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(WriterNotAllowed):
        services.append_history("tech_operations", student=ivy, kind="explain", payload={})
    assert LearningHistoryEntry.objects.filter(pk=entry.pk, kind="explain").exists()


def test_record_answer_is_idempotent():
    ivy = user("student-ivy")
    session = services.create_assessment_session("assessment", student=ivy, type="initial", items=[{"item_id": "item-1", "prompt": "Q", "answer": None}])
    services.record_answer("assessment", session, item_id="item-1", answer="first")
    services.record_answer("assessment", session, item_id="item-1", answer="second")
    session.refresh_from_db()
    assert session.items[0]["answer"] == "first"
    with pytest.raises(DomainError):
        services.record_answer("assessment", session, item_id="item-9", answer="x")


def test_activate_plan_supersedes_previous_active_version():
    ivy = user("student-ivy")
    pending = learning.pending_plan(ivy)
    previous = learning.active_plan(ivy)
    services.activate_plan("planning", pending, approved_by=user("teacher-emily"))
    previous.refresh_from_db()
    assert previous.status == "superseded"
    assert learning.active_plan(ivy).pk == pending.pk
    assert LearningPlan.objects.filter(student=ivy, status="active").count() == 1


def sydney(day: int, hour: int) -> datetime:
    # October 2026 in Sydney is UTC+11
    return datetime(2026, 10, day, hour, 0, tzinfo=timezone(timedelta(hours=11)))


def test_lesson_slot_checks_teacher_window_and_overlaps():
    emily, ivy, sophia = user("teacher-emily"), user("student-ivy"), user("student-sophia")
    # Thursday 2026-10-22 18:00-19:00 is inside Emily's window and free
    services.check_lesson_slot(teacher=emily, student=ivy, starts_at=sydney(22, 18), ends_at=sydney(22, 19))
    with pytest.raises(DomainError) as outside:
        services.check_lesson_slot(teacher=emily, student=ivy, starts_at=sydney(21, 18), ends_at=sydney(21, 19))  # Wednesday
    assert outside.value.code == "outside_teacher_availability"
    with pytest.raises(DomainError) as clash:
        # Thursday 2026-10-15 18:00 is Sophia's proposed lesson with Emily
        services.check_lesson_slot(teacher=emily, student=ivy, starts_at=sydney(15, 18), ends_at=sydney(15, 19))
    assert clash.value.code == "slot_conflict"
    lesson = services.book_lesson("planning", teacher=emily, student=sophia, starts_at=sydney(22, 18), ends_at=sydney(22, 19), title="Practice", status="confirmed")
    moved = services.move_lesson("planning", lesson, starts_at=sydney(22, 19), ends_at=sydney(22, 20))
    assert moved.starts_at == sydney(22, 19)


def test_availability_change_cannot_strand_a_booked_lesson():
    emily = user("teacher-emily")
    with pytest.raises(DomainError) as exc:
        # removing Thursday would strand Sophia's lesson on 2026-10-15
        services.replace_availability(emily, emily, windows=[{"day": "Tue", "start": "18:00", "end": "20:00"}], tz="Australia/Sydney")
    assert exc.value.code == "availability_conflicts_booking"
    slots = services.replace_availability(emily, emily, windows=[{"day": "Thu", "start": "17:00", "end": "21:00"}], tz="Australia/Sydney")
    assert [(s.day, s.start_time.hour, s.end_time.hour) for s in slots] == [("Thu", 17, 21)]


def test_student_selector_only_returns_students():
    assert learning.student(key("student-ivy")) == user("student-ivy")
    assert learning.student(key("teacher-emily")) is None
    assert learning.student(key("no-such-user")) is None
    assert learning.student("not-a-uuid") is None
