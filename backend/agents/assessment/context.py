"""What the assessment agent perceives about a learner (shared by agent.py and fake.py)."""

from __future__ import annotations

from typing import Any

from domain.learning import selectors as learning

from . import adaptive


def learner(student: Any, kind: str) -> dict:
    """What the agent perceives about the learner. No name or email: data minimisation (spec 8.6)."""
    profile = learning.profile_for(student)
    objective = (profile.structured_objective if profile else None) or {}
    baseline = learning.latest_confirmed_proficiency(student)
    baseline_level = adaptive.parse_level(baseline.overall_level, default=None) if baseline else None
    self_level = adaptive.parse_level(profile.english_level if profile else "", default=None)
    if kind != "initial" and baseline_level:
        start, source = baseline_level, "confirmed assessment"
    elif self_level:
        start, source = self_level, "self-reported"
    else:
        start, source = adaptive.DEFAULT_LEVEL, "default"
    stage = current_stage(student) if kind == "milestone" else None
    return {
        "kind": kind,
        "goal": objective.get("summary") or (profile.learning_goal if profile else ""),
        "target_level": objective.get("target_level", ""),
        "focus_skills": list(objective.get("focus_skills") or []),
        "start_level": start,
        "level_source": source,
        "baseline_level": baseline_level,
        "stage_title": (stage or {}).get("title", ""),
        "stage_milestone": (stage or {}).get("milestone", ""),
    }


def current_stage(student: Any) -> dict | None:
    """UC05: a milestone assessment targets the active plan's current stage."""
    plan = learning.active_plan(student)
    stages = list(learning.plan_stages(plan)) if plan else []
    if not stages:
        return None
    stage = stages[min(plan.stage_index, len(stages) - 1)]
    return {"title": stage.title, "milestone": stage.milestone, "topics": list(stage.topics or [])}
