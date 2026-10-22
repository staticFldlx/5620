"""AI Course Coordinator (IRequestRouting, Fig 6a): AR01, AR11; UC01.

Perceive  the goal text, the selected skills, the current profile (a returning student, UC01 2a)
          and the answers to earlier follow-up questions.
Decide    whether the goal is clear enough to plan against: the purpose and weekly lesson times.
          If not, ask one follow-up question (UC01 3a, at most MAX_FOLLOW_UPS); otherwise turn it
          into a structured objective whose summary names the domain the teachers declare
          (Academic English, Workplace English, ...), so the Course Consultant can match a teacher.
Act       save the profile the student confirmed and hand over to the initial assessment
          (UC01 steps 4-6); record completed materials in the learning history.

Routing itself is the pipeline table (orchestration/task_queue/pipelines.py): the frontend sends an
explicit request type, so there is no LLM classification (deviation A13). consolidate_response() is
not defined, so the Task Orchestrator merges the task results in order.

Reason codes: invalid_goal, student_not_found, material_not_found (all FAILED). A follow-up question
is NEEDS_INPUT with phase "follow_up_question"; the student replies through context_id.
"""

from __future__ import annotations

from typing import Any

from agents.runtime import AgentResult, AgentStatus, AIAgent, TaskInput
from domain.common import iso
from domain.governance import selectors as governance
from domain.learning import selectors as learning
from domain.learning import services as learning_services
from domain.learning.views import profile_view

from . import fake, prompts

AGENT_ID = "coordinator"
MAX_FOLLOW_UPS = 2
SUMMARY_CHARS = 90
MAX_WEEKLY_HOURS = 40
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


