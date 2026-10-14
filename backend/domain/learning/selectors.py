"""LearningDomain read-only queries. Agents and the gateway read through these, never Model.objects."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

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


def profile_for(student: Any) -> LearningProfile | None:
    return LearningProfile.objects.filter(student=student).first()


def proficiency_records(student: Any) -> QuerySet[ProficiencyProfile]:
    return ProficiencyProfile.objects.filter(session__student=student).select_related("session").order_by("created_at")


def latest_confirmed_proficiency(student: Any) -> ProficiencyProfile | None:
    return proficiency_records(student).filter(status="confirmed").last()


def proficiency(pk: Any) -> ProficiencyProfile | None:
    return ProficiencyProfile.objects.select_related("session").filter(pk=pk).first()


def assessment_session(pk: Any) -> AssessmentSession | None:
    return AssessmentSession.objects.filter(pk=pk).select_related("student").first()


def active_plan(student: Any) -> LearningPlan | None:
    return LearningPlan.objects.filter(student=student, status="active").select_related("teacher").first()


def pending_plan(student: Any) -> LearningPlan | None:
    return LearningPlan.objects.filter(student=student, status__in=PENDING_PLAN_STATUSES).select_related("teacher").last()


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
