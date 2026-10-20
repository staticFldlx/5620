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

from . import adaptive, context

WORD = re.compile(r"[A-Za-z']+")
NO_ANSWER = re.compile(r"\b(i\s*don'?t\s*know|no\s*idea|idk|not\s*sure)\b", re.I)

BANK: dict[str, list[tuple[str, list[str]]]] = {
    "Reading": [
        (
            "Read: \"Many cities now close their centres to cars on Sundays. Shops first worried about losing customers, "
            "but most report more visitors on foot.\" What was the shops' first concern, and what actually happened?",
            ["Names the concern about losing customers", "States that visitors on foot increased", "Uses own words"],
        ),
        (
            "Read: \"Remote work saves commuting time, yet some employees say they feel less connected to their team.\" "
            "Explain the trade-off the writer describes and give one example of your own.",
            ["Identifies the trade-off", "Mentions feeling less connected", "Gives a relevant own example"],
        ),
        (
            "Read: \"Although the study was small, its findings challenge the assumption that bilingual children learn to read later.\" "
            "What assumption is challenged, and why should the reader be careful with the result?",
            ["States the assumption about bilingual children", "Notes the small study size", "Explains the need for caution"],
        ),
    ],
    "Writing": [
        (
            "Write 3-4 sentences to a colleague asking to move tomorrow's meeting to Friday. Give a reason and suggest a time.",
            ["Clear request to move the meeting", "Gives a reason", "Suggests a time", "Polite tone"],
        ),
        (
            "Write a short paragraph (4-5 sentences) arguing whether students should learn a second language at school. "
            "State your claim and support it with one piece of evidence.",
            ["States a clear claim", "Supports it with evidence", "Explains how the evidence supports the claim"],
        ),
        (
            "Write a short paragraph that presents one counter-argument to your own view on online exams and then responds to it.",
            ["Presents a counter-argument fairly", "Responds to it", "Uses linking words"],
        ),
    ],
    "Grammar": [
        (
            "Correct the mistakes and rewrite the sentences: \"Yesterday I go to the market and buyed some apple. It were very cheap.\"",
            ["Uses past tense went/bought", "Plural apples", "Was instead of were"],
        ),
        (
            "Combine into one sentence using a relative clause: \"The report was late. My manager wrote the report.\" "
            "Then write one sentence of your own with 'which'.",
            ["Correct relative clause", "Own sentence uses which correctly"],
        ),
        (
            "Rewrite in the passive and explain when the passive is a better choice: \"The committee will announce the results next week.\"",
            ["Correct future passive", "Explains focus on the action or result"],
        ),
    ],
    "Vocabulary": [
        (
            "Use each of these words in a sentence about your daily life: 'schedule', 'deadline', 'improve'.",
            ["Uses schedule correctly", "Uses deadline correctly", "Uses improve correctly"],
        ),
        (
            "Explain the difference between 'affect' and 'effect' and write one example sentence for each.",
            ["Explains affect as a verb", "Explains effect as a noun", "Two correct example sentences"],
        ),
        (
            "Replace the informal words in this sentence with academic ones and explain your choices: \"Lots of people think this idea is really bad.\"",
            ["Uses many or numerous", "Uses argue or consider", "Uses a precise evaluative word"],
        ),
    ],
}


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
        return [_item(adaptive.skill_for(skills, 1), level, 1)]

    session_id = ((payload.get("previous") or {}).get("result") or {}).get("session_id")
    session = learning.assessment_session(session_id) if session_id else None
    if session is None:
        return []
    items = [dict(i) for i in session.items]
    current = next((i for i in items if i.get("item_id") == reply.get("item_id") and i.get("answer") is None), None)
    if current is None:
        return []
    scored = score_reply(str(reply.get("answer", "")), current)
    current.update(answer=reply.get("answer"), score=scored["score"], estimate=adaptive.estimate(adaptive.level_index(current["level"]), scored["score"]))
    answered = [i for i in items if i.get("answer") is not None]
    estimates = [i["estimate"] for i in answered if i.get("estimate") is not None]
    if adaptive.stop_reason(estimates, len(answered), session.max_items):
        return [scored, _report(answered, adaptive.final_level(estimates))]
    next_level = adaptive.level_name(adaptive.next_index(adaptive.level_index(current["level"]), scored["score"]))
    planned = items[0].get("planned_skills") or list(adaptive.TEXT_SKILLS)
    number = len(items) + 1
    return [scored, _item(adaptive.skill_for(planned, number), next_level, number)]


def score_reply(answer: str, item: dict) -> dict[str, Any]:
    words = len(WORD.findall(answer))
    points = list(item.get("expected_points") or [])
    if words < 3 or NO_ANSWER.search(answer):
        return {"score": 0.05, "met_points": [], "feedback": "Try to answer every part of the question in full sentences.", "off_task": True}
    needed = 10 + 4 * adaptive.level_index(item.get("level"))  # A1: 10 words ... C2: 30 words
    score = round(min(words / needed, 1.0) * 0.95, 2)
    met = points[: round(score * len(points))]
    feedback = "Clear and complete answer." if score >= 0.75 else "Good start; add more detail and explain your reasoning."
    return {"score": score, "met_points": met, "feedback": feedback, "off_task": False}


def _item(skill: str, level: str, number: int) -> dict:
    options = BANK[skill]
    band = min(adaptive.level_index(level) // 2, len(options) - 1)  # A -> 0, B -> 1, C -> 2
    repeat = (number - 1) // len(adaptive.TEXT_SKILLS)  # a skill's second item uses the next prompt, not the same one
    prompt, points = options[(band + repeat) % len(options)]
    return {"prompt": f"[{level} {skill}] {prompt}", "expected_points": points}


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
