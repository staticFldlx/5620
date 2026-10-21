"""Pydantic schemas for the assessment agent.

LLM outputs are kept flat (no nested models) so the JSON schema has no $defs, which some
OpenAI-compatible endpoints (e.g. Gemini) do not accept. Task payload schemas document what
the Orchestrator hands to each task type (docs/shared-conventions.md 3.4).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- LLM outputs ------------------------------------------------------------------------------
class GeneratedItem(BaseModel):
    """One assessment item (F2.3). It must be answerable in a text box."""

    prompt: str = Field(min_length=10)
    expected_points: list[str] = Field(min_length=1)  # hidden rubric points, used for scoring


class ScoredAnswer(BaseModel):
    """Evaluation of one answer against the item's rubric (F2.4)."""

    demonstrated_level: str  # CEFR level the language of the answer shows (A1..C2)
    score: float = Field(ge=0.0, le=1.0)  # holistic: how well the answer shows the item's level
    met_points: list[str] = []  # copied from expected_points
    feedback: str  # one or two sentences for the learner
    off_task: bool = False  # blank, "I don't know", copied text or unrelated to the item


class AssessmentReport(BaseModel):
    """Narrative part of the proficiency profile (F2.5). The level itself is computed, not asked for."""

    strengths: list[str] = []
    weaknesses: list[str] = []
    gap_to_goal: str
    feedback: str


# --- task payloads ----------------------------------------------------------------------------
class StartInput(BaseModel):
    kind: str  # initial | milestone | directed
    focus: str = ""


class AnswerReply(BaseModel):
    item_id: str
    answer: str


class ReviewDecision(BaseModel):
    action: str  # confirm_result | request_changes
    note: str = ""
    decided_by: str = ""
    corrected_level: str | None = None


class ConductPayload(BaseModel):
    """assessment.conduct_assessment: first call has `input`; each answer adds `reply` + `previous`."""

    input: StartInput
    reply: AnswerReply | None = None
    previous: dict[str, Any] | None = None

    def session_id(self) -> str | None:
        return ((self.previous or {}).get("result") or {}).get("session_id")


class ApplyReviewPayload(BaseModel):
    """assessment.apply_review: resumed by the EscalationManager after the teacher's decision (UC02 7a)."""

    decision: ReviewDecision
    subject_id: str  # ProficiencyProfile id
