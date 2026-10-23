"""LearningDomain read-only queries. Agents and the gateway read through these, never Model.objects."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import QuerySet

from domain.common import Role

from .models import (
    AssessmentSession,
    AvailabilitySlot,
    Course,
    LearningHistoryEntry,
    LearningPlan,
    LearningProfile,
    Lesson,
    LessonMaterial,
    PlanStage,
    ProficiencyProfile,
    TeacherComment,
)

PENDING_PLAN_STATUSES = ("pending_review", "changes_requested")
INTERACTION_KINDS = ("explain", "resources")


def student(pk: Any) -> Any | None:
    """The User with the student role, or None (agents cannot import the identity app)."""
    try:
        return get_user_model().objects.filter(pk=pk, groups__name=Role.STUDENT, is_active=True).first()
    except (ValidationError, ValueError, TypeError):
        return None


def profile_for(student: Any) -> LearningProfile | None:
    return LearningProfile.objects.filter(student=student).first()


def proficiency_records(student: Any) -> QuerySet[ProficiencyProfile]:
    return ProficiencyProfile.objects.filter(session__student=student).select_related("session").order_by("created_at")


def latest_confirmed_proficiency(student: Any) -> ProficiencyProfile | None:
    return proficiency_records(student).filter(status="confirmed").last()


def proficiency(pk: Any) -> ProficiencyProfile | None:
    return ProficiencyProfile.objects.select_related("session").filter(pk=pk).first()


def ongoing_assessments(student: Any) -> QuerySet[AssessmentSession]:
    return AssessmentSession.objects.filter(student=student, status="in_progress").order_by("-created_at")


def available_teachers():
    return get_user_model().objects.filter(groups__name=Role.TEACHER, is_active=True).select_related("teacher_profile").prefetch_related("availability_slots").order_by("pk").distinct()


def assessment_session(pk: Any) -> AssessmentSession | None:
    return AssessmentSession.objects.filter(pk=pk).select_related("student").first()


def active_plan(student: Any) -> LearningPlan | None:
    return LearningPlan.objects.filter(student=student, status="active").select_related("teacher").first()


def pending_plan(student: Any) -> LearningPlan | None:
    """Return an unfinished plan newer than the active version, preserving older history."""
    candidates = LearningPlan.objects.filter(student=student, status__in=PENDING_PLAN_STATUSES)
    current = active_plan(student)
    if current is not None:
        # Corrected predecessors retain changes_requested for the audit trail.
        # Once their replacement is active, they no longer block a new revision.
        candidates = candidates.filter(version__gt=current.version)
    return candidates.select_related("teacher").last()


def plan(pk: Any) -> LearningPlan | None:
    return LearningPlan.objects.select_related("teacher", "student").filter(pk=pk).first()


def plan_stages(plan: LearningPlan) -> QuerySet[PlanStage]:
    return plan.stages.prefetch_related("courses").order_by("stage_number")


def current_teacher(student: Any) -> Any | None:
    """Teacher of the active plan, else of the pending plan."""
    for candidate in (active_plan(student), pending_plan(student)):
        if candidate is not None and candidate.teacher_id:
            return candidate.teacher
    return None


def students_with_plan_teacher(teacher: Any) -> set[Any]:
    """Student ids whose active or pending plan names this teacher (assignment, UC06 2a)."""
    return set(
        LearningPlan.objects.filter(teacher=teacher, status__in=("active", *PENDING_PLAN_STATUSES)).values_list("student_id", flat=True)
    )


def lesson(pk: Any) -> Lesson | None:
    return Lesson.objects.select_related("teacher", "student", "stage").filter(pk=pk).first()


def lessons_for_student(student: Any) -> QuerySet[Lesson]:
    return Lesson.objects.filter(student=student).select_related("teacher", "stage")


def lessons_for_teacher(teacher: Any) -> QuerySet[Lesson]:
    return Lesson.objects.filter(teacher=teacher).select_related("teacher", "stage")


def teacher_windows(teacher: Any) -> QuerySet[AvailabilitySlot]:
    return AvailabilitySlot.objects.filter(teacher=teacher)


def material(pk: Any) -> LessonMaterial | None:
    return LessonMaterial.objects.select_related("lesson").filter(pk=pk).first()


def materials_for_lessons(lessons: QuerySet[Lesson] | list[Lesson], *, approved_only: bool = False) -> QuerySet[LessonMaterial]:
    qs = LessonMaterial.objects.filter(lesson__in=lessons)
    return qs.filter(status="approved") if approved_only else qs


def approved_material_ids(lesson: Lesson) -> list[str]:
    return [str(pk) for pk in lesson.lesson_materials.filter(status="approved").values_list("pk", flat=True)]


def latest_lesson_feedback(lesson: Lesson) -> str:
    comment = lesson.comments.filter(kind=TeacherComment.Kind.LESSON_FEEDBACK).last()
    return comment.text if comment else ""


def latest_observation(student: Any) -> TeacherComment | None:
    return TeacherComment.objects.filter(student=student, kind=TeacherComment.Kind.OBSERVATION).last()


def history(student: Any, *, kinds: tuple[str, ...] | None = None) -> QuerySet[LearningHistoryEntry]:
    qs = LearningHistoryEntry.objects.filter(student=student)
    return qs.filter(kind__in=kinds) if kinds else qs


def history_entry(pk: Any) -> LearningHistoryEntry | None:
    return LearningHistoryEntry.objects.filter(pk=pk).first()


def courses(*, skill: str | None = None, level: str | None = None) -> QuerySet[Course]:
    qs = Course.objects.prefetch_related("prerequisites", "materials")
    if skill:
        qs = qs.filter(skill__iexact=skill)
    if level:
        qs = qs.filter(level__iexact=level)
    return qs



def student_record_integrity_snapshot(student_id: str) -> dict:
    """Return minimal metadata for student record integrity checks."""

    from domain.learning.models import (
        LearningProfile,
        AssessmentSession,
        LearningPlan,
        ProficiencyProfile,
    )

    profile_exists = LearningProfile.objects.filter(
        student_id=student_id,
    ).exists()

    completed_assessments = AssessmentSession.objects.filter(
        student_id=student_id,
        status="completed",
    )

    assessment_exists = completed_assessments.exists()

    proficiency_exists = ProficiencyProfile.objects.filter(
        session__student_id=student_id,
        session__status="completed",
    ).exists()

    active_plan = (
        LearningPlan.objects
        .filter(
            student_id=student_id,
            status="active",
        )
        .select_related("based_on", "based_on__session")
        .order_by("-version")
        .first()
    )

    plan_assessment_valid = True

    if active_plan is not None:
        profile = active_plan.based_on

        plan_assessment_valid = (
            profile is not None
            and str(profile.session.student_id) == str(student_id)
            and profile.session.status == "completed"
        )

    return {
        "student_id": str(student_id),
        "profile_exists": profile_exists,
        "assessment_exists": assessment_exists,
        "proficiency_exists": proficiency_exists,
        "active_plan_id": (
            str(active_plan.pk)
            if active_plan is not None
            else None
        ),
        "plan_assessment_valid": plan_assessment_valid,
    }

def student_learning_history_summary(
    student_id: str,
    limit: int = 20,
) -> dict:
    """Return minimal learning history metadata for maintenance."""

    from domain.learning.models import LearningHistoryEntry

    limit = max(1, min(limit, 100))

    records = (
        LearningHistoryEntry.objects
        .filter(student_id=student_id)
        .order_by("-created_at", "-pk")[:limit]
    )

    entries = [
        {
            "entry_id": str(entry.pk),
            "source_agent": entry.source_agent,
            "kind": entry.kind,
            "confidence": entry.confidence,
            "escalated": entry.escalated,
            "created_at": entry.created_at.isoformat(),
        }
        for entry in records
    ]

    return {
        "student_id": str(student_id),
        "returned_count": len(entries),
        "entries": entries,
    }


def student_plan_version_snapshot(student_id: str) -> list[dict]:
    """Return plan version metadata without private plan content."""

    from domain.learning.models import LearningPlan

    plans = (
        LearningPlan.objects
        .filter(student_id=student_id)
        .order_by("version", "created_at")
    )

    return [
        {
            "plan_id": str(plan.pk),
            "version": plan.version,
            "status": plan.status,
            "previous_version_id": (
                str(plan.previous_version_id)
                if plan.previous_version_id
                else None
            ),
        }
        for plan in plans
    ]


def student_archive_snapshot(student_id: str) -> dict:
    """Return operational blockers for student record archiving."""

    from django.utils import timezone

    from domain.learning.models import (
        LearningPlan,
        Lesson,
        AssessmentSession,
        ProficiencyProfile,
    )

    now = timezone.now()

    has_active_plan = LearningPlan.objects.filter(
        student_id=student_id,
        status="active",
    ).exists()

    has_upcoming_lessons = Lesson.objects.filter(
        student_id=student_id,
        status__in=["confirmed", "proposed"],
        starts_at__gt=now,
    ).exists()

    has_pending_assessments = AssessmentSession.objects.filter(
        student_id=student_id,
        status="awaiting_review",
    ).exists()

    has_unresolved_reviews = ProficiencyProfile.objects.filter(
        session__student_id=student_id,
        status="pending_review",
    ).exists()

    return {
        "student_id": str(student_id),
        "has_active_plan": has_active_plan,
        "has_upcoming_lessons": has_upcoming_lessons,
        "has_pending_assessments": has_pending_assessments,
        "has_unresolved_reviews": has_unresolved_reviews,
    }
