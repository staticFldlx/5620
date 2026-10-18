
"""Pydantic-only unit tests for Planning schemas; no DB or LLM required."""

import json
import math

import pytest
from pydantic import ValidationError

from agents.planning.schemas import (
    FounderCaseDecision,
    GeneratePlanInput,
    PlanDraft,
    PlanResult,
    PlanRevisionRequest,
    PlanReviewDecision,
    PlanStageDraft,
    RevisePlanTaskInput,
)
from orchestration.task_queue import contracts


@pytest.fixture
def draft_data():
    return {
        "weekly_hours": 6,
        "stages": [
            {
                "title": "Academic Writing",
                "topics": ["Essay structure", "Grammar"],
                "milestone": "Write a B1 essay",
                "start_week": 1,
                "end_week": 4,
                "course_codes": ["B1-WRITING"],
            }
        ],
        "rationale": "Based on the confirmed proficiency profile",
    }


@pytest.fixture
def plan_record():
    # Mirrors learning.views.plan_view; the plan is already persisted.
    return {
        "id": "plan-123",
        "version": 1,
        "status": "pending_review",
        "stage_index": 0,
        "teacher": None,
        "weekly_hours": 6,
        "stages": [
            {
                "title": "Academic Writing",
                "course_ref": "B1-WRITING",
                "start_week": 1,
                "end_week": 4,
                "topics": ["Essay structure", "Grammar"],
                "milestone": "Write a B1 essay",
                "status": "upcoming",
            }
        ],
        "reason": "Based on the confirmed proficiency profile",
        "review_id": "",
        "approved_at": None,
    }


def test_generate_input_accepts_dispatcher_upstream():
    task = GeneratePlanInput.model_validate(
        {
            "input": {"kind": "initial", "focus": "writing"},
            "context_id": "ctx-1",
            "upstream": {"session_id": "session-1"},
            "upstream_data": {"result": {"session_id": "session-1"}},
        }
    )
    assert task.upstream["session_id"] == "session-1"


def test_generate_input_accepts_approval_resume():
    task = GeneratePlanInput.model_validate(
        {
            "input": {"kind": "initial"},
            "decision": {"action": "approve", "note": "  Looks good  ", "decided_by": "teacher-1"},
            "case_id": "case-1",
            "subject_id": "plan-123",
        }
    )
    assert isinstance(task.decision, PlanReviewDecision)
    assert task.decision.note == "Looks good"
    assert task.subject_id == "plan-123"


def test_generate_input_accepts_founder_escalation_resume():
    task = GeneratePlanInput.model_validate(
        {
            "input": {},
            "decision": {
                "action": "request_teacher",
                "note": "Assign another teacher",
                "decided_by": "founder-1",
                "requested_action": "request_followup",
            },
        }
    )
    assert isinstance(task.decision, FounderCaseDecision)


@pytest.mark.parametrize("action,note", [("reject", "No"), ("approve", "  ")])
def test_plan_review_rejects_invalid_action_or_blank_note(action, note):
    with pytest.raises(ValidationError):
        PlanReviewDecision(action=action, note=note)


def test_revision_request_strips_reason_and_checks_required():
    request = PlanRevisionRequest(reason="  More writing  ")
    assert request.reason == "More writing"
    with pytest.raises(ValidationError):
        PlanRevisionRequest(reason="  ")


def test_direct_revision_requires_reason():
    task = RevisePlanTaskInput.model_validate({"input": {"reason": "Need more writing"}})
    assert task.input["reason"] == "Need more writing"
    with pytest.raises(ValidationError):
        RevisePlanTaskInput.model_validate({"input": {"requested_change": "More writing"}})


def test_automatic_replan_accepts_original_assessment_input():
    task = RevisePlanTaskInput.model_validate(
        {
            "input": {"kind": "milestone", "focus": "writing"},
            "upstream": {"session_id": "session-2"},
            "upstream_data": {"result": {"session_id": "session-2"}},
        }
    )
    assert task.input["focus"] == "writing"


