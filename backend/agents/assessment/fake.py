"""Offline replies for LLM_PROVIDER=fake (spec 8.10): the assessment demo runs without network.

The Orchestrator asks for the script before the task runs, so this module replays the agent's own
rules (adaptive.py) to know which calls come next:
  first task        -> [item 1]
  each answer       -> [score, next item]  or  [score, report] when the assessment stops
  apply_review      -> []  (no LLM call)
Scores are deterministic: a longer, complete answer scores higher, and harder levels need longer
answers. Steady answers converge and are published; answers that swing between long and short,
or "I don't know", give an unstable estimate and go to the teacher - the two demo paths.
"""

from __future__ import annotations

import re
from typing import Any

from agents.runtime import TaskInput
from domain.learning import selectors as learning

from . import adaptive, bank, context

WORD = re.compile(r"[A-Za-z']+")
NO_ANSWER = re.compile(r"\b(i\s*don'?t\s*know|no\s*idea|idk|not\s*sure)\b", re.I)

def script(task: TaskInput) -> list:
    if task.task_type != "assessment.conduct_assessment":
        return []
    payload = task.payload or {}
    reply = payload.get("reply")
    if not reply:
        learner = _learner(task)
        if learner is None:
            return []
        skills, _ = adaptive.plan_skills(learner["focus_skills"], str(payload.get("input", {}).get("focus", "")))
        level = learner["start_level"]
        return [_item(adaptive.skill_for(skills, 1), level, 1, len(skills))]

    session_id = ((payload.get("previous") or {}).get("result") or {}).get("session_id")
    session = learning.assessment_session(session_id) if session_id else None
    if session is None:
        return []
    items = [dict(i) for i in session.items]
    current = next((i for i in items if i.get("item_id") == reply.get("item_id") and i.get("answer") is None), None)
    if current is None:
        return []
    scored = score_reply(str(reply.get("answer", "")), current)
    score, _ = adaptive.combine(current["level"], scored["score"], scored["demonstrated_level"], len(scored["met_points"]), len(current.get("expected_points") or []), scored["off_task"])
    replies: list = [scored]
    if not scored["off_task"] and adaptive.needs_second_opinion(score):
        replies.append(scored)  # the agent asks twice near a threshold; the fake scorer is deterministic
    current.update(answer=reply.get("answer"), score=score, estimate=adaptive.estimate(adaptive.level_index(current["level"]), score))
    answered = [i for i in items if i.get("answer") is not None]
    estimates = [i["estimate"] for i in answered if i.get("estimate") is not None]
    if adaptive.stop_reason(estimates, len(answered), session.max_items):
        return [*replies, _report(answered, adaptive.final_level(estimates))]
    next_level = adaptive.level_name(adaptive.next_index(adaptive.level_index(current["level"]), score))
    planned = items[0].get("planned_skills") or list(adaptive.TEXT_SKILLS)
    number = len(items) + 1
    return [*replies, _item(adaptive.skill_for(planned, number), next_level, number, len(planned))]


def score_reply(answer: str, item: dict) -> dict[str, Any]:
    words = len(WORD.findall(answer))
    points = list(item.get("expected_points") or [])
    level = item.get("level")
    if words < 3 or NO_ANSWER.search(answer):
        return {"demonstrated_level": "A1", "score": 0.05, "met_points": [], "feedback": "Try to answer every part of the question in full sentences.", "off_task": True}
    needed = 10 + 4 * adaptive.level_index(level)  # A1: 10 words ... C2: 30 words
    score = round(min(words / needed, 1.0) * 0.95, 2)
    met = points[: round(score * len(points))]
    # the level the fake "sees": one up for a clearly strong answer, one down for a weak one
    shift = 1 if score >= 0.8 else -1 if score < 0.2 else 0
    shown = adaptive.level_name(adaptive.level_index(level) + shift)
    feedback = "Clear and complete answer." if score >= 0.75 else "Good start; add more detail and explain your reasoning."
    return {"demonstrated_level": shown, "score": score, "met_points": met, "feedback": feedback, "off_task": False}


def _item(skill: str, level: str, number: int, planned: int) -> dict:
    """Bank item with a visible [level skill] tag, so the offline demo shows the difficulty moving."""
    picked = bank.item(skill, level, number, planned)
    return {**picked, "prompt": f"[{level} {skill}] {picked['prompt']}"}


def _report(answered: list[dict], level: str) -> dict:
    by_skill: dict[str, list[float]] = {}
    for item in answered:
        if item.get("score") is not None:
            by_skill.setdefault(item["skill"], []).append(item["score"])
    means = {s: sum(v) / len(v) for s, v in by_skill.items()}
    strengths = [f"{s}: complete, well-developed answers" for s, m in means.items() if m >= 0.7][:3]
    weaknesses = [f"{s}: answers need more detail" for s, m in means.items() if m < 0.7][:3]
    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "gap_to_goal": f"Working at {level}; extend answers with explanation and evidence to reach the target level.",
        "feedback": f"Your answers place you at {level}. Keep practising longer, structured answers in your weaker skills.",
    }


def _learner(task: TaskInput) -> dict | None:
    student = learning.student(task.student_id) if task.student_id else None
    return context.learner(student, str(task.payload.get("input", {}).get("kind", "initial"))) if student else None
