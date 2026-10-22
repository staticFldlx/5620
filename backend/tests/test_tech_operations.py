"""AI Technical Manager: Founder corrections (UC09 5a, AR12), proposal execution and monitoring (UC10).

The real TechOperationsAgent runs with LLM_PROVIDER=fake, so agents/tech_operations/fake.py supplies
the model replies (correction drafts and incident diagnoses).
"""

from io import StringIO

import pytest
from django.core.management import call_command

from agents.runtime import RequestContext, TaskInput
from agents.runtime.testing import make_runtime
from agents.tech_operations.agent import TechOperationsAgent
from domain.governance import selectors as governance
from domain.governance import services as gov
from domain.governance.models import AgentTask, EscalationCase, IncidentRecord, ServiceRequest, UpdateProposal
from orchestration.task_queue import registry
from tests.conftest import key

pytestmark = pytest.mark.django_db


def request_correction(alex, note):
    response = alex.post("/agents/technical/decision", {"action": "request_correction", "note": note})
    assert response.status_code == 200, response.content
    return response.json()["follow_up"]


def decide(alex, proposal_id, action, note="Checked the evidence."):
    version = alex.get(f"/proposals/{proposal_id}").json()["version"]
    response = alex.post(f"/proposals/{proposal_id}/decision", {"action": action, "note": note, "version": version})
    assert response.status_code == 200, response.content
    return response.json()


# --- Founder corrections -----------------------------------------------------------------------------
def test_timeout_note_becomes_an_executable_proposal_applied_after_approval(alex):
    follow_up = request_correction(alex, "Raise the Teaching Assistant timeout to 60 seconds")
    assert follow_up["status"] == "pending_review"
    proposal = follow_up["result"]["proposal"]
    assert proposal["type"] == "configuration" and proposal["status"] == "pending"
    assert UpdateProposal.objects.get(pk=proposal["id"]).payload == {
        "action": "update_agent_setting", "agent_id": "teaching_support", "setting": "timeout_seconds", "new_value": 60,
    }
    case = EscalationCase.objects.get(subject_type="proposal", subject_id=proposal["id"])
    assert (case.kind, case.status, case.resume_task_type) == ("approval", "open", "tech_operations.execute_proposal")
    assert governance.agent_timeout_override("teaching_support") is None  # nothing changes before approval

    decided = decide(alex, proposal["id"], "approve")
    assert decided["execution"]["status"] == "succeeded"
    assert governance.agent_timeout_override("teaching_support") == 60
    case.refresh_from_db()
    assert case.status == "resolved"
    assert ServiceRequest.objects.get(pk=follow_up["id"]).status == "completed"  # executed in the paused request


def test_same_timeout_as_a_waiting_proposal_reuses_it(alex):
    follow_up = request_correction(alex, "Raise the Teaching Assistant timeout to 45 seconds")  # seeded UP-09
    assert follow_up["status"] == "completed" and follow_up["result"]["proposal"]["id"] == key("UP-09")
    assert not EscalationCase.objects.filter(subject_type="proposal", subject_id=key("UP-09")).exists()


def test_rejected_correction_changes_nothing_and_closes_the_request(alex):
    follow_up = request_correction(alex, "Set the Course Consultant timeout to 20 seconds")
    proposal_id = follow_up["result"]["proposal"]["id"]
    decided = decide(alex, proposal_id, "reject", note="Not needed now.")
    assert decided["status"] == "rejected" and decided["follow_up"]["status"] == "completed"
    assert governance.agent_timeout_override("planning") is None


def test_other_notes_become_manual_proposals(alex):
    follow_up = request_correction(alex, "Rebuild the retrieval index from the approved corpus")
    proposal = follow_up["result"]["proposal"]
    assert proposal["type"] == "manual" and proposal["after"] and proposal["validation"]
    decided = decide(alex, proposal["id"], "approve")
    assert decided["execution"]["status"] == "manual_review" and decided["follow_up"]["status"] == "completed"


def test_llm_outage_still_records_the_note_as_a_manual_proposal(alex, monkeypatch):
    monkeypatch.setattr(registry, "build_runtime", lambda cls, task: make_runtime([]))  # every LLM call fails
    note = "Raise the Teaching Assistant timeout to 45 seconds"
    proposal = request_correction(alex, note)["result"]["proposal"]
    assert proposal["type"] == "manual" and proposal["after"] == note


def test_only_the_founder_or_the_system_may_run_technical_tasks():
    task = TaskInput("task-1", "tech_operations.apply_correction", None, {"input": {"note": "x"}}, RequestContext("request-1", "user-1", "teacher"))
    assert TechOperationsAgent(make_runtime([])).execute_task(task).reason == "permission_denied"


# --- seeded proposals ------------------------------------------------------------------------------------
def test_seeded_proposals_execute_after_approval(alex):
    configuration = decide(alex, key("UP-09"), "approve")
    assert configuration["execution"]["status"] == "succeeded" and configuration["follow_up"]["status"] == "completed"
    assert governance.agent_timeout_override("teaching_support") == 45
    corpus = decide(alex, key("UP-07"), "approve")
    assert corpus["execution"]["status"] == "manual_review" and corpus["follow_up"]["status"] == "completed"


# --- monitoring cycle (UC10) -------------------------------------------------------------------------------
def test_monitoring_detects_diagnoses_and_recovers_a_paused_agent(alex):
    gov.set_agent_state(governance.first_founder(), "teaching_support", status="paused", note="Wrong sources")
    for _ in range(5):  # every task of a paused agent fails
        AgentTask.objects.create(task_type="teaching_support.answer_question", target_agent="teaching_support", status="failed", reason="agent_paused")

    out = StringIO()
    call_command("monitor_agents", "--once", stdout=out)
    assert "monitoring completed: 1 anomalies, 1 new incident(s) diagnosed" in out.getvalue()
    request = ServiceRequest.objects.filter(type="system_monitoring").latest("created_at")
    assert (request.status, request.actor_role) == ("completed", "system")

    incident = IncidentRecord.objects.get(subject="teaching_support: high_failure_rate")
    assert incident.status == "awaiting_approval" and "paused" in incident.diagnosis
    proposal = UpdateProposal.objects.get(incident=incident, change_type="recovery")
    assert proposal.payload["action"] == "resume_agent" and proposal.payload["agent_id"] == "teaching_support"
    assert governance.agent_state("teaching_support").status == "paused"  # nothing runs before approval

    decided = decide(alex, str(proposal.pk), "approve")
    assert decided["execution"]["status"] == "succeeded"
    assert governance.agent_state("teaching_support").status == "healthy"
    incident.refresh_from_db()
    assert incident.status == "recovery_pending_verification"

    call_command("monitor_agents", "--once", stdout=StringIO())  # the open incident is not duplicated
    assert IncidentRecord.objects.filter(subject="teaching_support: high_failure_rate").count() == 1
