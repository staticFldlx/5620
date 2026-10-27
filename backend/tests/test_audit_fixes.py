"""Regression checks for the Stage 1 demo audit; all writes are rolled back."""
from io import StringIO
import pytest
from django.core.management import call_command
from django.utils import timezone
from domain.governance.models import AgentTask, EscalationCase, IncidentRecord, RecoveryAttempt, ServiceRequest
from domain.learning.models import LearningPlan
from domain.learning import selectors as learning
from orchestration.task_queue import registry
from orchestration.task_queue.recovery import execute_retry
from agents.runtime.testing import make_runtime
from tests.conftest import key

pytestmark = pytest.mark.django_db


def test_completed_student_remains_in_teacher_workspace(emily):
    LearningPlan.objects.filter(student_id=key("student-ivy")).update(status="completed")
    workspace = emily.get("/workspace").json()
    assert workspace["students"][key("student-ivy")]["name"] == "Ivy Lin"
    assert emily.get("/workspace", student_id=key("student-ivy")).status_code == 200


def test_founder_followup_reaches_teacher_without_closing_exception(alex, emily):
    parent = EscalationCase.objects.filter(subject_type="business", assignee__email="alex.hu@example.com", status="open").first()
    assert parent
    response = alex.post(f"/cases/{parent.pk}/decision", {"action": "request_followup", "note": "Please check teacher times."})
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "followup_pending"
    child = EscalationCase.objects.get(subject_type="business", subject_id=str(parent.pk))
    reviews = emily.get("/workspace").json()["reviews"]
    assert any(r["id"] == str(child.pk) for r in reviews)
    assert emily.get(f"/reviews/{child.pk}").status_code == 200
    duplicate = alex.post(f"/cases/{parent.pk}/decision", {"action": "request_followup", "note": "Again"})
    assert duplicate.status_code >= 400
    reply = emily.post(f"/reviews/{child.pk}/decision", {"action": "answer", "note": "I have checked the timetable."})
    assert reply.status_code == 200, reply.content
    parent.refresh_from_db()
    assert parent.status == "open" and parent.outcome == "followup_received"
    assert any("checked the timetable" in e["summary"] for e in parent.evidence)
    assert str(child.pk) not in [c["id"] for c in alex.get("/workspace").json()["operations"]["cases"]]
    final = alex.post(f"/cases/{parent.pk}/decision", {"action": "resolve", "note": "Follow-up reviewed."})
    assert final.status_code == 200, final.content
    assert final.json()["status"] == "resolved"


def failed_briefing(emily, monkeypatch):
    original = registry.build_runtime
    monkeypatch.setattr(registry, "build_runtime", lambda cls, task: make_runtime([]))
    response = emily.post("/requests", {"type": "lesson_briefing", "input": {"lesson_id": key("L-018")}, "context_id": key("L-018")})
    assert response.status_code == 422, response.content
    request = ServiceRequest.objects.get(pk=response.json()["request"]["id"])
    assert request.status == "failed"
    source = request.tasks.latest("created_at")
    monkeypatch.setattr(registry, "build_runtime", original)
    incident = IncidentRecord.objects.create(subject="Temporary briefing failure", affected_components=["teaching_support"], status="diagnosed", evidence=[{"ref": f"task:{source.pk}", "summary": "Transient provider failure"}])
    return incident, source


def test_controlled_retry_runs_actual_task_and_verifies_request(emily, monkeypatch):
    incident, source = failed_briefing(emily, monkeypatch)
    result = execute_retry(str(incident.pk))
    assert result["verified"], result
    incident.refresh_from_db()
    source.request.refresh_from_db()
    assert incident.status == "resolved" and source.request.status == "completed"
    assert source.request.result["briefing"]
    assert RecoveryAttempt.objects.filter(source_task=source).count() == 1
    assert execute_retry(str(incident.pk))["execution_status"] == "skipped"
    assert source.children.count() == 1


def test_failed_retry_escalates_and_cannot_repeat(emily, monkeypatch):
    incident, source = failed_briefing(emily, monkeypatch)
    monkeypatch.setattr(registry, "build_runtime", lambda cls, task: make_runtime([]))
    result = execute_retry(str(incident.pk))
    assert not result["verified"]
    incident.refresh_from_db()
    assert incident.status == "escalated"
    execute_retry(str(incident.pk))
    assert source.children.count() == 1


def test_recovery_refuses_write_task(emily, monkeypatch):
    incident, source = failed_briefing(emily, monkeypatch)
    source.task_type = "planning.activate_plan"
    source.save(update_fields=["task_type"])
    result = execute_retry(str(incident.pk))
    assert not result["verified"] and source.children.count() == 0


def test_monitor_closes_resumed_incident_only_after_fresh_success():
    incident = IncidentRecord.objects.create(subject="Recovered agent", status="recovery_pending_verification", affected_components=["teaching_support"])
    call_command("monitor_agents", "--once", stdout=StringIO())
    incident.refresh_from_db()
    assert incident.status == "recovery_pending_verification"
    AgentTask.objects.create(task_type="teaching_support.lesson_briefing", target_agent="teaching_support", status="succeeded", started_at=timezone.now())
    call_command("monitor_agents", "--once", stdout=StringIO())
    incident.refresh_from_db()
    assert incident.status == "resolved" and incident.verification == "fresh_task_verified"


def test_full_monitor_cycle_detects_retries_verifies_closes_and_reports(emily, monkeypatch, alex):
    # Enough real failures for the configured anomaly threshold; the latest has a retryable request.
    for _ in range(5):
        _, source = failed_briefing(emily, monkeypatch)
    call_command("monitor_agents", "--once", stdout=StringIO())
    incident = IncidentRecord.objects.get(subject="teaching_support: high_failure_rate")
    assert incident.status == "resolved" and incident.verification == "retry_verified"
    assert RecoveryAttempt.objects.filter(source_task=source).count() == 1
    report = alex.get("/operations/maintenance-report").json()
    assert any(i["incident_id"] == str(incident.pk) and i["status"] == "resolved" for i in report["incidents"])
    call_command("monitor_agents", "--once", stdout=StringIO())
    assert IncidentRecord.objects.filter(subject="teaching_support: high_failure_rate").count() == 1
