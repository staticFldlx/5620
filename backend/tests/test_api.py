"""HTTP contract tests for the 20 operations in frontend/src/api/client.ts, plus permission paths."""

from datetime import UTC, datetime

import pytest
from django.test import Client
from django.utils import timezone

from access_control.identity import services as identity
from agents.runtime import AgentResult, AgentStatus
from domain.learning import services as learning_services
from domain.learning.models import AssessmentSession, LessonMaterial
from domain.learning.views import proficiency_view
from domain.governance.models import EscalationCase
from tests.conftest import Api, key

pytestmark = pytest.mark.django_db


def error_code(response) -> str:
    body = response.json()
    assert body["message"] == body["error"]["message"]  # the frontend reads `message`
    return body["error"]["code"]


# --- auth ----------------------------------------------------------------------------------------
def test_register_creates_a_student_with_a_default_profile(api):
    response = api.post("/auth/register", {"name": "Mia", "email": "mia@example.com", "password": "longenough"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "Student" and body["session"]
    api.headers = {"HTTP_AUTHORIZATION": f"Bearer {body['session']}"}
    workspace = api.get("/workspace").json()
    record = workspace["students"][body["user"]["id"]]
    assert record["profile"]["goal_summary"] == "Set your learning goal" and record["plan"] is None


def test_register_and_login_errors(api):
    assert error_code(api.post("/auth/register", {"name": "", "email": "bad", "password": "x"})) == "invalid_registration"
    assert api.post("/auth/register", {"name": "Ivy", "email": "IVY.LIN@example.com", "password": "longenough"}).status_code == 409
    response = api.post("/auth/login", {"email": "ivy.lin@example.com", "password": "wrong"})
    assert response.status_code == 401 and error_code(response) == "invalid_credentials"
    api.headers = {"HTTP_AUTHORIZATION": "Bearer forged-token"}
    assert api.get("/workspace").status_code == 401


# --- workspace ------------------------------------------------------------------------------------
def test_student_workspace_shape(ivy):
    body = ivy.get("/workspace").json()
    assert set(body) == {"user", "students", "lessons", "materials", "interactions"}
    record = body["students"][key("student-ivy")]
    assert record["plan"]["status"] == "active" and record["pending_plan"]["version"] == 2
    assert record["plan"]["stages"][1]["course_ref"] == "CAT-02"
    assert [a["status"] for a in record["assessments"]] == ["confirmed", "pending_review"]
    assert record["observation"].startswith("Ivy states a claim")
    assert record["material_records"][0]["material_id"] == key("M-01")
    assert {m["id"] for m in body["materials"]} == {key("M-01"), key("M-02")}
    escalated = next(i for i in body["interactions"] if i["status"] == "escalated")
    assert escalated["escalation"]["review_id"] == key("RV-Q09")
    assert ivy.get("/workspace", student_id=key("student-sophia")).status_code == 403


def test_teacher_workspace_and_assignment_scope(emily):
    body = emily.get("/workspace").json()
    assert set(body["students"]) == {key("student-ivy"), key("student-sophia")}  # Sophia only has a pending plan (A10)
    assert len(body["reviews"]) == 4 and {r["kind"] for r in body["reviews"]} == {"plan", "assessment", "question"}
    assert body["teacher_availability"][0] == {"day": "Tue", "start": "18:00", "end": "20:00"}
    one = emily.get("/workspace", student_id=key("student-sophia")).json()
    assert list(one["students"]) == [key("student-sophia")]

    identity.create_user(name="Tom", email="tom@example.com", password="longenough", role="teacher")
    tom = Api(Client()).login("tom@example.com", "longenough")
    assert tom.get("/workspace").json()["students"] == {}
    response = tom.get("/workspace", student_id=key("student-ivy"))
    assert response.status_code == 403 and error_code(response) == "forbidden_student_access"


def test_founder_workspace_has_operations_only(alex):
    body = alex.get("/workspace").json()
    assert set(body) == {"user", "operations"}
    ops = body["operations"]
    agents = {a["id"]: a for a in ops["agents"]}
    assert set(agents) == {"coordinator", "assessment", "consultant", "assistant", "technical"}  # public ids (A7)
    assert agents["assistant"]["status"] == "degraded"
    assert agents["coordinator"]["status"] == "healthy"  # all five agents are implemented
    assert {c["kind"] for c in ops["cases"]} == {"business", "technical"}
    assert len(ops["proposals"]) == 3 and ops["audit"][0]["action"]
    assert any(log["task_status"] == "failed" for log in ops["logs"])
    assert alex.get("/workspace", student_id=key("student-ivy")).status_code == 403


# --- requests -------------------------------------------------------------------------------------
def test_request_failure_is_422_with_envelope(ivy, settings):
    settings.AGENT_REGISTRY = {**settings.AGENT_REGISTRY, "teaching_support": "agents.missing.agent.MissingAgent"}
    response = ivy.post("/requests", {"type": "explain", "input": {"question": "?"}})
    assert response.status_code == 422 and error_code(response) == "agent_not_implemented"
    envelope = response.json()["request"]
    assert envelope["status"] == "failed" and envelope["type"] == "explain"
    assert ivy.get(f"/requests/{envelope['id']}").json()["status"] == "failed"


def test_request_validation_and_role_rules(ivy, emily):
    assert error_code(ivy.post("/requests", {"type": "nope"})) == "unknown_request_type"
    assert error_code(ivy.post("/requests", {"type": "start_assessment"})) == "unknown_request_type"  # internal type
    assert error_code(ivy.post("/requests", {"type": "practice_answer", "input": {}})) == "invalid_input"
    assert ivy.post("/requests", {"type": "lesson_briefing", "input": {"lesson_id": key("L-018")}}).status_code == 403
    assert emily.post("/requests", {"type": "explain", "input": {"question": "?"}}).status_code == 403
    assert error_code(emily.post("/requests", {"type": "review_progress", "input": {}})) == "student_id_required"
    assert error_code(ivy.post("/requests", {"type": "revise_plan", "input": {"reason": "x"}})) == "plan_review_pending"


def test_teacher_request_scoped_by_lesson_and_get_request_permissions(stubs, emily, ivy, alex):
    def briefing(task, runtime):
        return AgentResult(AgentStatus.OK, {"result": {"briefing": "Focus on evidence links.", "source_refs": []}})

    stubs["teaching_support.lesson_briefing"] = briefing
    response = emily.post("/requests", {"type": "lesson_briefing", "input": {"lesson_id": key("L-018")}, "context_id": key("L-018")})
    assert response.status_code == 200, response.content
    envelope = response.json()
    assert envelope["status"] == "completed" and envelope["result"]["briefing"] == "Focus on evidence links."
    assert ivy.get(f"/requests/{envelope['id']}").status_code == 200  # the request is about Ivy
    trace = alex.get(f"/requests/{envelope['id']}/trace").json()
    assert trace["tasks"][0]["agent_id"] == "assistant"


def test_reply_to_waiting_request_via_context_id(stubs, ivy):
    def collect(task, runtime):
        if "reply" not in task.payload:
            return AgentResult(AgentStatus.NEEDS_INPUT, {"result": {"question": "Which exam?"}, "phase": "follow_up_question"})
        return AgentResult(AgentStatus.OK, {"result": {"summary": task.payload["reply"]["answer"], "focus_skills": []}})

    stubs["coordinator.collect_goal"] = collect
    first = ivy.post("/requests", {"type": "collect_goal", "input": {"goal_text": "exam"}}).json()
    assert (first["status"], first["phase"]) == ("awaiting_confirmation", "follow_up_question")
    second = ivy.post("/requests", {"type": "collect_goal", "context_id": first["id"], "input": {"answer": "IELTS"}}).json()
    assert second["id"] == first["id"] and second["result"]["summary"] == "IELTS"


# --- assessments ------------------------------------------------------------------------------------
def assessment_agent(task, runtime):
    """Three fixed items, ids item-1..3 as the frontend sends them; low confidence at the end."""
    from access_control.identity.models import User

    student = User.objects.get(pk=task.student_id)
    if "reply" not in task.payload:
        items = [{"item_id": f"item-{n}", "prompt": f"Question {n}", "answer": None} for n in (1, 2, 3)]
        session = learning_services.create_assessment_session("assessment", student=student, type=task.payload["input"]["kind"], items=items)
    else:
        session = AssessmentSession.objects.get(pk=task.payload["previous"]["result"]["session_id"])
        session = learning_services.record_answer("assessment", session, **task.payload["reply"])
    if any(i["answer"] is None for i in session.items):
        return AgentResult(AgentStatus.NEEDS_INPUT, {"result": {"session_id": str(session.pk)}, "phase": "next_item"})
    learning_services.update_assessment_session("assessment", session, status="awaiting_review")
    record = learning_services.record_proficiency("assessment", session=session, overall_level="B1", confidence=0.62, feedback="Provisional")
    payload = {"result": {"session_id": str(session.pk), "assessment": proficiency_view(record)}, "subject_type": "assessment", "subject_id": str(record.pk), "resume": "assessment.apply_review"}
    return AgentResult(AgentStatus.NEEDS_ESCALATION, payload, confidence=0.62, reason="low_confidence")


def test_assessment_flow_answers_resume_and_review(stubs, ivy, emily):
    stubs["assessment.conduct_assessment"] = assessment_agent
    started = ivy.post("/assessments", {"student_id": key("student-ivy"), "kind": "milestone"})
    assert started.status_code == 200, started.content
    session = started.json()
    assert (session["status"], session["answered"], session["current_item"]) == ("in_progress", 0, "Question 1")
    sid = session["id"]
    assert ivy.post(f"/assessments/{sid}/answers", {"item_id": "item-1", "answer": "a"}).json()["answered"] == 1
    assert ivy.post(f"/assessments/{sid}/answers", {"item_id": "item-1", "answer": "again"}).json()["answered"] == 1  # idempotent
    assert error_code(ivy.post(f"/assessments/{sid}/answers", {"item_id": "item-2", "answer": "  "})) == "answer_required"
    ivy.post(f"/assessments/{sid}/answers", {"item_id": "item-2", "answer": "b"})
    final = ivy.post(f"/assessments/{sid}/answers", {"item_id": "item-3", "answer": "c"}).json()
    assert final["status"] == "awaiting_review" and final["result"]["confidence"] == 0.62
    assert ivy.get(f"/assessments/{sid}").json()["answered"] == 3
    review = next(r for r in emily.get("/workspace").json()["reviews"] if r["subject_id"] == final["result"]["id"])
    detail = emily.get(f"/reviews/{review['id']}").json()
    assert detail["subject"]["level"] == "B1"
    # apply_review is not implemented: the decision is stored, the follow-up reports why it stopped
    decided = emily.post(f"/reviews/{review['id']}/decision", {"action": "confirm_result", "note": "Matches class work"}).json()
    assert decided["review"]["status"] == "decided" and decided["follow_up"]["error"]["code"] == "no_stub"


def test_assessment_permissions(ivy, emily):
    assert ivy.post("/assessments", {"student_id": key("student-ivy"), "kind": "directed"}).status_code == 403
    assert emily.post("/assessments", {"student_id": key("student-ivy"), "kind": "initial"}).status_code == 403
    assert ivy.post("/assessments", {"student_id": key("student-sophia"), "kind": "initial"}).status_code == 403
    response = ivy.post("/assessments", {"student_id": key("student-ivy"), "kind": "initial"})
    assert response.status_code == 200 and response.json()["status"] == "in_progress"  # the real agent, offline script
    old = ivy.get(f"/assessments/{key('A-104')}").json()  # a ProficiencyRecord id resolves to its session
    assert old["result"]["status"] == "pending_review"
    assert error_code(ivy.post(f"/assessments/{key('A-104')}/answers", {"item_id": "item-9", "answer": "x"})) == "assessment_not_awaiting_answer"


# --- reviews ----------------------------------------------------------------------------------------
def test_review_detail_and_question_answer(emily, ivy):
    detail = emily.get(f"/reviews/{key('RV-019-v2')}").json()
    assert detail["review"]["kind"] == "plan" and detail["subject"]["version"] == 2 and detail["evidence"]
    assert error_code(emily.post(f"/reviews/{key('RV-Q09')}/decision", {"action": "answer", "note": ""})) == "note_required"
    decided = emily.post(f"/reviews/{key('RV-Q09')}/decision", {"action": "answer", "note": "Ask for written permission."}).json()
    assert decided["updated_subject"]["answer"] == "Ask for written permission." and decided["follow_up"] is None
    answered = next(i for i in ivy.get("/workspace").json()["interactions"] if i["id"] == key("RQ-09"))
    assert answered["status"] == "completed" and answered["escalation"]["status"] == "resolved"
    assert emily.post(f"/reviews/{key('RV-Q09')}/decision", {"action": "answer", "note": "again"}).status_code == 409
    assert ivy.get(f"/reviews/{key('RV-021')}").status_code == 403


def test_seeded_plan_reviews_can_be_approved(emily, alex):
    """Seeded review cases point at the planning task that submitted the plan, like real ones."""
    from domain.learning import selectors as learning

    decided = emily.post(f"/reviews/{key('RV-019-v2')}/decision", {"action": "approve", "note": "More guided practice fits."}).json()
    assert decided["follow_up"]["status"] == "completed", decided["follow_up"]["error"]
    ivy = learning.student(key("student-ivy"))
    assert str(learning.active_plan(ivy).pk) == key("PL-019-v2") and learning.pending_plan(ivy) is None

    decided = emily.post(f"/reviews/{key('RV-021')}/decision", {"action": "approve", "note": "Matches the workplace goal."}).json()
    assert decided["follow_up"]["status"] == "completed", decided["follow_up"]["error"]
    assert str(learning.active_plan(learning.student(key("student-sophia"))).pk) == key("PL-021")

    closed = alex.post(f"/cases/{key('ES-12')}/decision", {"action": "widen_match", "note": "Handled outside the platform."}).json()
    assert closed["status"] == "resolved" and closed["follow_up"] is None


# --- teaching records ---------------------------------------------------------------------------------
def test_observation_availability_and_lesson_records(emily, ivy, monkeypatch):
    # Fixture lessons have fixed dates; freeze the clock before L-021 (2026-10-15) so it is still upcoming.
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 10, 14, tzinfo=UTC))
    saved = emily.patch(f"/students/{key('student-ivy')}/observation", {"note": "Clearer claims now."}).json()
    assert saved["note"] == "Clearer claims now." and saved["teacher_id"] == key("teacher-emily")
    assert ivy.get("/workspace").json()["students"][key("student-ivy")]["observation"] == "Clearer claims now."

    response = emily.patch("/teachers/me/availability", {"timezone": "Australia/Sydney", "availability": [{"day": "Tue", "start": "18:00", "end": "20:00"}]})
    assert response.status_code == 409 and error_code(response) == "availability_conflicts_booking"
    windows = [{"day": "Tue", "start": "18:00", "end": "20:00"}, {"day": "Thu", "start": "17:00", "end": "20:00"}]
    assert emily.patch("/teachers/me/availability", {"timezone": "Australia/Sydney", "availability": windows}).json()["availability"] == windows

    lesson = emily.patch(f"/lessons/{key('L-018')}", {"attendance": "attended", "feedback": "Good evidence link."}).json()
    assert (lesson["status"], lesson["attendance"], lesson["feedback"]) == ("completed", "attended", "Good evidence link.")
    assert error_code(emily.patch(f"/lessons/{key('L-021')}", {"attendance": "attended", "feedback": "x"})) == "lesson_not_started"
    assert ivy.patch(f"/lessons/{key('L-018')}", {"attendance": "absent"}).status_code == 403


