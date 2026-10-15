"""Prompt context for the Teaching Assistant, built from domain selectors.

Data minimisation (spec 8.6): only what a task needs leaves the platform. No names, emails
or user ids are included; materials are truncated. Without RAG, "retrieval" means choosing the
approved lesson materials of the learner's current plan stage.
"""

from __future__ import annotations

import re
from typing import Any

from domain.common import iso
from domain.learning import selectors as learning

MATERIAL_CHARS = 1200
WORD = re.compile(r"[a-z]{3,}")
# words that say nothing about which material fits (the default resources question in the frontend uses several)
STOPWORDS = frozenset(
    "the and for with how what can you your are have has this that from about into does should would could "
    "find learning resources resource current stage materials material help need want some which please".split()
)
RECENT_QUESTIONS = 5
RECENT_FEEDBACK = 3


def redact(text: str, student: Any) -> str:
    """Replace the learner's name in free text (teacher notes, questions) before it leaves the platform."""
    parts = [student.name] + [part for part in student.name.split() if len(part) > 1]
    for part in sorted(set(parts), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(part)}\b", "the learner", text, flags=re.IGNORECASE)
    return text


def current_stage(student: Any) -> dict | None:
    plan = learning.active_plan(student) or learning.pending_plan(student)
    if plan is None:
        return None
    stages = list(learning.plan_stages(plan))
    if not stages:
        return None
    stage = stages[min(plan.stage_index, len(stages) - 1)]
    return {
        "number": stage.stage_number,
        "of": len(stages),
        "title": stage.title,
        "topics": list(stage.topics or []),
        "milestone": stage.milestone,
        "plan_status": plan.status,
    }


def recent_questions(student: Any, limit: int = RECENT_QUESTIONS) -> list[str]:
    entries = learning.history(student, kinds=("explain",)).order_by("-created_at")[:limit]
    return [redact(entry.payload["question"], student) for entry in entries if entry.payload.get("question")]


def learner(student: Any) -> dict:
    """What a student-facing task needs: level, goal, current stage, weak areas, recent questions."""
    profile = learning.profile_for(student)
    objective = (profile.structured_objective if profile else None) or {}
    confirmed = learning.latest_confirmed_proficiency(student)
    if confirmed is not None:
        level, source = confirmed.overall_level, "confirmed assessment"
    else:
        level, source = (profile.english_level if profile else "") or "unknown", "self-reported"
    return {
        "level": level,
        "level_source": source,
        "target_level": objective.get("target_level", ""),
        "goal": objective.get("summary", ""),
        "focus_skills": list(objective.get("focus_skills") or []),
        "current_stage": current_stage(student),
        "weak_areas": list(confirmed.weak_areas or []) if confirmed else [],
        "recent_questions": recent_questions(student),
    }


def teacher_view(student: Any) -> dict:
    """Learner context plus the records a teacher reviews (UC06): assessments, plan, lessons, observation."""
    view = learner(student)
    view["assessments"] = [
        {
            "kind": record.session.type,
            "date": iso(record.created_at),
            "level": record.overall_level,
            "status": record.status,
            "provisional": record.status != "confirmed",  # pending_review: not yet confirmed by a teacher
            "confidence": record.confidence,
            "strengths": list(record.strengths or []),
            "weaknesses": list(record.weak_areas or []),
            "gap_to_goal": record.gap_to_goal,
        }
        for record in list(learning.proficiency_records(student))[-5:]
    ]
    plan = learning.active_plan(student)
    view["plan"] = (
        {
            "version": plan.version,
            "status": plan.status,
            "weekly_hours": plan.weekly_hours,
            "stages": [{"number": s.stage_number, "title": s.title, "milestone": s.milestone, "status": s.status} for s in learning.plan_stages(plan)],
        }
        if plan
        else None
    )
    pending = learning.pending_plan(student)
    view["pending_plan"] = {"version": pending.version, "status": pending.status, "reason": pending.rationale} if pending else None
    lessons = list(learning.lessons_for_student(student))
    feedback = [
        {"lesson": lesson.title, "date": iso(lesson.starts_at), "feedback": redact(text, student)}
        for lesson in lessons
        if (text := learning.latest_lesson_feedback(lesson))
    ]
    view["lesson_feedback"] = feedback[-RECENT_FEEDBACK:]
    observation = learning.latest_observation(student)
    view["teacher_observation"] = redact(observation.text, student) if observation else ""
    return view


