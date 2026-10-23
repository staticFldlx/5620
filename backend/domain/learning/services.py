"""LearningDomain writes. First argument is always the actor (see domain.common).

Functions here cover what the shared layer itself needs plus the core writes every agent
needs to satisfy the frontend contract. Agent owners add more via PR (spec 3.3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from domain.common import DomainError, actor_label, check_writer, save_fields, writes
from infrastructure.scheduling import WeeklyWindow, fits_weekly_window, normalise_day, overlaps, parse_hhmm

from .models import (
    AssessmentSession,
    AvailabilitySlot,
    LearningHistoryEntry,
    LearningPlan,
    LearningProfile,
    Lesson,
    LessonMaterial,
    PlanStage,
    ProficiencyProfile,
    TeacherComment,
)

DEFAULT_TIMEZONE = "Australia/Sydney"


# --- LearningProfile (coordinator, role:student) -------------------------------
@writes(LearningProfile, "profile.created")
def create_profile(actor: Any, *, student: Any, **fields: Any) -> LearningProfile:
    fields.setdefault("preferences", {"weekly_hours": 3, "timezone": DEFAULT_TIMEZONE, "availability": []})
    fields.setdefault("structured_objective", {"summary": "", "focus_skills": [], "target_level": ""})
    return LearningProfile.objects.create(student=student, **fields)


def update_profile(actor: Any, profile: LearningProfile, **fields: Any) -> LearningProfile:
    """Fig 6b updateProfile(). JSON fields are merged, not replaced."""
    for key in ("structured_objective", "preferences"):
        if key in fields:
            fields[key] = {**getattr(profile, key), **fields[key]}
    return save_fields(actor, profile, "profile.updated", fields, {"fields": sorted(fields)})


# --- Assessment (assessment) ------------------------------------------------------
@writes(AssessmentSession, "assessment_session.created")
def create_assessment_session(actor: Any, *, student: Any, type: str, **fields: Any) -> AssessmentSession:
    fields.setdefault("started_at", timezone.now())
    return AssessmentSession.objects.create(student=student, type=type, **fields)


def update_assessment_session(actor: Any, session: AssessmentSession, **fields: Any) -> AssessmentSession:
    return save_fields(actor, session, "assessment_session.updated", fields, {"status": fields.get("status", session.status)})


def record_answer(actor: Any, session: AssessmentSession, *, item_id: str, answer: str) -> AssessmentSession:
    """Idempotent: a second submission for the same item changes nothing."""
    items = [dict(item) for item in session.items]
    item = next((i for i in items if i.get("item_id") == item_id), None)
    if item is None:
        raise DomainError("unknown_item", f"Item {item_id} is not part of this assessment.", status=400)
    if item.get("answer") is not None:
        return session
    item["answer"] = answer
    item["answered_at"] = timezone.now().isoformat()
    return update_assessment_session(actor, session, items=items)


@writes(ProficiencyProfile, "proficiency.recorded")
def record_proficiency(actor: Any, *, session: AssessmentSession, **fields: Any) -> ProficiencyProfile:
    return ProficiencyProfile.objects.create(session=session, **fields)


def update_proficiency(actor: Any, profile: ProficiencyProfile, **fields: Any) -> ProficiencyProfile:
    """E.g. the teacher's confirmation written back through the escalation flow (UC02 7a)."""
    return save_fields(actor, profile, "proficiency.updated", fields, {"status": fields.get("status", profile.status)})


# --- Plans (planning) -----------------------------------------------------------------
def create_plan(actor: Any, *, student: Any, stages: list[dict], **fields: Any) -> LearningPlan:
    """Create a plan version with its stages. `stages` items use PlanStage field names."""
    check_writer(actor, LearningPlan)
    from domain.governance.services import record_audit

    with transaction.atomic():
        plan = LearningPlan.objects.create(student=student, **fields)
        for number, stage in enumerate(stages, start=1):
            stage = dict(stage)
            courses = stage.pop("courses", [])
            created = PlanStage.objects.create(plan=plan, stage_number=stage.pop("stage_number", number), **stage)
            if courses:
                created.courses.set(courses)
        record_audit(actor, "plan.created", plan, detail={"version": plan.version, "status": plan.status})
    return plan


