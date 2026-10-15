"""AI Teaching Assistant (ITeachingSupport, Fig 6a): AR04, AR05, AR06-AR08; UC04-UC08.

No RAG: the "retrieval" step selects approved materials of the learner's current stage
from the database (context.py) and puts them in the prompt. Every task is one structured
LLM call, except answer_question in loop mode (TEACHING_SUPPORT_EXPLAIN_MODE=loop), where the
model looks things up with read-only tools first. Writes happen last so a re-queued task
stays idempotent (spec 8.5).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from pydantic import BaseModel, ValidationError

from agents.runtime import AgentResult, AgentStatus, AIAgent, LoopSpec, TaskInput
from agents.runtime.loop import parse_json_object
from domain.governance import services as governance_services
from domain.learning import selectors as learning
from domain.learning import services as learning_services
from domain.learning.views import interaction_view, material_view

from . import context, fake, prompts
from .schemas import ExplainOutput, LessonBriefing, MaterialDraft, PlanRecommendations, PracticeFeedback, PracticeItem, ProgressAnalysis, ResourceGuide
from .tools import ExplainTools

AGENT_ID = "teaching_support"

# Answer confidence (UC04): the model's own estimate, whether a provided material backs the answer,
# and whether the question is in scope. The escalation threshold itself is the shared one.
CONFIDENCE_WEIGHTS = {"model": 0.5, "grounding": 0.3, "scope": 0.2}
UNCITED_GROUNDING = 0.6  # in-scope general-knowledge answers are allowed but count for less
NOT_CITED_NOTE = "(Not based on course materials.)"
LOOP_MAX_STEPS = 4
NO_MATERIALS_REPLY = (
    "There are no approved materials for your current stage yet. The gap has been logged so suitable materials "
    "can be added. You can still ask me questions about this stage."
)
HOLDING_REPLY = {
    "needs_teacher": "This question needs your teacher's decision. Your teacher will review it and reply here.",
    "out_of_scope": "This question is outside your current English learning plan. Your teacher will review it and reply here.",
    "low_confidence": "I'm not confident enough to answer this one. Your teacher will review it and reply here.",
    "llm_unavailable": "I couldn't answer right now. Your teacher will review your question and reply here.",
    "invalid_llm_output": "I couldn't answer right now. Your teacher will review your question and reply here.",
}


class TeachingSupportAgent(AIAgent):
    agent_id = AGENT_ID
    task_types = (
        "teaching_support.answer_question",
        "teaching_support.retrieve_material",
        "teaching_support.generate_practice",
        "teaching_support.give_feedback",
        "teaching_support.analyze_progress",
        "teaching_support.recommend_adjustments",
        "teaching_support.lesson_briefing",
        "teaching_support.generate_material",
    )

    @staticmethod
    def fake_script(task: TaskInput) -> list:
        return fake.script(task)

    def execute_task(self, task: TaskInput) -> AgentResult:
        handler = getattr(self, "_" + task.task_type.split(".", 1)[1])
        return handler(task)

    # --- student-facing (UC04, UC05) ------------------------------------------------------------
    def _answer_question(self, task: TaskInput) -> AgentResult:
        """UC04: answer at the learner's level with sources; escalate when unsure, out of scope or sensitive (AR13)."""
        student = self._student(task)
        if student is None:
            return _failed("student_not_found", "Student not found.")
        question = str(task.payload.get("input", {}).get("question", "")).strip()
        if settings.TEACHING_SUPPORT_EXPLAIN_MODE == "loop":
            return self._answer_with_loop(student, question)
        materials = context.stage_materials(student)
        self.runtime.note("materials_selected", material_ids=[m["id"] for m in materials])
        output = self._ask(prompts.EXPLAIN, ExplainOutput, context=context.learner(student), materials=materials, student_input=question)
        return self._answer_from(student, question, output, materials)

    def _answer_with_loop(self, student: Any, question: str) -> AgentResult:
        """The model decides what to read (tool loop); a single call takes over if the loop does not end cleanly."""
        tools = ExplainTools(student)
        spec = LoopSpec(
            system=prompts.EXPLAIN_LOOP.system,
            tools=tools.specs(),
            max_steps=LOOP_MAX_STEPS,
            tier=prompts.EXPLAIN_LOOP.tier,
            max_tokens=prompts.EXPLAIN_LOOP.max_tokens,
            time_budget_s=settings.TEACHING_SUPPORT_LOOP_BUDGET_SECONDS,
        )
        self.runtime.note("prompt", id=prompts.EXPLAIN_LOOP.id)
        loop = self.runtime.run_tool_loop(spec, [prompts.user_message(student_input=question)])
        output = None
        if loop.stopped == "end":
            try:
                output = ExplainOutput.model_validate(parse_json_object(loop.final_text) or {})
            except ValidationError:
                output = None
        if output is not None:
            self.runtime.note("loop_answered", tool_calls=len(loop.tool_results), materials_read=list(tools.read))
            return self._answer_from(student, question, output, list(tools.read.values()))
        self.runtime.note("fallback_to_single", reason=loop.stopped if loop.stopped != "end" else "invalid_final_output", tool_calls=len(loop.tool_results))
        materials = list(tools.available.values())
        output = self._ask(prompts.EXPLAIN, ExplainOutput, context=context.learner(student), materials=materials, student_input=question)
        return self._answer_from(student, question, output, materials)

    def _answer_from(self, student: Any, question: str, output: ExplainOutput | None, materials: list[dict]) -> AgentResult:
        """Shared by the single-call and loop modes: citation check, confidence, escalation, history record."""
        if output is None:
            reason = self._llm_failure_reason()
            return self._escalate_question(
                student,
                question,
                reason=reason,
                trigger="The AI service could not answer this question.",
                confidence=None,
                payload={"answer": HOLDING_REPLY[reason]},
            )
        refs = _refs(output.cited_material_ids, materials)
        answer = output.answer.strip()
        if not refs:
            answer = f"{answer} {NOT_CITED_NOTE}"
        signals = {
            "model": min(max(output.self_confidence, 0.0), 1.0),
            "grounding": 1.0 if refs else UNCITED_GROUNDING,
            "scope": 1.0 if output.in_scope else 0.0,
        }
        confidence = self.runtime.calculate_confidence(signals, CONFIDENCE_WEIGHTS)
        if output.needs_teacher:
            reason, trigger = "needs_teacher", f"Needs a teacher's decision: {output.reason or 'sensitive question'}"
        elif not output.in_scope:
            reason, trigger = "out_of_scope", f"Outside the learning scope: {output.reason or 'not an English-learning question'}"
        elif self.runtime.is_low_confidence(confidence):
            reason, trigger = "low_confidence", f"Confidence {confidence:.2f} is below the review threshold."
        else:
            reason = trigger = ""
        self.runtime.note("confidence", signals=signals, confidence=confidence, cited=[r["material_id"] for r in refs], escalate=bool(reason), reason=reason or None)
        payload = {"answer": answer, "source_refs": refs}
        if reason:
            # the learner sees a holding reply, not an unconfirmed AI answer; the draft is kept for the record
            payload = {"answer": HOLDING_REPLY[reason], "draft_answer": answer, "draft_source_refs": refs}
            return self._escalate_question(student, question, reason=reason, trigger=trigger, confidence=confidence, payload=payload)
        entry = learning_services.append_history(
            AGENT_ID,
            student=student,
            kind="explain",
            payload={"question": question, **payload, "prompt": prompts.EXPLAIN.id},
            confidence=confidence,
        )
        return _ok({"interaction": interaction_view(entry)}, summary="Answered a learning question.", confidence=confidence)

    def _escalate_question(self, student: Any, question: str, *, reason: str, trigger: str, confidence: float | None, payload: dict) -> AgentResult:
        """Record the question as escalated and hand it to the teacher; the teacher's answer is overlaid later."""
        entry = learning_services.append_history(
            AGENT_ID,
            student=student,
            kind="explain",
            payload={"question": question, "source_refs": [], **payload, "reason": reason, "prompt": prompts.EXPLAIN.id},
            confidence=confidence,
            escalated=True,
        )
        control = {"summary": "Escalated a learning question to the teacher.", "subject_type": "question", "subject_id": str(entry.pk), "trigger": trigger}
        return AgentResult(AgentStatus.NEEDS_ESCALATION, {"result": {"interaction": interaction_view(entry)}, **control}, confidence=confidence, reason=reason)

    def _retrieve_material(self, task: TaskInput) -> AgentResult:
        """UC04 2a: approved materials for the current stage, best match first, with a short guide."""
        student = self._student(task)
        if student is None:
            return _failed("student_not_found", "Student not found.")
        question = str(task.payload.get("input", {}).get("question", "")).strip()
        learner = context.learner(student)
        materials = context.rank_materials(context.stage_materials(student), question)
        if not materials:
            self._log_corpus_gap("resources", learner["current_stage"])
            answer, refs = NO_MATERIALS_REPLY, []
        else:
            self.runtime.note("materials_ranked", material_ids=[m["id"] for m in materials])
            guide = self._ask(prompts.RESOURCES, ResourceGuide, context=learner, materials=materials, student_input=question)
            if guide is None:  # listing materials does not need the model; fall back to a plain guide
                self.runtime.note("template_fallback", reason=self._llm_failure_reason())
                answer, refs = _resource_guide(materials, learner["current_stage"]), [context.source_ref(m) for m in materials]
            else:
                answer = guide.guide
                refs = _refs(guide.material_ids, materials) + [context.source_ref(m) for m in materials if m["id"] not in guide.material_ids]
        entry = learning_services.append_history(
            AGENT_ID,
            student=student,
            kind="resources",
            payload={"question": question, "answer": answer, "source_refs": refs, "prompt": prompts.RESOURCES.id},
        )
        return _ok({"interaction": interaction_view(entry)}, summary="Listed materials for the current stage.")

    def _generate_practice(self, task: TaskInput) -> AgentResult:
        student = self._student(task)
        if student is None:
            return _failed("student_not_found", "Student not found.")
        materials = context.stage_materials(student, limit=2)
        focus = task.payload.get("input", {}).get("focus")
        item = self._ask(prompts.PRACTICE, PracticeItem, context=context.learner(student), materials=materials, request={"focus": focus} if focus else None)
        if item is None:
            return self._llm_failed()
        source = next((m["title"] for m in materials if m["id"] == item.material_id), "")
        item_id = f"P-{uuid.uuid4().hex[:8]}"
        learning_services.append_history(
            AGENT_ID,
            student=student,
            kind="practice",
            payload={"item_id": item_id, "question": item.question, "expected_points": item.expected_points, "material_id": item.material_id, "prompt": prompts.PRACTICE.id},
        )
        return _ok({"question": item.question, "item_id": item_id, "source": source}, summary="Created a practice item.")

    def _give_feedback(self, task: TaskInput) -> AgentResult:
        """UC05 step 2 / AR05: instant feedback on light practice. It never changes assessments or the plan."""
        student = self._student(task)
        if student is None:
            return _failed("student_not_found", "Student not found.")
        data = task.payload.get("input", {})
        answer = str(data.get("answer", "")).strip()
        practices = learning.history(student, kinds=("practice",))
        # the frontend only sends the answer, so without an item_id the latest practice item is the one answered
        practice = practices.filter(payload__item_id=data["item_id"]).last() if data.get("item_id") else practices.last()
        if practice is None:
            return _failed("no_practice_item", "Start a practice first.")
        item = {"question": practice.payload.get("question"), "expected_points": practice.payload.get("expected_points", [])}
        feedback = self._ask(prompts.FEEDBACK, PracticeFeedback, context={"level": context.learner(student)["level"]}, practice=item, student_input=answer)
        if feedback is None:
            return self._llm_failed()
        learning_services.append_history(
            AGENT_ID,
            student=student,
            kind="practice_answer",
            payload={
                "item_id": practice.payload.get("item_id"),
                "answer": answer,
                "feedback": feedback.feedback,
                "met_points": feedback.met_points,
                "missing_points": feedback.missing_points,
                "prompt": prompts.FEEDBACK.id,
            },
        )
        return _ok({"feedback": feedback.feedback}, summary="Gave practice feedback.")

    # --- teacher-facing (UC06, UC07, UC08) --------------------------------------------------------
    def _analyze_progress(self, task: TaskInput) -> AgentResult:
        student = self._student(task)
        if student is None:
            return _failed("student_not_found", "Student not found.")
        analysis = self._ask(prompts.PROGRESS, ProgressAnalysis, context=context.teacher_view(student))
        if analysis is None:
            return self._llm_failed()
        return _ok({"recommendation": analysis.analysis, "evidence": analysis.evidence}, summary="Compiled a progress analysis.")

    def _recommend_adjustments(self, task: TaskInput) -> AgentResult:
        student = self._student(task)
        if student is None:
            return _failed("student_not_found", "Student not found.")
        advice = self._ask(prompts.RECOMMEND, PlanRecommendations, context=context.teacher_view(student))
        if advice is None:
            return self._llm_failed()
        text = "\n".join(f"{n}. {item}" for n, item in enumerate(advice.recommendations, start=1))
        return _ok({"recommendation": text, "evidence": advice.evidence}, summary="Recommended plan adjustments.")

    def _lesson_briefing(self, task: TaskInput) -> AgentResult:
        lesson = self._lesson(task)
        if lesson is None:
            return _failed("lesson_not_found", "Lesson not found.")
        materials = context.lesson_materials(lesson)
        briefing = self._ask(
            prompts.BRIEFING, LessonBriefing, context=context.learner(lesson.student), lesson=context.lesson_info(lesson), materials=materials
        )
        if briefing is None:
            return self._llm_failed()
        return _ok({"briefing": briefing.briefing, "source_refs": _refs(briefing.material_ids, materials)}, summary="Prepared a lesson briefing.")

    def _generate_material(self, task: TaskInput) -> AgentResult:
        lesson = self._lesson(task)
        if lesson is None:
            return _failed("lesson_not_found", "Lesson not found.")
        data = task.payload.get("input", {})
        learner = context.learner(lesson.student)
        info = context.lesson_info(lesson)
        request = {
            "title": data.get("title") or data.get("topic") or "",
            "topic": data.get("topic") or ", ".join((info["stage"] or {}).get("topics", [])),
            "level": data.get("level") or learner["level"],
            "type": data.get("type") or "exercise",
            "guidance": data.get("guidance") or "",
        }
        materials = context.lesson_materials(lesson)
        draft = self._ask(prompts.MATERIAL, MaterialDraft, context=learner, lesson=info, materials=materials, request=request)
        if draft is None:
            return self._llm_failed()
        material = learning_services.create_material_draft(
            AGENT_ID,
            lesson=lesson,
            title=request["title"] or draft.title,
            content=draft.content,
            citations=_refs(draft.cited_material_ids, materials),
            locator="Teacher draft",
        )
        return _ok({"material": material_view(material)}, summary="Drafted teaching material for review.")

    # --- helpers --------------------------------------------------------------------------------
    def _ask(self, prompt: prompts.Prompt, schema: type[BaseModel], **sections: Any) -> Any:
        self.runtime.note("prompt", id=prompt.id)
        return self.runtime.structured(prompt.system, [prompts.user_message(**sections)], schema, tier=prompt.tier, max_tokens=prompt.max_tokens)

    def _log_corpus_gap(self, request: str, stage: dict | None) -> None:
        """UC08 3a: report missing material so the Technical Manager can propose a corpus update."""
        stage_title = stage["title"] if stage else "no plan stage"
        self.runtime.note("corpus_gap", request=request, stage=stage_title)
        governance_services.record_audit(
            AGENT_ID,
            "teaching_support.corpus_gap",
            ("plan_stage", stage["number"] if stage else ""),
            detail={"summary": f"No approved materials for {stage_title} ({request})", "request": request, "topics": (stage or {}).get("topics", [])},
        )

    def _llm_failure_reason(self) -> str:
        unavailable = any(step.get("step") == "llm" and step.get("stop") == "error" for step in self.runtime.trace)
        return "llm_unavailable" if unavailable else "invalid_llm_output"

    def _llm_failed(self) -> AgentResult:
        if self._llm_failure_reason() == "llm_unavailable":
            return _failed("llm_unavailable", "The AI service is not available right now. Please try again later.")
        return _failed("invalid_llm_output", "The AI reply could not be used. Please try again.")

    @staticmethod
    def _student(task: TaskInput) -> Any:
        return learning.student(task.student_id) if task.student_id else None

    @staticmethod
    def _lesson(task: TaskInput) -> Any:
        lesson_id = task.payload.get("input", {}).get("lesson_id") or task.payload.get("context_id")
        return learning.lesson(lesson_id) if lesson_id else None


def _resource_guide(materials: list[dict], stage: dict | None) -> str:
    first = materials[0]
    text = f"Start with {first['title']} ({first['locator']})"
    if len(materials) > 1:
        text += ", then " + ", ".join(m["title"] for m in materials[1:3])
    stage_part = f" for {stage['title']}" if stage else ""
    return f"{text}. These are the approved materials{stage_part}."


def _refs(ids: list[str], materials: list[dict]) -> list[dict]:
    """Source references for the cited ids that were actually provided; unknown ids are dropped."""
    by_id = {m["id"]: m for m in materials}
    return [context.source_ref(by_id[i]) for i in dict.fromkeys(ids) if i in by_id]


def _ok(result: dict, *, summary: str, confidence: float | None = None) -> AgentResult:
    return AgentResult(AgentStatus.OK, {"result": result, "summary": summary}, confidence=confidence)


def _failed(reason: str, message: str) -> AgentResult:
    return AgentResult(AgentStatus.FAILED, {"message": message}, reason=reason)
