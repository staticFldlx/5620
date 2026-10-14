"""Hard contract between agents and the frontend.

* Record shapes mirror frontend/src/api/types.ts (the code wins over contract.json).
* RESULT_CONTRACTS: what `ServiceRequest.result` must look like for each request type.
  The Orchestrator validates every user-facing result against it before saving it.
* INPUT_CONTRACTS: what the frontend actually sends in `input` (lenient: extra keys allowed).

Build records with domain.*.views helpers instead of hand-writing dicts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="allow")


# --- records (src/api/types.ts) -----------------------------------------------------
class UserRef(Record):
    id: str
    name: str


class UserRecord(UserRef):
    email: str
    role: str  # "Student" | "Teacher" | "Founder"


class AvailabilityRecord(Record):
    day: str
    start: str
    end: str


class ProfileRecord(Record):
    goal_text: str
    goal_summary: str
    focus_skills: list[str]
    target_level: str
    self_level: str
    weekly_hours: float
    timezone: str
    availability: list[AvailabilityRecord]


class ProficiencyRecord(Record):
    id: str
    kind: str
    status: str
    created_at: str
    level: str
    confidence: float | None
    strengths: list[str]
    weaknesses: list[str]
    goal_gap: str
    feedback: str
    review_note: str | None = None
    requested_focus: str | None = None


class StageRecord(Record):
    title: str
    course_ref: str
    start_week: int
    end_week: int
    topics: list[str]
    milestone: str
    status: str


class PlanRecord(Record):
    id: str
    version: int
    status: str
    stage_index: int
    teacher: UserRef | None
    weekly_hours: float
    stages: list[StageRecord]
    reason: str
    review_id: str
    approved_at: str | None


class LessonRecord(Record):
    id: str
    student_id: str
    title: str
    starts_at: str
    ends_at: str
    teacher: UserRef
    stage_index: int
    status: str
    classroom_url: str | None
    attendance: str
    feedback: str
    material_ids: list[str]


class MaterialRecord(Record):
    id: str
    title: str
    locator: str
    status: str
    lesson_id: str
    content: str
    source_refs: list[Any]


class SourceRef(Record):
    material_id: str
    title: str
    locator: str


class InteractionRecord(Record):
    id: str
    student_id: str
    type: str
    question: str
    answer: str
    feedback: str | None
    status: str
    confidence: float | None
    source_refs: list[SourceRef]
    sent_at: str
    escalation: dict | None


class StudentRecord(Record):
    name: str
    profile: ProfileRecord
    assessments: list[ProficiencyRecord]
    plan: PlanRecord | None
    pending_plan: PlanRecord | None
    material_records: list[dict]
    observation: str


class ReviewRecord(Record):
    id: str
    kind: str
    student_id: str
    subject_id: str
    status: str
    trigger: str
    decision: str | None


class LatestTask(Record):
    id: str
    status: str
    confidence: float | None
    output_summary: str


class AgentRecord(Record):
    id: str
    name: str
    status: str
    latest_task: LatestTask


class LogRecord(Record):
    id: str
    time: str
    agent_id: str
    event: str
    severity: str
    task_status: str
    confidence: float | None
    escalated: bool


class EvidenceRef(Record):
    ref: str
    summary: str


class CaseRecord(Record):
    id: str
    kind: str
    status: str
    subject: str
    trigger: str
    diagnosis: str
    evidence: list[EvidenceRef]
    proposal_id: str | None
    decision: str | None
    verification: str | None


class Execution(Record):
    status: str
    verification: str | None


class ProposalRecord(Record):
    id: str
    type: str
    title: str
    case_id: str | None
    status: str
    evidence: list[str]
    before: str
    after: str
    validation: str
    rollback: str
    decision: str | None
    execution: Execution


class ServiceRecord(Record):
    name: str
    status: str
    last_backup_at: str | None


class WarningRecord(Record):
    id: str
    trigger: str
    status: str
    output_summary: str


class AuditRecord(Record):
    id: str
    time: str
    actor_role: str
    actor_name: str
    subject_id: str
    action: str
    result: str


class OperationsRecord(Record):
    agents: list[AgentRecord]
    services: list[ServiceRecord]
    logs: list[LogRecord]
    warnings: list[WarningRecord]
    cases: list[CaseRecord]
    proposals: list[ProposalRecord]
    audit: list[AuditRecord]


class WorkspaceRecord(Record):
    user: UserRecord
    students: dict[str, StudentRecord] | None = None
    lessons: list[LessonRecord] | None = None
    materials: list[MaterialRecord] | None = None
    interactions: list[InteractionRecord] | None = None
    reviews: list[ReviewRecord] | None = None
    teacher_availability: list[AvailabilityRecord] | None = None
    operations: OperationsRecord | None = None


class AssessmentSessionRecord(Record):
    id: str
    student_id: str
    kind: str
    focus: str
    answered: int
    answered_items: list[str]
    max_items: int
    status: str  # the frontend shows the next item only while status == "in_progress"
    current_item: str
    current_item_id: str | None = None
    result: ProficiencyRecord | None = None


class EnvelopeRecord(Record):
    id: str
    type: str
    status: str
    phase: str
    result: dict[str, Any]
    error: dict[str, Any] | None = None


# --- request results ------------------------------------------------------------------
class CollectGoalResult(Record):
    summary: str | None = None
    focus_skills: list[str] = []
    question: str | None = None  # UC01 3a follow-up

    @model_validator(mode="after")
    def summary_or_question(self):
        if not self.summary and not self.question:
            raise ValueError("collect_goal result needs a summary or a follow-up question")
        return self


class ConfirmGoalResult(Record):
    profile: ProfileRecord


class InteractionResult(Record):
    interaction: InteractionRecord


class PracticeResult(Record):
    question: str
    item_id: str | None = None
    source: str | None = None


class PracticeAnswerResult(Record):
    feedback: str


class CompletedMaterial(Record):
    id: str
    title: str
    locator: str
    completed_at: str


class CompleteMaterialResult(Record):
    material: CompletedMaterial


class RecommendationResult(Record):
    recommendation: str
    evidence: Any = None


class PlanReviewResult(Record):
    plan: PlanRecord
    review_id: str | None = None


class ReplaceTeacherResult(Record):
    plan: PlanRecord | None = None
    review_id: str | None = None
    message: str | None = None


class Slot(Record):
    id: str
    starts_at: str
    ends_at: str


class RescheduleResult(Record):
    lesson_id: str
    proposed_slot: str | None = None
    slots: list[Slot] = []
    message: str = ""
    rationale: str | None = None


class ConfirmSlotResult(Record):
    lesson: LessonRecord


class BriefingResult(Record):
    briefing: str
    source_refs: list[Any] = []


class MaterialResult(Record):
    material: MaterialRecord


class AssessmentStepResult(Record):
    session_id: str


class FollowUpQuestion(Record):
    """Any request may pause with a question (NEEDS_INPUT); the user replies via context_id."""

    question: str
    options: list[Any] = []


class DecisionFollowUpResult(Record):
    """Internal requests that continue after a human decision; any dict is accepted."""


RESULT_CONTRACTS: dict[str, type[Record]] = {
    "collect_goal": CollectGoalResult,
    "confirm_goal": ConfirmGoalResult,
    "explain": InteractionResult,
    "resources": InteractionResult,
    "practice": PracticeResult,
    "practice_answer": PracticeAnswerResult,
    "complete_material": CompleteMaterialResult,
    "review_progress": RecommendationResult,
    "recommend_plan": RecommendationResult,
    "revise_plan": PlanReviewResult,
    "reschedule": RescheduleResult,
    "confirm_slot": ConfirmSlotResult,
    "replace_teacher": ReplaceTeacherResult,
    "lesson_briefing": BriefingResult,
    "generate_material": MaterialResult,
    "start_assessment": AssessmentStepResult,
    "decision_follow_up": DecisionFollowUpResult,
    "agent_correction": DecisionFollowUpResult,
}


# --- request inputs (what the frontend sends today) -----------------------------------------
class AnyInput(Record):
    pass


class CollectGoalInput(Record):
    goal_text: str
    focus_skills: list[str] = []


class ConfirmGoalInput(Record):
    goal_text: str | None = None
    goal_summary: str | None = None
    confirmed_summary: str | None = None  # contract.json name
    focus_skills: list[str] = []
    weekly_hours: float | None = None
    self_level: str | None = None
    target_level: str | None = None


class QuestionInput(Record):
    question: str = ""


class PracticeAnswerInput(Record):
    answer: str


class MaterialRefInput(Record):
    material_id: str


class RevisePlanInput(Record):
    reason: str
    requested_change: str | None = None


class LessonRefInput(Record):
    lesson_id: str


class RescheduleInput(LessonRefInput):
    slot: str | None = None  # frontend: local "YYYY-MM-DDTHH:mm"
    requested_time: str | None = None  # contract.json: ISO with offset

    @model_validator(mode="after")
    def needs_time(self):
        if not (self.slot or self.requested_time):
            raise ValueError("slot or requested_time is required")
        return self


class ConfirmSlotInput(Record):
    lesson_id: str | None = None
    slot: str | None = None
    starts_at: str | None = None
    slot_request_id: str | None = None
    slot_id: str | None = None


class GenerateMaterialInput(LessonRefInput):
    title: str | None = None
    topic: str | None = None
    level: str | None = None
    type: str | None = None
    guidance: str | None = None


class StartAssessmentInput(Record):
    kind: str
    focus: str = ""


class ReplyInput(Record):
    """Body of a reply to a request that is awaiting input (B3)."""

    answer: Any = None


INPUT_CONTRACTS: dict[str, type[Record]] = {
    "collect_goal": CollectGoalInput,
    "confirm_goal": ConfirmGoalInput,
    "explain": QuestionInput,
    "resources": QuestionInput,
    "practice": AnyInput,
    "practice_answer": PracticeAnswerInput,
    "complete_material": MaterialRefInput,
    "review_progress": AnyInput,
    "recommend_plan": AnyInput,
    "revise_plan": RevisePlanInput,
    "reschedule": RescheduleInput,
    "confirm_slot": ConfirmSlotInput,
    "replace_teacher": AnyInput,
    "lesson_briefing": LessonRefInput,
    "generate_material": GenerateMaterialInput,
    "start_assessment": StartAssessmentInput,
}


class ContractError(ValueError):
    pass


def _validate(model: type[Record], data: Any) -> dict:
    """Validate and return the data unchanged (validation must not reshape what agents produced)."""
    try:
        model.model_validate(data)
        return data
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'result'}: {e['msg']}" for e in exc.errors()[:5])
        raise ContractError(problems) from exc


def validate_input(request_type: str, data: Any) -> dict:
    return _validate(INPUT_CONTRACTS.get(request_type, AnyInput), data or {})


def validate_result(request_type: str, data: Any, *, awaiting_input: bool = False) -> dict:
    model = RESULT_CONTRACTS.get(request_type, DecisionFollowUpResult)
    if awaiting_input and isinstance(data, dict) and "question" in data and model is not CollectGoalResult:
        try:
            return _validate(model, data)
        except ContractError:
            return _validate(FollowUpQuestion, data)
    return _validate(model, data)