def update_plan(actor: Any, plan: LearningPlan, **fields: Any) -> LearningPlan:
    return save_fields(actor, plan, "plan.updated", fields, {"status": fields.get("status", plan.status)})


def activate_plan(actor: Any, plan: LearningPlan, *, approved_by: Any) -> LearningPlan:
    """Teacher-approved version becomes active once; the previous active version is superseded."""
    check_writer(actor, LearningPlan)
    if plan.status == "active":
        return plan
    with transaction.atomic():
        for old in LearningPlan.objects.select_for_update().filter(student=plan.student, status="active").exclude(pk=plan.pk):
            save_fields(actor, old, "plan.superseded", {"status": "superseded"})
        save_fields(actor, plan, "plan.activated", {"status": "active", "approved_by": approved_by, "approved_at": timezone.now()})
        initialise_stage_statuses(plan)
    return plan


# --- Teacher time and lessons (role:teacher, planning) ---------------------------------
def replace_availability(actor: Any, teacher: Any, *, windows: list[dict], tz: str) -> list[AvailabilitySlot]:
    """Replace the weekly windows; reject changes that would strand an upcoming booked lesson."""
    check_writer(actor, AvailabilitySlot)
    parsed = []
    for window in windows:
        try:
            day, start, end = normalise_day(window["day"]), parse_hhmm(window["start"]), parse_hhmm(window["end"])
        except (KeyError, ValueError) as exc:
            raise DomainError("invalid_availability", f"Invalid availability entry {window}: {exc}", status=400) from exc
        if start >= end:
            raise DomainError("invalid_availability", f"Start must be before end: {window}", status=400)
        parsed.append(WeeklyWindow(day, start, end))
    upcoming = Lesson.objects.filter(teacher=teacher, starts_at__gte=timezone.now(), status__in=["confirmed", "proposed"])
    stranded = [lesson for lesson in upcoming if not fits_weekly_window(lesson.starts_at, lesson.ends_at, parsed, tz)]
    if stranded:
        titles = ", ".join(lesson.title for lesson in stranded[:3])
        raise DomainError("availability_conflicts_booking", f"The new availability no longer covers booked lessons: {titles}")
    from domain.governance.services import record_audit

    with transaction.atomic():
        AvailabilitySlot.objects.filter(teacher=teacher).delete()
        slots = [AvailabilitySlot.objects.create(teacher=teacher, day=w.day, start_time=w.start, end_time=w.end) for w in parsed]
        profile = getattr(teacher, "teacher_profile", None)
        if profile is not None and profile.timezone != tz:
            profile.timezone = tz
            profile.save(update_fields=["timezone", "updated_at"])
        record_audit(actor, "availability.replaced", teacher, detail={"windows": len(slots), "timezone": tz})
    return slots


def check_lesson_slot(*, teacher: Any, student: Any, starts_at: datetime, ends_at: datetime, exclude: Lesson | None = None) -> None:
    """NFR-03: inside the teacher's weekly window and no overlap for teacher or student."""
    if starts_at >= ends_at:
        raise DomainError("invalid_slot", "A lesson must end after it starts.", status=400)
    windows = [WeeklyWindow(s.day, s.start_time, s.end_time) for s in AvailabilitySlot.objects.filter(teacher=teacher)]
    tz = getattr(getattr(teacher, "teacher_profile", None), "timezone", DEFAULT_TIMEZONE)
    if not fits_weekly_window(starts_at, ends_at, windows, tz):
        raise DomainError("outside_teacher_availability", "The time is outside the teacher's declared availability.")
    busy = Lesson.objects.filter(status__in=["proposed", "confirmed"]).filter(teacher=teacher) | Lesson.objects.filter(
        status__in=["proposed", "confirmed"], student=student
    )
    if exclude is not None:
        busy = busy.exclude(pk=exclude.pk)
    if any(overlaps(starts_at, ends_at, other.starts_at, other.ends_at) for other in busy):
        raise DomainError("slot_conflict", "The time overlaps another lesson.")


