"""Planning-owned validation; no imports from frontend/orchestration contracts."""
from __future__ import annotations

from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PlanningSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanningDecision(PlanningSchema):
    action: NonBlank
    note: NonBlank
    decided_by: NonBlank
    requested_action: str | None = None


class PlanningTask(BaseModel):
    model_config = ConfigDict(extra="allow")
    input: dict[str, Any] = Field(default_factory=dict)
    decision: PlanningDecision | None = None
    case_id: str | None = None
    subject_id: str | None = None
    reply: dict[str, Any] | None = None
    previous: dict[str, Any] | None = None
    upstream: dict[str, Any] | None = None
    upstream_data: dict[str, Any] | None = None


class PlanRevisionRequest(PlanningSchema):
    """Student/teacher-initiated revision input (matches the frontend keys)."""

    reason: NonBlank
    requested_change: str | None = None


class SlotRequest(BaseModel):
    """Planning input boundary; shared frontend contracts may carry extra keys."""
    model_config = ConfigDict(extra="allow")
    lesson_id: NonBlank | None = None
    slot: NonBlank | None = None
    requested_time: NonBlank | None = None
    starts_at: NonBlank | None = None
    slot_request_id: NonBlank | None = None
    slot_id: NonBlank | None = None


class PlanStageDraft(PlanningSchema):
    """LLM-authored stage: no DB IDs or Django ORM objects."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    topics: list[NonBlank] = Field(min_length=1)
    milestone: NonBlank
    start_week: int = Field(ge=1)
    end_week: int = Field(ge=1, le=104)
    course_codes: list[str] = Field(default_factory=list)

    @field_validator("course_codes", mode="before")
    @classmethod
    def normalise_course_codes(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value  # Let Pydantic raise the normal list-type error.
        codes: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("course_codes must contain strings")
            code = item.strip()
            if not (1 <= len(code) <= 32):
                raise ValueError("course codes must contain 1 to 32 characters")
            if code in codes:
                raise ValueError("duplicate course code within a stage")
            codes.append(code)
        return codes

    @model_validator(mode="after")
    def validate_week_range(self) -> PlanStageDraft:
        if self.end_week < self.start_week:
            raise ValueError("end_week must be >= start_week")
        return self


class PlanDraft(PlanningSchema):
    """Unpersisted plan content to validate before business checks and saving."""

    weekly_hours: float = Field(gt=0, allow_inf_nan=False)
    stages: list[PlanStageDraft] = Field(min_length=1)
    rationale: NonBlank


class PlanResult(PlanningSchema):
    """Business payload for a pending-review plan.

    `plan` must come from the domain plan serializer; Orchestration validates
    the final frontend-facing PlanReviewResult for `revise_plan`.
    Control keys are stored directly in AgentTask.result; only `plan` is
    placed in the nested student-facing business result.
    """

    plan: dict[str, Any]
    subject_type: Literal["plan"] = "plan"
    subject_id: NonBlank
    trigger: NonBlank = "A teacher must review this learning plan."
    resume: Literal["planning.activate_plan"] = "planning.activate_plan"
    summary: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    route_to: Literal["founder"] | None = None
    review_id: str | None = None

    @model_validator(mode="after")
    def validate_subject(self) -> PlanResult:
        if self.subject_id != str(self.plan.get("id", "")):
            raise ValueError("subject_id must equal the persisted plan.id")
        return self


class PlanBusinessResult(PlanningSchema):
    plan: dict[str, Any]


class SlotResult(PlanningSchema):
    id: NonBlank
    starts_at: NonBlank
    ends_at: NonBlank


class SlotBusinessResult(PlanningSchema):
    lesson_id: str
    slots: list[SlotResult]
    proposed_slot: str | None = None
    question: str | None = None
    message: str


class LessonBusinessResult(PlanningSchema):
    lesson: dict[str, Any]


class MessageBusinessResult(PlanningSchema):
    message: NonBlank


class FailurePayload(PlanningSchema):
    message: NonBlank
