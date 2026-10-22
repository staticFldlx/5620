"""Pipeline table: request type -> ordered task types (spec 5.2).

The execution logic is shared; the table content is maintained by the Coordinator owner and
each agent owner registers its task types here by PR. Task type format: <agent_id>.<verb_noun>.

Human checkpoints are not listed as steps: an agent returns NEEDS_ESCALATION or AWAITING_APPROVAL
with payload["resume"] = <task_type>, and the EscalationManager enqueues that task after the
human decision (see docs/shared-conventions.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from domain.common import DomainError, Role
from domain.learning import selectors as learning

StudentScope = Literal["self", "self_or_student_id", "student_id", "lesson", "none"]
REPLAN_TASK = "planning.revise_plan"


@dataclass(frozen=True)
class Pipeline:
    request_type: str
    steps: tuple[str, ...]
    roles: frozenset[str]
    student_scope: StudentScope
    precheck: Callable[[Any, dict], None] | None = None
    public: bool = True  # False: internal, not accepted by POST /requests


def target_agent(task_type: str) -> str:
    return task_type.split(".", 1)[0]


# --- prechecks: data invariants checked before anything is queued (409 on violation) ---------
def _needs_active_plan_without_pending(student: Any, _input: dict) -> None:
    if learning.active_plan(student) is None:
        raise DomainError("no_active_plan", "There is no active learning plan to revise yet.")
    if learning.pending_plan(student) is not None:
        raise DomainError("plan_review_pending", "Wait for the current plan review before requesting another revision.")


def _needs_active_plan(student: Any, _input: dict) -> None:
    if learning.active_plan(student) is None:
        raise DomainError("no_active_plan", "There is no active learning plan yet.")


def _needs_goal(student: Any, _input: dict) -> None:
    profile = learning.profile_for(student)
    if profile is None or not profile.learning_goal.strip():
        raise DomainError("profile_incomplete", "Confirm a learning goal before assessment.")


def _needs_own_lesson(student: Any, data: dict) -> None:
    lesson_id = data.get("lesson_id")
    lesson = learning.lesson(lesson_id) if lesson_id else None
    if lesson_id and (lesson is None or lesson.student_id != student.pk):
        raise DomainError("lesson_not_found", "Lesson not found.", status=404)


def _needs_own_approved_material(student: Any, data: dict) -> None:
    material = learning.material(data.get("material_id"))
    if material is None or material.status != "approved" or material.lesson.student_id != student.pk:
        raise DomainError("material_not_found", "Material not found.", status=404)


S, T, F = Role.STUDENT.value, Role.TEACHER.value, Role.FOUNDER.value

_TABLE = [
    # Student requests: Coordinator entry (AR11)
    Pipeline("collect_goal", ("coordinator.collect_goal",), frozenset({S}), "self"),
    Pipeline("confirm_goal", ("coordinator.confirm_goal",), frozenset({S}), "self"),
    Pipeline("complete_material", ("coordinator.record_material_completion",), frozenset({S}), "self", _needs_own_approved_material),
    Pipeline("explain", ("teaching_support.answer_question",), frozenset({S}), "self"),
    Pipeline("resources", ("teaching_support.retrieve_material",), frozenset({S}), "self"),
    Pipeline("practice", ("teaching_support.generate_practice",), frozenset({S}), "self"),
    Pipeline("practice_answer", ("teaching_support.give_feedback",), frozenset({S}), "self"),
    Pipeline("revise_plan", ("planning.revise_plan",), frozenset({S, T}), "self_or_student_id", _needs_active_plan_without_pending),
    Pipeline("reschedule", ("planning.propose_slot",), frozenset({S}), "self", _needs_own_lesson),
    Pipeline("confirm_slot", ("planning.book_slot",), frozenset({S}), "self", _needs_own_lesson),
    Pipeline("replace_teacher", ("planning.match_teacher",), frozenset({S}), "self", _needs_active_plan),
    # Teacher requests: intent is explicit, no classification (spec 5.1)
    Pipeline("review_progress", ("teaching_support.analyze_progress",), frozenset({T}), "student_id"),
    Pipeline("recommend_plan", ("teaching_support.recommend_adjustments",), frozenset({T}), "student_id"),
    Pipeline("lesson_briefing", ("teaching_support.lesson_briefing",), frozenset({T}), "lesson"),
    Pipeline("generate_material", ("teaching_support.generate_material",), frozenset({T}), "lesson"),
    # Dedicated endpoints and follow-ups (not accepted by POST /requests)
    # C1: a confirmed assessment feeds planning. With an active plan, generate_plan compares the result with the
    # milestone and may return TRIGGER_REPLAN (UC05 step 6 / 7a).
    Pipeline("start_assessment", ("assessment.conduct_assessment", "planning.generate_plan"), frozenset({S, T}), "self_or_student_id", _needs_goal, public=False),
    Pipeline("decision_follow_up", (), frozenset({T, F}), "none", public=False),
    Pipeline("agent_correction", ("tech_operations.apply_correction",), frozenset({F}), "none", public=False),
    # UC10: started by `manage.py monitor_agents` as the system, never by a user.
    Pipeline("system_monitoring", ("tech_operations.detect_anomalies",), frozenset(), "none", public=False),
]

PIPELINES: dict[str, Pipeline] = {p.request_type: p for p in _TABLE}


def get(request_type: str) -> Pipeline:
    try:
        return PIPELINES[request_type]
    except KeyError:
        raise DomainError("unknown_request_type", f"Unknown request type: {request_type}", status=400) from None