@writes(Lesson, "lesson.booked")
def book_lesson(actor: Any, *, teacher: Any, student: Any, starts_at: datetime, ends_at: datetime, **fields: Any) -> Lesson:
    check_lesson_slot(teacher=teacher, student=student, starts_at=starts_at, ends_at=ends_at)
    return Lesson.objects.create(teacher=teacher, student=student, starts_at=starts_at, ends_at=ends_at, **fields)


def move_lesson(actor: Any, lesson: Lesson, *, starts_at: datetime, ends_at: datetime) -> Lesson:
    """Only after the student confirmed the exact slot; the conflict check runs again here."""
    check_lesson_slot(teacher=lesson.teacher, student=lesson.student, starts_at=starts_at, ends_at=ends_at, exclude=lesson)
    return save_fields(actor, lesson, "lesson.moved", {"starts_at": starts_at, "ends_at": ends_at, "status": "confirmed"})


def record_lesson_outcome(actor: Any, lesson: Lesson, *, attendance: str | None, feedback: str | None, teacher: Any) -> Lesson:
    """Teacher's post-lesson record (SM4). Schedule changes are not allowed here."""
    if attendance is not None:
        if attendance not in ("attended", "absent"):
            raise DomainError("invalid_attendance", "Attendance must be 'attended' or 'absent'.", status=400)
        if lesson.starts_at > timezone.now():
            raise DomainError("lesson_not_started", "Attendance can only be recorded after the lesson starts.")
    with transaction.atomic():
        if attendance is not None:
            save_fields(actor, lesson, "lesson.attendance_recorded", {"attendance": attendance, "status": "completed"})
        if feedback:
            add_teacher_comment(actor, teacher=teacher, student=lesson.student, lesson=lesson, kind=TeacherComment.Kind.LESSON_FEEDBACK, text=feedback)
    return lesson


# --- Teacher comments and materials ------------------------------------------------------
@writes(TeacherComment, "teacher_comment.created")
def add_teacher_comment(actor: Any, *, teacher: Any, student: Any, kind: str, text: str, lesson: Lesson | None = None) -> TeacherComment:
    return TeacherComment.objects.create(teacher=teacher, student=student, lesson=lesson, kind=kind, text=text)


@writes(LessonMaterial, "material.drafted")
def create_material_draft(actor: Any, *, lesson: Lesson, title: str, content: str, citations: list | None = None, locator: str = "") -> LessonMaterial:
    return LessonMaterial.objects.create(lesson=lesson, title=title, content=content, citations=citations or [], locator=locator, status="draft")


def edit_material(actor: Any, material: LessonMaterial, *, content: str, approve: bool, by: Any) -> LessonMaterial:
    """Teacher edits; approval makes it visible to the lesson's student. Editing an approved item returns it to draft."""
    fields: dict[str, Any] = {"content": content, "status": "approved" if approve else "draft"}
    fields["approved_by"] = by if approve else None
    return save_fields(actor, material, "material.approved" if approve else "material.saved", fields)


# --- Learning history (append-only, own rows only) -------------------------------------------
def append_history(actor: str, *, student: Any, kind: str, payload: dict, confidence: float | None = None, escalated: bool = False) -> LearningHistoryEntry:
    check_writer(actor, LearningHistoryEntry)
    from domain.governance.services import record_audit

    with transaction.atomic():
        entry = LearningHistoryEntry.objects.create(
            student=student, source_agent=actor_label(actor), kind=kind, payload=payload, confidence=confidence, escalated=escalated
        )
        record_audit(actor, f"history.{kind}", entry, detail={"escalated": escalated})
    return entry



