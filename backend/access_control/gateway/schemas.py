"""Request bodies, as the frontend client (src/api/client.ts) sends them. Responses reuse the
record shapes in orchestration.task_queue.contracts."""

from __future__ import annotations

from typing import Any

from ninja import Schema

from orchestration.task_queue.contracts import AgentRecord, CaseRecord, EnvelopeRecord, ProposalRecord, ReviewRecord, UserRecord


class RegisterIn(Schema):
    name: str
    email: str
    password: str


class LoginIn(Schema):
    email: str
    password: str


class SessionOut(Schema):
    session: str
    user: UserRecord


class RequestIn(Schema):
    type: str
    input: dict[str, Any] = {}
    student_id: str | None = None
    context_id: str | None = None


class AssessmentIn(Schema):
    student_id: str
    kind: str  # initial | milestone | directed
    focus: str | None = None


class AnswerIn(Schema):
    item_id: str
    answer: str


class ReviewDecisionIn(Schema):
    action: str  # approve | request_changes | confirm_result | answer
    note: str = ""
    corrected_level: str | None = None


class ReviewDetailOut(Schema):
    review: ReviewRecord
    subject: Any = None
    evidence: str


class ReviewDecisionOut(Schema):
    review: ReviewRecord
    updated_subject: Any = None
    follow_up: EnvelopeRecord | None = None


class ObservationIn(Schema):
    note: str


class ObservationOut(Schema):
    note: str
    updated_at: str
    teacher_id: str


class WindowIn(Schema):
    day: str
    start: str
    end: str


class AvailabilityIn(Schema):
    timezone: str = "Australia/Sydney"
    availability: list[WindowIn]


class AvailabilityOut(Schema):
    timezone: str
    availability: list[WindowIn]


class LessonPatchIn(Schema):
    attendance: str | None = None
    feedback: str | None = None


class MaterialPatchIn(Schema):
    content: str
    status: str | None = None  # draft | approved (frontend)
    action: str | None = None  # save | approve (contract.json)


class CaseDecisionIn(Schema):
    action: str
    note: str = ""


class CaseDecisionOut(CaseRecord):
    follow_up: EnvelopeRecord | None = None


class AgentDecisionIn(Schema):
    action: str  # pause | resume | request_correction
    note: str = ""
    case_id: str | None = None


class AgentDecisionOut(Schema):
    agent: AgentRecord
    status: str
    follow_up: EnvelopeRecord | None = None


class ProposalDecisionIn(Schema):
    action: str  # approve | reject
    note: str = ""
    version: int | None = None


class ProposalDecisionOut(ProposalRecord):
    follow_up: EnvelopeRecord | None = None