class CoordinatorAgent(AIAgent):
    agent_id = AGENT_ID
    task_types = ("coordinator.collect_goal", "coordinator.confirm_goal", "coordinator.record_material_completion")

    @staticmethod
    def fake_script(task: TaskInput) -> list:
        return fake.script(task)

    def execute_task(self, task: TaskInput) -> AgentResult:
        student = learning.student(task.student_id) if task.student_id else None
        if student is None:
            return _failed("student_not_found", "Student not found.")
        handler = getattr(self, "_" + task.task_type.split(".", 1)[1])
        return handler(task, student)

    # --- coordinator.collect_goal (UC01 steps 1-3, 3a) --------------------------------------------
    def _collect_goal(self, task: TaskInput, student: Any) -> AgentResult:
        data = task.payload.get("input") or {}
        goal = str(data.get("goal_text", "")).strip()
        if not goal:
            return _failed("invalid_goal", "Describe what you are learning English for.")
        selected = [str(skill) for skill in data.get("focus_skills") or []]

        # A reply carries the previous round's payload: the questions asked so far and their answers.
        previous = task.payload.get("previous") or {}
        answers = list(previous.get("answers") or [])
        reply = task.payload.get("reply")
        if reply is not None:
            asked = str((previous.get("result") or {}).get("question", ""))
            answers.append({"question": asked, "answer": prompts.as_data(str(reply.get("answer", "")).strip())})

        profile = learning.profile_for(student)
        returning = bool(profile and profile.learning_goal.strip())
        left = max(0, MAX_FOLLOW_UPS - len(answers))
        self.runtime.note("intake_read", returning_student=returning, answers=len(answers), follow_ups_left=left)
        intake = {
            "goal_text": prompts.as_data(goal),
            "selected_focus_skills": selected,
            "current_profile": _profile_context(profile) if returning else None,
            "answers": answers,
            "follow_ups_left": left,
        }
        self.runtime.note("prompt", id=prompts.PROMPT_ID)
        reading = self.runtime.structured(prompts.SYSTEM, [prompts.user_message(intake)], prompts.GoalReading, max_tokens=prompts.MAX_TOKENS)

        if reading is None:  # the model is unavailable: keep the student going with their own words
            self.runtime.note("goal_reading_fallback", llm=self._llm_failure_reason())
            draft = {"summary": goal[:SUMMARY_CHARS], "focus_skills": selected, "target_level": "", "learning_needs": "", "availability": []}
            return _summary(draft, answers)

        question = reading.follow_up_question.strip()
        if not reading.enough and question and left > 0:
            self.runtime.note("follow_up_asked", question=question, follow_ups_left=left - 1)
            return AgentResult(AgentStatus.NEEDS_INPUT, {"result": {"question": question}, "phase": "follow_up_question", "answers": answers})

        suggested = [s.strip().title() for s in reading.focus_skills if s.strip().title() in prompts.SKILLS]
        skills = list(dict.fromkeys([*selected, *suggested]))
        level = reading.target_level.strip().upper()
        draft = {
            "summary": (reading.summary.strip() or goal)[:SUMMARY_CHARS],
            "focus_skills": skills,
            "target_level": level if level in LEVELS else "",
            "learning_needs": reading.learning_needs.strip()[:500],
            "availability": prompts.parse_windows(reading.availability),
        }
        self.runtime.note("goal_structured", summary=draft["summary"], focus_skills=skills, availability=draft["availability"], questions_left=left, forced=not reading.enough)
        return _summary(draft, answers)

    # --- coordinator.confirm_goal (UC01 steps 4-6) -------------------------------------------------
    def _confirm_goal(self, task: TaskInput, student: Any) -> AgentResult:
        data = task.payload.get("input") or {}
        profile = learning.profile_for(student)
        goal = str(data.get("goal_text") or (profile.learning_goal if profile else "")).strip()
        summary = str(data.get("goal_summary") or data.get("confirmed_summary") or "").strip()
        if not goal or not summary:
            return _failed("invalid_goal", "Organise your goal and check the summary before confirming it.")
        try:
            hours = float(data["weekly_hours"]) if data.get("weekly_hours") is not None else float(profile_view(profile)["weekly_hours"])
        except (TypeError, ValueError):
            return _failed("invalid_goal", "Weekly hours must be a number.")
        if not 1 <= hours <= MAX_WEEKLY_HOURS:
            return _failed("invalid_goal", f"Weekly hours must be between 1 and {MAX_WEEKLY_HOURS}.")
        levels = {}
        for key in ("self_level", "target_level"):
            value = str(data.get(key) or "").strip().upper()
            if value and value not in LEVELS:
                return _failed("invalid_goal", f"{key.replace('_', ' ').capitalize()} must be a CEFR level (A1-C2).")
            levels[key] = value

        # The intake draft (lesson times, needs) applies only to the summary the student saw and confirmed.
        draft = (governance.latest_task_result(student, "coordinator.collect_goal") or {}).get("draft") or {}
        if draft.get("summary") != summary:
            draft = {}
        preferences: dict[str, Any] = {"weekly_hours": int(hours) if hours.is_integer() else hours}
        if draft.get("availability"):
            preferences["availability"] = draft["availability"]
        fields: dict[str, Any] = {
            "learning_goal": goal[:4000],
            "english_level": levels["self_level"],
            "structured_objective": {
                "summary": summary[:200],
                # No skill selected on the page: keep the skills the Coordinator suggested for this summary.
                "focus_skills": [str(skill) for skill in data.get("focus_skills") or []] or list(draft.get("focus_skills") or []),
                "target_level": levels["target_level"] or draft.get("target_level", ""),
            },
            "preferences": preferences,
        }
        if draft.get("learning_needs"):
            fields["learning_needs"] = draft["learning_needs"]

        if profile is None:
            preferences.setdefault("timezone", learning_services.DEFAULT_TIMEZONE)
            preferences.setdefault("availability", [])
            profile = learning_services.create_profile(AGENT_ID, student=student, **fields)
        else:
            profile = learning_services.update_profile(AGENT_ID, profile, **fields)

        # UC01 step 6: without a confirmed level the next step is the initial assessment.
        assessed = learning.latest_confirmed_proficiency(student) is not None
        phase = "profile_updated" if assessed else "initial_assessment_next"
        self.runtime.note("profile_saved", availability_from_intake=bool(draft.get("availability")), next=phase)
        return AgentResult(AgentStatus.OK, {"result": {"profile": profile_view(profile)}, "phase": phase})

    # --- coordinator.record_material_completion ----------------------------------------------------
    def _record_material_completion(self, task: TaskInput, student: Any) -> AgentResult:
        material = learning.material(str((task.payload.get("input") or {}).get("material_id", "")))
        if material is None or material.status != "approved" or material.lesson.student_id != student.pk:
            return _failed("material_not_found", "Material not found.")
        entry = next(
            (e for e in learning.history(student, kinds=("material_completed",)) if (e.payload or {}).get("material_id") == str(material.pk)),
            None,
        )
        if entry is None:
            entry = learning_services.append_history(
                AGENT_ID, student=student, kind="material_completed", payload={"material_id": str(material.pk), "title": material.title}
            )
        else:
            self.runtime.note("material_already_recorded", material_id=str(material.pk))
        record = {"id": str(material.pk), "title": material.title, "locator": material.locator, "completed_at": iso(entry.created_at)}
        return AgentResult(AgentStatus.OK, {"result": {"material": record}})

    def _llm_failure_reason(self) -> str:
        unavailable = any(step.get("step") == "llm" and step.get("stop") == "error" for step in self.runtime.trace)
        return "llm_unavailable" if unavailable else "invalid_llm_output"


# --- helpers ----------------------------------------------------------------------------------------
def _profile_context(profile: Any) -> dict:
    """What a returning student already told us; no name, email or user id (spec 8.6)."""
    view = profile_view(profile)
    return {
        "goal_text": prompts.as_data(view["goal_text"]),
        "goal_summary": prompts.as_data(view["goal_summary"]),
        "focus_skills": view["focus_skills"],
        "self_level": view["self_level"],
        "target_level": view["target_level"],
        "weekly_hours": view["weekly_hours"],
        "availability": view["availability"],
    }


def _summary(draft: dict, answers: list[dict]) -> AgentResult:
    """The summary shown for confirmation; the draft stays in the task result for confirm_goal.

    The request result merges every round, so `question: None` clears the last follow-up question.
    """
    result = {"summary": draft["summary"], "focus_skills": draft["focus_skills"], "question": None}
    return AgentResult(AgentStatus.OK, {"result": result, "draft": draft, "answers": answers})


def _failed(reason: str, message: str) -> AgentResult:
    return AgentResult(AgentStatus.FAILED, {"message": message}, reason=reason)