def initialise_stage_statuses(plan):
    """Planning owns stage transitions; never infer completion from elapsed time."""
    for index, stage in enumerate(plan.stages.order_by("stage_number")):
        if stage.status == "completed":
            continue
        status = "current" if index == plan.stage_index else "upcoming"
        if stage.status != status:
            save_fields("planning", stage, "stage.status_updated", {"status": status})


def apply_progress_assessment(plan, assessment):
    """Return an auditable on-track/revision decision; only confirmed evidence can advance a stage.

    A drop of >= one CEFR band is significant. At a course-completion checkpoint,
    the confirmed level must also meet the milestone's stated CEFR target (or
    catalogue level, falling back to the plan baseline). Never interpret free-text
    weakness descriptions as an instruction to change the plan.
    """
    from . import selectors
    with transaction.atomic():
        plan = LearningPlan.objects.select_for_update().get(pk=plan.pk)
        if assessment.status != "confirmed" or assessment.session.student_id != plan.student_id:
            return {"revise": False, "advanced": False, "message": "Awaiting confirmed evidence."}
        previous = LearningHistoryEntry.objects.filter(student_id=plan.student_id, kind="progress_decision", payload__plan_id=str(plan.pk), payload__assessment_id=str(assessment.pk)).first()
        if previous:
            return {**previous.payload, "advanced": False}
        session = assessment.session
        if plan.status != "active" or (session.milestone_stage_id and session.milestone_stage.plan_id != plan.pk):
            return {"revise": False, "advanced": False, "message": "Historical assessment saved; current plan unchanged."}
        # Late results for an earlier stage must not move the current stage or replan it.
        if session.milestone_stage_id and session.milestone_stage.stage_number != plan.stage_index + 1:
            return {"revise": False, "advanced": False, "message": "Earlier milestone saved; current stage unchanged."}
        levels = selectors.CEFR_LEVELS
        baseline = session.baseline_level or (plan.based_on.overall_level if plan.based_on else "")
        level = assessment.overall_level
        if level not in levels:
            return {"revise": False, "advanced": False, "message": "A confirmed CEFR level is required to assess progress."}
        # A late result collected before this plan's baseline cannot revise the newer plan.
        if plan.based_on and assessment.created_at < plan.based_on.created_at:
            return {"revise": False, "advanced": False, "message": "Historical assessment saved; newer plan evidence is retained."}
        regressed = level in levels and baseline in levels and levels.index(level) < levels.index(baseline)
        stage = session.milestone_stage
        checkpoint = bool(stage and selectors.stage_lessons_attended(stage))
        target = session.milestone_target_level or (selectors.stage_target_level(stage) if stage else "")
        below_target = checkpoint and level in levels and target in levels and levels.index(level) < levels.index(target)
        revise = regressed or below_target
        advanced = False
        if revise:
            message = f"Plan review required: confirmed level {level}; baseline {baseline or 'not available'}" + (f"; milestone target {target}." if checkpoint else ".")
        elif checkpoint:
            save_fields("planning", stage, "stage.completed", {"status": "completed"})
            next_stage = plan.stages.filter(stage_number__gt=stage.stage_number).order_by("stage_number").first()
            if next_stage:
                save_fields("planning", plan, "plan.stage_advanced", {"stage_index": next_stage.stage_number - 1})
                initialise_stage_statuses(plan)
                message = f"Milestone achieved at {level}. Stage {stage.stage_number} completed; Stage {next_stage.stage_number} is current. Plan version unchanged."
            else:
                save_fields("planning", plan, "plan.completed", {"status": "completed"})
                message = f"Final milestone achieved at {level}. All plan stages are complete."
            advanced = True
        else:
            message = f"Progress is on track at {level}. Current plan and stage are unchanged."
        result = {"plan_id": str(plan.pk), "assessment_id": str(assessment.pk), "revise": revise, "advanced": advanced, "message": message}
        append_history("planning", student=plan.student, kind="progress_decision", payload=result)
        return result