def missing_progress_data(view: dict) -> list[str]:
    """UC06 3a: gaps the platform can see without the model, so they are always reported."""
    gaps = []
    assessments = view["assessments"]
    if not assessments:
        gaps.append("no assessment results")
    elif all(a["provisional"] for a in assessments):
        gaps.append("no confirmed assessment result")
    if view["plan"] is None:
        gaps.append("no active learning plan")
    if not view["lesson_feedback"]:
        gaps.append("no lesson feedback yet")
    if not view["teacher_observation"]:
        gaps.append("no teacher observation")
    return gaps


def results_summary(view: dict) -> str:
    """One line that always separates confirmed from provisional results."""
    parts = []
    for a in view["assessments"]:
        state = "confirmed" if not a["provisional"] else "provisional, awaiting teacher review" if a["status"] == "pending_review" else a["status"]
        parts.append(f"{a['kind']} {a['level']} ({state}, {(a['date'] or '')[:10]})")
    return f"Results: {'; '.join(parts)}." if parts else ""


def lesson_info(lesson: Any) -> dict:
    stage = lesson.stage
    return {
        "title": lesson.title,
        "starts_at": iso(lesson.starts_at),
        "status": lesson.status,
        "stage": {"number": stage.stage_number, "title": stage.title, "topics": list(stage.topics or []), "milestone": stage.milestone} if stage else None,
        "last_feedback": redact(learning.latest_lesson_feedback(lesson), lesson.student),
    }


def material_entry(material: Any) -> dict:
    return {"id": str(material.pk), "title": material.title, "locator": material.locator, "content": material.content[:MATERIAL_CHARS]}


def source_ref(entry: dict) -> dict:
    """The InteractionRecord / MaterialRecord source reference shape."""
    return {"material_id": entry["id"], "title": entry["title"], "locator": entry["locator"]}


def stage_materials(student: Any, *, limit: int = 5) -> list[dict]:
    """Approved materials of the learner's lessons, current-stage lessons first."""
    stage = current_stage(student)
    lessons = list(learning.lessons_for_student(student))
    current = [lesson for lesson in lessons if stage and lesson.stage and lesson.stage.stage_number == stage["number"]]
    ordered = current + [lesson for lesson in lessons if lesson not in current]
    found: dict[str, dict] = {}
    for lesson in ordered:
        for material in learning.materials_for_lessons([lesson], approved_only=True):
            found.setdefault(str(material.pk), material_entry(material))
    return list(found.values())[:limit]


def lesson_materials(lesson: Any) -> list[dict]:
    return [material_entry(m) for m in learning.materials_for_lessons([lesson], approved_only=True)]


def lesson_and_stage_materials(lesson: Any, *, limit: int = 5) -> list[dict]:
    """The lesson's own approved materials first, then the learner's current-stage materials."""
    found = {m["id"]: m for m in lesson_materials(lesson)}
    for material in stage_materials(lesson.student, limit=limit):
        found.setdefault(material["id"], material)
    return list(found.values())[:limit]


def keywords(text: str) -> set[str]:
    return {word for word in WORD.findall(text.lower()) if word not in STOPWORDS}


def rank_materials(materials: list[dict], question: str) -> list[dict]:
    """Order materials by how many question keywords they contain; ties keep the stage order."""
    words = keywords(question)
    if not words:
        return list(materials)

    def score(material: dict) -> int:
        text = f"{material['title']} {material['locator']} {material['content']}".lower()
        return sum(1 for word in words if word in text)

    return sorted(materials, key=score, reverse=True)
