"""AI Assessment Agent (IAssessment, Fig 6a): AR02, AR05, AR13; UC02, UC05; F2.1-F2.7; NFR-02.

Perceive  the learner profile, the last confirmed level, the current plan stage and every answer.
Decide    which skills and start level to use (F2.7), the next item's difficulty, when to stop, and
          whether the result is reliable enough to publish or needs a teacher (NFR-02).
Act       generate items, score answers, write the session and proficiency profile, hand the result
          to the Course Consultant (pipeline step C1) or to the teacher (EscalationManager).

One conduct_assessment task runs per item: it returns NEEDS_INPUT with the session id, and the
Orchestrator hands the student's answer back to the same task type (backend/README.md 4.2).
Every decision is written to the trace with runtime.note() for GET /requests/{id}/trace.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from pydantic import BaseModel, ValidationError

from agents.runtime import AgentResult, AgentStatus, AIAgent, TaskInput
from domain.learning import selectors as learning
from domain.learning import services as learning_services
from domain.learning.views import proficiency_view

from . import adaptive, bank, context, fake, prompts
from .schemas import AnswerReply, ApplyReviewPayload, AssessmentReport, ConductPayload, GeneratedItem, ScoredAnswer

AGENT_ID = "assessment"
PROVISIONAL_NOTE = "This result is provisional until your teacher reviews it."


class AssessmentAgent(AIAgent):
    agent_id = AGENT_ID
    task_types = ("assessment.conduct_assessment", "assessment.apply_review")

    @staticmethod
    def fake_script(task: TaskInput) -> list:
        return fake.script(task)

    def execute_task(self, task: TaskInput) -> AgentResult:
        handler = getattr(self, "_" + task.task_type.split(".", 1)[1])
        return handler(task)

    # --- assessment.conduct_assessment (UC02, UC05, directed UC06 3a) -----------------------------
    def _conduct_assessment(self, task: TaskInput) -> AgentResult:
        try:
            payload = ConductPayload.model_validate(task.payload)
        except ValidationError as exc:
            return _failed("invalid_task_payload", f"The assessment request is incomplete: {exc.errors(include_url=False)[0]['msg']}")
        student = learning.student(task.student_id) if task.student_id else None
        if student is None:
            return _failed("student_not_found", "Student not found.")
        if payload.reply is None:
            return self._start(task, student, payload)
        session = learning.assessment_session(payload.session_id())
        if session is None or session.student_id != student.pk:
            return _failed("session_not_found", "This assessment could not be found.")
        if session.status != "in_progress":
            return _failed("session_closed", "This assessment is already finished.")
        return self._answer(student, session, payload, payload.reply)

    def _start(self, task: TaskInput, student: Any, payload: ConductPayload) -> AgentResult:
        kind, focus = payload.input.kind, payload.input.focus.strip()
        if payload.input.milestone_stage_id:
            stage = learning.milestone_stage(payload.input.milestone_stage_id, student)
            if kind != "milestone" or stage is None or not learning.stage_lessons_attended(stage):
                return _failed("stale_milestone", "This milestone no longer belongs to the active stage.")
        learner = context.learner(student, kind)
        skills, proxied = adaptive.plan_skills(learner["focus_skills"], focus)
        level = learner["start_level"]
        self.runtime.note(
            "skills_selected",
            kind=kind,
            skills=skills,
            written_proxy_for=proxied,
            start_level=level,
            level_source=learner["level_source"],
            focus=focus or learner["stage_milestone"] or "",
        )
        item = self._generate(learner, skills, number=1, level=level, focus=focus, previous=[])
        item["planned_skills"] = skills
        fields: dict[str, Any] = {"focus": focus, "difficulty": level, "max_items": adaptive.MAX_ITEMS, "items": [item]}
        fields["baseline_level"] = learner["baseline_level"] or ""
        if payload.input.milestone_stage_id:
            fields["milestone_stage"] = stage
            fields["milestone_target_level"] = learning.stage_target_level(stage)
        if task.ctx.actor_role == "teacher":
            fields["requested_by_id"] = task.ctx.actor_id  # directed assessment (UC06 3a)
        session = learning_services.create_assessment_session(AGENT_ID, student=student, type=kind, **fields)
        return _next_item(session)

    def _answer(self, student: Any, session: Any, payload: ConductPayload, reply: AnswerReply) -> AgentResult:
        items = [dict(item) for item in session.items]
        pending = next((i for i in items if i.get("answer") is None), None)
        if pending is None:  # every item answered but not finished (e.g. the worker stopped): finish now
            return self._finish(student, session, payload.input.kind, "item_limit_reached")
        if reply.item_id != pending["item_id"]:
            self.runtime.note("unexpected_item", received=reply.item_id, expected=pending["item_id"])
            return _next_item(session)
        session = learning_services.record_answer(AGENT_ID, session, item_id=reply.item_id, answer=reply.answer)
        items = [dict(item) for item in session.items]
        current = next(i for i in items if i["item_id"] == reply.item_id)
        if "score" not in current:  # a re-queued task does not score twice (spec 8.5)
            current.update(self._score(current, reply.answer))
            session = learning_services.update_assessment_session(AGENT_ID, session, items=items)

        answered = [i for i in items if i.get("answer") is not None]
        estimates = [i["estimate"] for i in answered if i.get("estimate") is not None]
        stop = adaptive.stop_reason(estimates, len(answered), session.max_items)
        if stop is not None:
            return self._finish(student, session, payload.input.kind, stop)

        index = adaptive.level_index(current["level"])
        if current.get("score") is not None:
            index = adaptive.next_index(index, current["score"])
        level = adaptive.level_name(index)
        self.runtime.note("difficulty_adjusted", item_id=current["item_id"], score=current.get("score"), from_level=current["level"], to_level=level)
        planned = items[0].get("planned_skills") or list(adaptive.TEXT_SKILLS)
        learner = context.learner(student, payload.input.kind)
        item = self._generate(learner, planned, number=len(items) + 1, level=level, focus=session.focus, previous=[i["prompt"] for i in items])
        session = learning_services.update_assessment_session(AGENT_ID, session, items=[*items, item], difficulty=level)
        return _next_item(session)

    def _finish(self, student: Any, session: Any, kind: str, stop: str) -> AgentResult:
        """UC02 steps 6-7 / UC05 step 5: level, confidence, report; publish or escalate (NFR-02)."""
        existing = getattr(session, "proficiency", None)
        if existing is not None:  # re-queued after the profile was written
            reason = "low_confidence" if self.runtime.is_low_confidence(existing.confidence) else "insufficient_evidence"
            return self._publish(session, existing, low=existing.status == "pending_review", reason=reason)

        answered = [i for i in session.items if i.get("answer") is not None]
        scored = [i for i in answered if i.get("score") is not None]
        estimates = [i["estimate"] for i in scored]
        planned = session.items[0].get("planned_skills") or list(adaptive.TEXT_SKILLS)
        level = adaptive.final_level(estimates)
        signals = adaptive.confidence_signals(
            estimates,
            [i["agreement"] for i in scored],
            answered=len(answered),
            max_items=session.max_items,
            skills_covered=len({i["skill"] for i in scored}),
            skills_planned=len(planned),
        )
        confidence = self.runtime.calculate_confidence(signals, adaptive.CONFIDENCE_WEIGHTS)
        off_task = sum(1 for i in answered if i.get("off_task"))
        unscored = len(answered) - len(scored)
        self.runtime.note("level_estimated", level=level, estimates=estimates, stop_reason=stop)
        self.runtime.note("confidence_scored", confidence=confidence, signals=signals, weights=adaptive.CONFIDENCE_WEIGHTS)

        reason = None
        if self.runtime.is_low_confidence(confidence):
            reason = "low_confidence"
        elif off_task * 2 >= len(answered) or unscored:
            reason = "insufficient_evidence"  # many blank/off-task or unscored answers: a teacher must judge
        learner = context.learner(student, kind)
        baseline = learner["baseline_level"]
        if baseline:
            self.runtime.note("progress_vs_baseline", baseline=baseline, measured=level, delta=adaptive.level_index(level) - adaptive.level_index(baseline))

        report = self._report(learner, level, answered, kind)
        feedback = report.feedback.strip()
        if reason:
            feedback = f"{feedback} {PROVISIONAL_NOTE}".strip()
        record = learning_services.record_proficiency(
            AGENT_ID,
            session=session,
            overall_level=level,
            strengths=report.strengths[:3],
            weak_areas=report.weaknesses[:3],
            gap_to_goal=report.gap_to_goal,
            confidence=confidence,
            status="pending_review" if reason else "confirmed",
            feedback=feedback,
        )
        session = learning_services.update_assessment_session(
            AGENT_ID, session, status="awaiting_review" if reason else "completed", completed_at=timezone.now(), difficulty=level
        )
        learning_services.append_history(
            AGENT_ID,
            student=student,
            kind="assessment",
            payload={"session_id": str(session.pk), "proficiency_id": str(record.pk), "kind": kind, "level": level, "signals": signals, "stop_reason": stop},
            confidence=confidence,
            escalated=bool(reason),
        )
        return self._publish(session, record, low=bool(reason), reason=reason or "", signals=signals, stop=stop)

    def _publish(self, session: Any, record: Any, *, low: bool, reason: str, signals: dict | None = None, stop: str = "") -> AgentResult:
        result = {"session_id": str(session.pk), "assessment": proficiency_view(record)}
        if not low:
            self.runtime.note("result_published", proficiency_id=str(record.pk), level=record.overall_level)
            return AgentResult(AgentStatus.OK, {"result": result, "phase": "assessment_completed", "summary": f"Assessed at {record.overall_level}."}, confidence=record.confidence)
        trigger = {
            "low_confidence": "Low-confidence assessment result",
            "insufficient_evidence": "Too many blank, off-task or unscored answers",
        }.get(reason, "Assessment needs teacher review")
        self.runtime.note("escalated_to_teacher", reason=reason, confidence=record.confidence)
        evidence = [f"{name}: {value}" for name, value in (signals or {}).items()]
        if stop:
            evidence.append(f"stop: {stop}")
        payload = {
            "result": result,
            "phase": "assessment_review",
            "subject_type": "assessment",
            "subject_id": str(record.pk),
            "resume": "assessment.apply_review",
            "trigger": trigger,
            "summary": f"Provisional {record.overall_level} (confidence {record.confidence})",
            "evidence": evidence,
        }
        return AgentResult(AgentStatus.NEEDS_ESCALATION, payload, confidence=record.confidence, reason=reason)

    # --- assessment.apply_review (UC02 7a, UC05 5a) ---------------------------------------------
    def _apply_review(self, task: TaskInput) -> AgentResult:
        """The teacher confirmed or corrected the provisional result, or asked for a new assessment."""
        try:
            payload = ApplyReviewPayload.model_validate(task.payload)
        except ValidationError:
            return _failed("invalid_task_payload", "The review decision is incomplete.")
        record = learning.proficiency(payload.subject_id)
        if record is None:
            return _failed("proficiency_not_found", "The reviewed assessment result could not be found.")
        session, decision = record.session, payload.decision
        reviewer = {"reviewed_by_id": decision.decided_by} if decision.decided_by else {}
        if decision.action == "confirm_result":
            if record.status != "confirmed":
                corrected = (decision.corrected_level or "").strip()
                level = adaptive.parse_level(corrected, default=None) or record.overall_level
                if corrected and adaptive.parse_level(corrected, default=None) is None:
                    self.runtime.note("corrected_level_ignored", value=corrected[:40])  # not a CEFR level; the note keeps it
                fields: dict[str, Any] = {"status": "confirmed", "overall_level": level, "review_note": decision.note, **reviewer}
                feedback = record.feedback.replace(PROVISIONAL_NOTE, "").strip()
                if level != record.overall_level:
                    feedback = f"{feedback} Your teacher set your level to {level}.".strip()
                    self.runtime.note("teacher_corrected_level", from_level=record.overall_level, to_level=level)
                fields["feedback"] = feedback
                record = learning_services.update_proficiency(AGENT_ID, record, **fields)
                learning_services.update_assessment_session(AGENT_ID, session, status="completed")
            self.runtime.note("teacher_confirmed", proficiency_id=str(record.pk), level=record.overall_level)
            result = {"session_id": str(session.pk), "assessment": proficiency_view(record)}
            return AgentResult(AgentStatus.OK, {"result": result, "phase": "assessment_confirmed", "summary": f"Teacher confirmed {record.overall_level}."})
        if decision.action == "request_changes":
            if record.status != "changes_requested":
                learning_services.update_proficiency(AGENT_ID, record, status="changes_requested", review_note=decision.note, **reviewer)
                learning_services.update_assessment_session(AGENT_ID, session, status="completed")
            self.runtime.note("teacher_requested_reassessment", proficiency_id=str(record.pk))
            # C1: no plan from a rejected result, so the pipeline stops here instead of reaching planning
            return _failed("assessment_changes_requested", "Your teacher asked for a new assessment before your level is updated.")
        return _failed("invalid_review_action", f"Unknown review action: {decision.action}")

    # --- LLM steps --------------------------------------------------------------------------------
    def _generate(self, learner: dict, skills: list[str], *, number: int, level: str, focus: str, previous: list[str]) -> dict:
        """F2.3. UC02 3a: structured() retries once; if the model still fails, a bank item keeps the assessment going."""
        skill = adaptive.skill_for(skills, number)
        request = {
            "skill": skill,
            "level": level,
            "item_number": number,
            "max_items": adaptive.MAX_ITEMS,
            "focus": focus or learner["stage_milestone"] or "",
            "previous_prompts": previous,
        }
        context = {k: learner[k] for k in ("goal", "target_level", "kind", "stage_title")}
        item = self._ask(prompts.GENERATE_ITEM, GeneratedItem, learner=context, request=request)
        if item is not None and _is_repeat(item.prompt, previous):
            self.runtime.note("repeated_item_regenerated", item_number=number)
            item = self._ask(prompts.GENERATE_ITEM, GeneratedItem, learner=context, request={**request, "note": "Your last item repeated an earlier one. Write a different item."})
            if item is not None and _is_repeat(item.prompt, previous):
                item = None
        if item is None:
            fallback = bank.item(skill, level, number, len(skills))
            self.runtime.note("item_bank_fallback", item_id=f"item-{number}", skill=skill, level=level, llm=self._llm_failure_reason())
            text, points, source = fallback["prompt"], fallback["expected_points"], bank.PROMPT_ID
        else:
            self.runtime.note("item_generated", item_id=f"item-{number}", skill=skill, level=level)
            text, points, source = item.prompt.strip(), item.expected_points[:4], prompts.GENERATE_ITEM.id
        return {"item_id": f"item-{number}", "prompt": text, "answer": None, "skill": skill, "level": level, "expected_points": points, "prompt_id": source}

    def _score(self, item: dict, answer: str) -> dict:
        public = {k: item[k] for k in ("skill", "level", "prompt", "expected_points")}
        if len(answer) > prompts.MAX_ANSWER_CHARS:
            self.runtime.note("answer_truncated", item_id=item["item_id"], chars=len(answer))
        scored = self._ask(prompts.SCORE_ANSWER, ScoredAnswer, item=public, answer=prompts.as_data(answer))
        if scored is None:
            self.runtime.note("scoring_failed", item_id=item["item_id"])
            return {"score": None, "estimate": None, "agreement": None, "scoring_failed": True}
        met = [p for p in scored.met_points if p in item["expected_points"]]
        score, agreement = self._combine(item, scored, met)
        if not scored.off_task and adaptive.needs_second_opinion(score):
            # the score decides the next level: a second independent scoring, averaged (consistency evidence too)
            second = self._ask(prompts.SCORE_ANSWER, ScoredAnswer, item=public, answer=prompts.as_data(answer))
            if second is not None:
                second_score, _ = self._combine(item, second, [p for p in second.met_points if p in item["expected_points"]])
                self.runtime.note("second_opinion", item_id=item["item_id"], first=score, second=second_score)
                agreement = round(min(agreement, 1.0 - abs(score - second_score)), 3)
                score = round((score + second_score) / 2, 3)
        estimate = adaptive.estimate(adaptive.level_index(item["level"]), score)
        self.runtime.note(
            "answer_scored",
            item_id=item["item_id"],
            score=score,
            rubric_score=scored.score,
            demonstrated_level=scored.demonstrated_level,
            met_points=len(met),
            agreement=agreement,
            off_task=scored.off_task,
        )
        return {
            "score": score,
            "demonstrated_level": adaptive.parse_level(scored.demonstrated_level, default=None),
            "met_points": met,
            "feedback": scored.feedback.strip(),
            "off_task": scored.off_task,
            "agreement": agreement,
            "estimate": estimate,
        }

    @staticmethod
    def _combine(item: dict, scored: ScoredAnswer, met: list[str]) -> tuple[float, float]:
        return adaptive.combine(item["level"], scored.score, scored.demonstrated_level, len(met), len(item["expected_points"]), scored.off_task)

    def _report(self, learner: dict, level: str, answered: list[dict], kind: str) -> AssessmentReport:
        items = [{k: i.get(k) for k in ("skill", "level", "score", "feedback", "off_task")} for i in answered]
        request = {
            "overall_level": level,
            "kind": kind,
            "goal": learner["goal"],
            "target_level": learner["target_level"],
            "previous_confirmed_level": learner["baseline_level"],
        }
        report = self._ask(prompts.REPORT, AssessmentReport, request=request, items=items)
        if report is not None:
            return report
        self.runtime.note("report_template_fallback")
        return _template_report(level, answered, learner)

    def _ask(self, prompt: prompts.Prompt, schema: type[BaseModel], **sections: Any) -> Any:
        self.runtime.note("prompt", id=prompt.id)
        return self.runtime.structured(prompt.system, [prompts.user_message(**sections)], schema, tier=prompt.tier, max_tokens=prompt.max_tokens)

    def _llm_failure_reason(self) -> str:
        unavailable = any(step.get("step") == "llm" and step.get("stop") == "error" for step in self.runtime.trace)
        return "llm_unavailable" if unavailable else "invalid_llm_output"


# --- helpers ----------------------------------------------------------------------------------------
def _template_report(level: str, answered: list[dict], learner: dict) -> AssessmentReport:
    """Used when the report call fails: built only from the computed scores."""
    by_skill: dict[str, list[float]] = {}
    for item in answered:
        if item.get("score") is not None:
            by_skill.setdefault(item["skill"], []).append(item["score"])
    means = {skill: sum(scores) / len(scores) for skill, scores in by_skill.items()}
    strengths = [s for s, m in sorted(means.items(), key=lambda kv: -kv[1]) if m >= 0.6][:3]
    weaknesses = [s for s, m in sorted(means.items(), key=lambda kv: kv[1]) if m < 0.6][:3]
    target = learner["target_level"] or "your target level"
    return AssessmentReport(
        strengths=strengths,
        weaknesses=weaknesses,
        gap_to_goal=f"Current level {level}; target {target}.",
        feedback=f"Your answers place you at {level}." + (f" Focus next on {', '.join(weaknesses)}." if weaknesses else ""),
    )


def _is_repeat(prompt: str, previous: list[str]) -> bool:
    """Same opening words as an earlier item (the model sometimes ignores previous_prompts)."""
    head = " ".join(prompt.lower().split()[:12])
    return any(head == " ".join(p.lower().split()[:12]) for p in previous)


def _next_item(session: Any) -> AgentResult:
    return AgentResult(AgentStatus.NEEDS_INPUT, {"result": {"session_id": str(session.pk)}, "phase": "next_item"})


def _failed(reason: str, message: str) -> AgentResult:
    return AgentResult(AgentStatus.FAILED, {"message": message}, reason=reason)
