"""Offline replies for LLM_PROVIDER=fake (spec 8.10): the demo still runs without network.

The texts are the ones the frontend mock (frontend/src/mocks/handlers.ts) used, so pages look
the same as before. Each script is the JSON the real model would return for the task's prompt.
"""

from __future__ import annotations

import re

from agents.runtime import TaskInput
from domain.learning import selectors as learning

from . import context

NEEDS_TEACHER = re.compile(r"unpublished|permission|copyright|未经|引用录音", re.I)


def _material_ids(task: TaskInput, limit: int = 2) -> list[str]:
    student = learning.student(task.student_id) if task.student_id else None
    return [m["id"] for m in context.stage_materials(student)][:limit] if student else []


def _replies(task: TaskInput) -> list[dict]:
    data = task.payload.get("input", {})
    kind = task.task_type.split(".", 1)[1]
    if kind == "answer_question":
        if NEEDS_TEACHER.search(str(data.get("question", ""))):
            return [
                {
                    "answer": "The available sources do not establish the permission rules. Your teacher will review this question.",
                    "cited_material_ids": [],
                    "self_confidence": 0.41,
                    "in_scope": True,
                    "needs_teacher": True,
                    "reason": "Citation permission is a teacher decision.",
                }
            ]
        return [
            {
                "answer": "Use a short because bridge: state the evidence, explain what it shows, then connect it to your claim.",
                "cited_material_ids": _material_ids(task),
                "self_confidence": 0.89,
                "in_scope": True,
                "needs_teacher": False,
                "reason": "Covered by the current stage materials.",
            }
        ]
    if kind == "retrieve_material":
        return [
            {
                "guide": "Start with the approved Academic Argument Guide and Evidence & Commentary. Each resource is linked to your current stage.",
                "material_ids": _material_ids(task),
            }
        ]
    if kind == "generate_practice":
        ids = _material_ids(task, 1)
        return [
            {
                "question": "Write one sentence that explains how evidence supports your main claim.",
                "expected_points": ["States the evidence", "Explains what the evidence shows", "Links it to the claim with because"],
                "material_id": ids[0] if ids else "",
            }
        ]
    if kind == "give_feedback":
        long_enough = len(str(data.get("answer", "")).strip()) > 30
        return [
            {
                "feedback": "Good connection. You explained how the evidence supports the claim."
                if long_enough
                else "Add a because bridge and explain what the evidence shows.",
                "met_points": ["Links it to the claim with because"] if long_enough else [],
                "missing_points": [] if long_enough else ["Explains what the evidence shows"],
            }
        ]
    if kind == "analyze_progress":
        return [
            {
                "analysis": "Stage 2 (Argumentative writing) is in progress. Reading is a stable strength; explicit evidence-to-claim links remain the main weakness. "
                "The latest milestone result is provisional until it is reviewed.",
                "evidence": ["Confirmed initial assessment", "Provisional milestone assessment", "Latest lesson feedback"],
                "missing_data": [],
                "suggest_directed_assessment": False,
            }
        ]
    if kind == "recommend_adjustments":
        return [
            {
                "recommendations": [
                    "Add guided evidence-linking practice to the current stage, because the last two results show the same weakness.",
                    "Keep the weekly hours; review progress again after the milestone result is confirmed.",
                ],
                "evidence": ["Weak area: explicit evidence links", "Teacher observation"],
            }
        ]
    if kind == "lesson_briefing":
        return [
            {
                "briefing": "Focus on evidence-to-claim connections. The latest feedback asks for a clearer explanation of significance.",
                "material_ids": _material_ids(task),
            }
        ]
    if kind == "generate_material":
        return [
            {
                "title": str(data.get("title") or data.get("topic") or "Evidence linking practice"),
                "content": "Model: The claim is supported by the evidence because the observation explains the underlying reason. Add a source citation before use.",
                "cited_material_ids": [],
            }
        ]
    return []


def script(task: TaskInput) -> list[dict]:
    try:
        return _replies(task)
    except Exception:  # an offline script must never break task execution
        return []
