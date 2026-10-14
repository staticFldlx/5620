"""Read models: LearningDomain rows rendered as the JSON records the frontend uses (src/api/types.ts).

Agents use these to build request results, so the frontend contract has one implementation.
"""

from __future__ import annotations

from typing import Any

from domain.common import iso

from . import selectors
from .models import AssessmentSession, AvailabilitySlot, LearningHistoryEntry, LearningPlan, LearningProfile, Lesson, LessonMaterial, ProficiencyProfile

DEFAULT_PROFILE = {
    "goal_text": "",
    "goal_summary": "Set your learning goal",
    "focus_skills": [],
    "target_level": "",
    "self_level": "",
    "weekly_hours": 3,
    "timezone": "Australia/Sydney",
    "availability": [],
}


def user_ref(user: Any) -> dict | None:
    return {"id": str(user.pk), "name": user.name} if user is not None else None


def profile_view(profile: LearningProfile | None) -> dict:
    if profile is None:
        return dict(DEFAULT_PROFILE)
    objective, prefs = profile.structured_objective or {}, profile.preferences or {}
    return {
        "goal_text": profile.learning_goal,
        "goal_summary": objective.get("summary") or DEFAULT_PROFILE["goal_summary"],
        "focus_skills": list(objective.get("focus_skills") or []),
        "target_level": objective.get("target_level") or "",
        "self_level": profile.english_level,
        "weekly_hours": prefs.get("weekly_hours", DEFAULT_PROFILE["weekly_hours"]),
        "timezone": prefs.get("timezone") or DEFAULT_PROFILE["timezone"],
        "availability": list(prefs.get("availability") or []),
    }


def proficiency_view(record: ProficiencyProfile) -> dict:
    """Frontend `Assessment` (contract ProficiencyRecord)."""
    session = record.session
    return {
        "id": str(record.pk),
        "kind": session.type,
        "status": record.status,
        "created_at": iso(record.created_at),
        "level": record.overall_level,
        "confidence": record.confidence,
        "strengths": list(record.strengths or []),
        "weaknesses": list(record.weak_areas or []),
        "goal_gap": record.gap_to_goal,
        "feedback": record.feedback,
        "review_note": record.review_note,
        "requested_focus": session.focus or None,
    }


def session_view(session: AssessmentSession) -> dict:
    """Assessment session as returned by /assessments endpoints."""
    items = session.items or []
    answered = [i.get("item_id") for i in items if i.get("answer") is not None]
    pending = next((i for i in items if i.get("answer") is None), None)
    proficiency = getattr(session, "proficiency", None)  # reverse one-to-one; None when not evaluated yet
    return {
        "id": str(session.pk),
        "student_id": str(session.student_id),
        "kind": session.type,
        "focus": session.focus,
        "answered": len(answered),
        "answered_items": answered,
        "max_items": session.max_items,
        "status": session.status,
        "current_item": (pending or {}).get("prompt", ""),
        "current_item_id": (pending or {}).get("item_id"),
        "result": proficiency_view(proficiency) if proficiency else None,
    }


def plan_view(plan: LearningPlan, *, review_id: str = "") -> dict:
    return {
        "id": str(plan.pk),
        "version": plan.version,
        "status": plan.status,
        "stage_index": plan.stage_index,
        "teacher": user_ref(plan.teacher),
        "weekly_hours": plan.weekly_hours,
        "stages": [
            {
                "title": stage.title,
                "course_ref": next((c.code for c in stage.courses.all()), ""),
                "start_week": stage.start_week,
                "end_week": stage.end_week,
                "topics": list(stage.topics or []),
                "milestone": stage.milestone,
                "status": stage.status,
            }
            for stage in selectors.plan_stages(plan)
        ],
        "reason": plan.rationale,
        "review_id": review_id,
        "approved_at": iso(plan.approved_at),
    }


def lesson_view(lesson: Lesson) -> dict:
    return {
        "id": str(lesson.pk),
        "student_id": str(lesson.student_id),
        "title": lesson.title,
        "starts_at": iso(lesson.starts_at),
        "ends_at": iso(lesson.ends_at),
        "teacher": user_ref(lesson.teacher),
        "stage_index": (lesson.stage.stage_number - 1) if lesson.stage else 0,
        "status": lesson.status,
        "classroom_url": lesson.classroom_url,
        "attendance": lesson.attendance,
        "feedback": selectors.latest_lesson_feedback(lesson),
        "material_ids": selectors.approved_material_ids(lesson),
    }


def material_view(material: LessonMaterial) -> dict:
    return {
        "id": str(material.pk),
        "title": material.title,
        "locator": material.locator,
        "status": material.status,
        "lesson_id": str(material.lesson_id),
        "content": material.content,
        "source_refs": list(material.citations or []),
    }


def interaction_view(entry: LearningHistoryEntry, *, case: Any = None) -> dict:
    """Frontend `Interaction`. A teacher's answer to an escalated question is overlaid from its case."""
    payload = entry.payload or {}
    view = {
        "id": str(entry.pk),
        "student_id": str(entry.student_id),
        "type": entry.kind,
        "question": payload.get("question", ""),
        "answer": payload.get("answer", ""),
        "feedback": payload.get("feedback"),
        "status": "escalated" if entry.escalated else "completed",
        "confidence": entry.confidence,
        "source_refs": list(payload.get("source_refs") or []),
        "sent_at": iso(entry.created_at),
        "escalation": None,
    }
    if case is not None:
        resolved = case.status != "open"
        decision = case.decision or {}
        view["escalation"] = {
            "trigger": case.trigger,
            "status": "resolved" if resolved else "pending",
            "review_id": str(case.pk),
            "resolved_by": user_ref(case.resolved_by)["name"] if case.resolved_by else None,
        }
        if resolved and decision.get("action") == "answer":
            view["answer"] = decision.get("note", view["answer"])
            view["status"] = "completed"
    return view


def availability_view(slot: AvailabilitySlot) -> dict:
    return {"day": slot.day, "start": slot.start_time.strftime("%H:%M"), "end": slot.end_time.strftime("%H:%M")}


def material_completion_view(entry: LearningHistoryEntry) -> dict:
    return {"material_id": (entry.payload or {}).get("material_id"), "completed_at": iso(entry.created_at)}