def test_material_visibility_and_approval(emily, ivy):
    draft = LessonMaterial.objects.create(lesson_id=key("L-018"), title="Draft", content="v1", status="draft")
    assert ivy.get(f"/materials/{draft.pk}").status_code == 404  # students never see drafts
    assert emily.get(f"/materials/{draft.pk}").json()["status"] == "draft"
    approved = emily.patch(f"/materials/{draft.pk}", {"content": "v2", "status": "approved"}).json()
    assert approved["status"] == "approved" and approved["content"] == "v2"
    assert ivy.get(f"/materials/{draft.pk}").json()["content"] == "v2"
    assert str(draft.pk) in next(lesson for lesson in ivy.get("/workspace").json()["lessons"] if lesson["id"] == key("L-018"))["material_ids"]
    assert emily.patch(f"/materials/{draft.pk}", {"content": "v3", "action": "save"}).json()["status"] == "draft"  # contract.json format


# --- founder operations --------------------------------------------------------------------------------
def test_cases_agents_and_proposals(alex, emily):
    business = alex.get(f"/cases/{key('ES-13')}").json()
    assert business["kind"] == "business" and business["status"] == "pending"
    technical = alex.get(f"/cases/{key('IN-014')}").json()
    assert technical["kind"] == "technical" and technical["proposal_id"] == key("UP-08")
    assert error_code(alex.post(f"/cases/{key('IN-014')}/decision", {"action": "resolve", "note": "x"})) == "use_proposal_decision"
    decided = alex.post(f"/cases/{key('ES-13')}/decision", {"action": "approve_resolution", "note": "Scope confirmed."}).json()
    assert decided["status"] == "resolved" and decided["decision"].startswith("resolve")
    assert emily.get(f"/cases/{key('ES-13')}").status_code == 403

    paused = alex.post("/agents/assistant/decision", {"action": "pause", "note": "Wrong sources"}).json()
    assert paused["status"] == "paused" and paused["agent"]["status"] == "paused"

    correction = alex.post(
        "/agents/technical/decision",
        {
            "action": "request_correction",
            "note": "Check the index",
        },
    ).json()

    assert correction["status"] == "requested"

    follow_up = correction["follow_up"]

    # A note no executor can apply becomes a manual proposal awaiting the Founder's approval.
    assert follow_up["status"] == "pending_review"
    assert follow_up["error"] is None
    proposal = follow_up["result"]["proposal"]
    assert proposal["type"] == "manual" and proposal["status"] == "pending"

    approval_case = EscalationCase.objects.get(
        task__request_id=follow_up["id"],
        task__task_type="tech_operations.apply_correction",
        kind=EscalationCase.Kind.APPROVAL,
        status=EscalationCase.Status.OPEN,
    )

    assert approval_case.subject_type == "proposal" and approval_case.subject_id == proposal["id"]

    assert alex.post("/agents/unknown/decision", {"action": "pause", "note": "x"}).status_code == 404

    assert alex.get(f"/proposals/{key('UP-07')}").json()["execution"]["status"] == "not_started"
    assert error_code(alex.post(f"/proposals/{key('UP-07')}/decision", {"action": "reject", "note": ""})) == "note_required"
    rejected = alex.post(f"/proposals/{key('UP-07')}/decision", {"action": "reject", "note": "Licences unclear"}).json()
    assert rejected["status"] == "rejected" and rejected["decision"] == "reject: Licences unclear" and rejected["follow_up"] is None
    approved = alex.post(f"/proposals/{key('UP-08')}/decision", {"action": "approve", "note": "Proceed"}).json()
    # Founder review has no executor: approval is recorded and a person rebuilds the index.
    assert approved["status"] == "approved" and approved["execution"]["status"] == "manual_review"
    assert approved["follow_up"]["status"] == "completed"
    audit = alex.get("/workspace").json()["operations"]["audit"]
    assert {"proposal.approved", "proposal.rejected", "agent.paused", "escalation.resolved"} <= {a["action"] for a in audit}


def test_cors_preflight_and_request_id(client, settings):
    settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
    response = client.options("/api/v1/workspace", HTTP_ORIGIN="http://localhost:5173", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET")
    assert response.status_code == 204 and response["Access-Control-Allow-Origin"] == "http://localhost:5173"
    other = client.options("/api/v1/workspace", HTTP_ORIGIN="http://evil.example", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET")
    assert "Access-Control-Allow-Origin" not in other
    assert client.get("/api/v1/workspace")["X-Request-ID"]
