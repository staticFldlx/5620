"""Offline replies for LLM_PROVIDER=fake (spec 8.10): goal intake follows simple keyword rules, so the
demo is repeatable without a network. Each reply is the JSON the real model would return."""

from __future__ import annotations

import json
import re

from agents.runtime import TaskInput

from .prompts import DAY_PATTERN

MIN_GOAL_WORDS = 8
DEFAULT_TIMES = ("18:00", "20:00")  # a day without times means an evening lesson
PURPOSE_QUESTION = "What do you need English for, and by when?"
TIMES_QUESTION = "Which days and times can you take a lesson each week? (for example: Tue 18:00-20:00)"
DOMAIN_WORDS = (
    ("Exam preparation", ("exam", "ielts", "toefl", "pte", "cambridge")),
    ("Academic English", ("study", "university", "master", "degree", "academic", "essay", "thesis", "seminar", "phd")),
    ("Workplace English", ("work", "job", "interview", "office", "meeting", "career", "business", "colleague")),
)
SKILL_WORDS = {
    "Reading": ("read", "article", "paper"),
    "Writing": ("writ", "essay", "email", "report"),
    "Speaking": ("speak", "talk", "interview", "seminar", "presentation", "meeting"),
    "Listening": ("listen", "lecture"),
}
_DAY = re.compile(rf"\b{DAY_PATTERN}\b", re.I)
_TIME = re.compile(r"(\d{1,2}):?(\d{2})?\s*(?:-|–|to)\s*(\d{1,2}):?(\d{2})?")


def script(task: TaskInput) -> list:
    if task.task_type == "coordinator.collect_goal":
        return [_reading] * 2  # the second reply covers the runtime's validation retry
    return []


def _reading(**call) -> dict:
    content = call["messages"][0].content
    intake = json.loads(content[content.index("{") : content.rindex("}") + 1])
    goal = str(intake.get("goal_text", ""))
    answers = [str(a.get("answer", "")) for a in intake.get("answers", [])]
    text = " ".join([goal, *answers])
    profile = intake.get("current_profile") or {}
    times = _windows(text) or [f"{w['day']} {w['start']}-{w['end']}" for w in profile.get("availability") or []]
    left = int(intake.get("follow_ups_left", 0))

    if left > 0 and len(goal.split()) < MIN_GOAL_WORDS and not answers:
        return {"enough": False, "follow_up_question": PURPOSE_QUESTION}
    if left > 0 and not times:
        return {"enough": False, "follow_up_question": TIMES_QUESTION}

    lower = text.lower()
    domain = next((name for name, words in DOMAIN_WORDS if any(w in lower for w in words)), "Everyday English")
    basis = goal if len(goal.split()) >= MIN_GOAL_WORDS or not answers else answers[0]  # a short goal: use the answer
    purpose = " ".join(basis.split()[:10]).rstrip(".,;")
    skills = list(intake.get("selected_focus_skills") or [])
    skills += [s for s, words in SKILL_WORDS.items() if s not in skills and any(w in lower for w in words)]
    level = re.search(r"\b([ABC][12])\b", text.upper())
    return {
        "enough": True,
        "summary": f"{domain}: {purpose}"[:90],
        "focus_skills": skills or ["Reading", "Writing"],
        "target_level": level.group(1) if level else "",
        "learning_needs": f"{domain} for the stated goal, plus everyday English for life around it.",
        "availability": times,
    }


def _windows(text: str) -> list[str]:
    """"Tuesday and Thursday 18-20" -> ["Tue 18:00-20:00", "Thu 18:00-20:00"]."""
    days = list(dict.fromkeys(m[:3].title() for m in _DAY.findall(text)))
    if not days:
        return []
    time = _TIME.search(text)
    start, end = DEFAULT_TIMES
    if time:
        h1, m1, h2, m2 = time.groups()
        start, end = f"{int(h1):02d}:{m1 or '00'}", f"{int(h2):02d}:{m2 or '00'}"
    return [f"{day} {start}-{end}" for day in days]