def test_revision_resume_accepts_review_decision():
    task = RevisePlanTaskInput.model_validate(
        {
            "input": {"reason": "More writing"},
            "decision": {"action": "request_changes", "note": "Add grammar"},
            "subject_id": "plan-123",
            "case_id": "case-123",
        }
    )
    assert task.decision.action == "request_changes"


def test_draft_round_trip_json(draft_data):
    draft = PlanDraft.model_validate(draft_data)
    assert json.loads(draft.model_dump_json())["weekly_hours"] == 6
    assert PlanDraft.model_validate_json(draft.model_dump_json()) == draft


@pytest.mark.parametrize("hours", [0, -2, math.inf, -math.inf, math.nan])
def test_draft_rejects_invalid_weekly_hours(draft_data, hours):
    draft_data["weekly_hours"] = hours
    with pytest.raises(ValidationError):
        PlanDraft.model_validate(draft_data)


def test_draft_requires_a_stage(draft_data):
    draft_data["stages"] = []
    with pytest.raises(ValidationError):
        PlanDraft.model_validate(draft_data)


@pytest.mark.parametrize("field", ["title", "milestone"])
def test_stage_rejects_blank_text(draft_data, field):
    draft_data["stages"][0][field] = "  "
    with pytest.raises(ValidationError):
        PlanDraft.model_validate(draft_data)


def test_stage_rejects_blank_topics(draft_data):
    draft_data["stages"][0]["topics"] = ["  "]
    with pytest.raises(ValidationError):
        PlanDraft.model_validate(draft_data)


@pytest.mark.parametrize("start,end", [(0, 2), (4, 3)])
def test_stage_rejects_invalid_week_range(draft_data, start, end):
    draft_data["stages"][0].update(start_week=start, end_week=end)
    with pytest.raises(ValidationError):
        PlanDraft.model_validate(draft_data)


def test_stage_normalises_course_codes_and_rejects_duplicates(draft_data):
    stage = PlanStageDraft.model_validate({**draft_data["stages"][0], "course_codes": [" B1-WRITING "]})
    assert stage.course_codes == ["B1-WRITING"]
    with pytest.raises(ValidationError):
        PlanStageDraft.model_validate({**draft_data["stages"][0], "course_codes": ["C1", " C1 "]})


@pytest.mark.parametrize("codes", [["X" * 33], ["  "], [123]])
def test_stage_rejects_invalid_course_codes(draft_data, codes):
    with pytest.raises(ValidationError):
        PlanStageDraft.model_validate({**draft_data["stages"][0], "course_codes": codes})


def test_draft_rejects_unknown_fields(draft_data):
    with pytest.raises(ValidationError):
        PlanDraft.model_validate({**draft_data, "approved_at": "not-for-llm"})


def test_plan_result_matches_frontend_revision_contract(plan_record):
    result = PlanResult.model_validate(
        {
            "plan": plan_record,
            "subject_id": "plan-123",
            "resume": "planning.revise_plan",
        }
    )
    payload = result.model_dump(mode="json")
    assert contracts.validate_result("revise_plan", payload)["plan"]["id"] == "plan-123"
    assert json.loads(result.model_dump_json())["resume"] == "planning.revise_plan"


def test_plan_result_can_join_assessment_pipeline_output(plan_record):
    result = PlanResult(plan=plan_record, subject_id="plan-123", resume="planning.generate_plan")
    # For start_assessment the first task supplies session_id. The result
    # contract permits additional keys, which _consolidate normally merges.
    combined = {"session_id": "session-123", **result.model_dump(mode="json")}
    assert contracts.validate_result("start_assessment", combined)["session_id"] == "session-123"


def test_plan_result_rejects_wrong_subject_id(plan_record):
    with pytest.raises(ValidationError):
        PlanResult(plan=plan_record, subject_id="different-id", resume="planning.generate_plan")


def test_plan_result_disallows_unregistered_activate_task(plan_record):
    with pytest.raises(ValidationError):
        PlanResult(plan=plan_record, subject_id="plan-123", resume="planning.activate_plan")


def test_plan_result_requires_frontend_plan_fields():
    with pytest.raises(ValidationError):
        PlanResult(plan={"id": "plan-123"}, subject_id="plan-123", resume="planning.generate_plan")
