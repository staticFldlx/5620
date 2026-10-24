import pytest
from tests.test_assessment_acceptance import agent, start, answer, STEADY
from domain.governance.models import AgentTask, EscalationCase
from domain.learning.models import AssessmentSession
from domain.learning import services
from orchestration.task_queue import dispatcher, registry

@pytest.mark.django_db
def test_saved_answer_retry_retains_valid_score(agent, ivy, settings):
    session = start(ivy)
    settings.AGENT_TASK_EXECUTION = "worker"
    answer(ivy, session, STEADY)
    task = AgentTask.objects.filter(task_type="assessment.conduct_assessment", status="queued").latest("created_at")
    stored = AssessmentSession.objects.get(pk=session["id"])
    services.record_answer("assessment", stored, item_id="item-1", answer=STEADY)
    dispatcher.drain(task.request)
    stored.refresh_from_db()
    assert stored.items[0].get("score") is not None, stored.items[0]

@pytest.mark.django_db
@pytest.mark.parametrize("answer_text, count, expected", [(STEADY, 4, "completed"), ("yes", 6, "escalated")])
@pytest.mark.parametrize("session_written", [True, False])
def test_retry_after_final_session_write_restores_handoff(agent, ivy, settings, answer_text, count, expected, session_written):
    session = start(ivy)
    for _ in range(count - 1):
        session = answer(ivy, session, answer_text).json()
    settings.AGENT_TASK_EXECUTION = "worker"
    answer(ivy, session, answer_text)
    task = AgentTask.objects.filter(task_type="assessment.conduct_assessment", status="queued").latest("created_at")
    ti = dispatcher._task_input(task)
    cls = registry.load_agent_class("assessment")
    result = cls(registry.build_runtime(cls, ti)).execute_task(ti)
    stored = AssessmentSession.objects.get(pk=session["id"])
    assert stored.status in ("completed", "awaiting_review")
    if not session_written:
        # Simulate the earlier boundary: proficiency committed, session status not yet updated.
        stored.status = "in_progress"
        stored.save(update_fields=["status"])
    # Crash after agent has written the result but before dispatcher handles it.
    dispatcher.drain(task.request)
    task.request.refresh_from_db()
    assert task.request.status == expected, task.request.error
    stored.refresh_from_db()
    assert stored.status == ("completed" if expected == "completed" else "awaiting_review")
    if expected == "completed":
        assert task.request.tasks.filter(task_type="planning.generate_plan").count() == 1
    else:
        assert EscalationCase.objects.filter(subject_id=stored.proficiency.pk).count() == 1
        assert not task.request.tasks.filter(task_type="planning.generate_plan").exists()

@pytest.mark.django_db
def test_second_start_while_first_answer_is_queued_is_rejected(agent, ivy, settings):
    session = start(ivy)
    settings.AGENT_TASK_EXECUTION = "worker"
    answer(ivy, session, STEADY)
    response = ivy.post("/assessments", {"student_id": str(AssessmentSession.objects.get(pk=session["id"]).student_id), "kind": "initial"})
    task = AgentTask.objects.filter(task_type="assessment.conduct_assessment", status="queued").latest("created_at")
    dispatcher.run_task(task)
    task.refresh_from_db()
    assert task.status == "failed" and task.reason == "assessment_in_progress", (task.status, task.reason)

@pytest.mark.django_db
@pytest.mark.parametrize("stored_score", [None, 0.8])
def test_retry_reuses_existing_score_and_only_generates_next_item(agent, ivy, settings, stored_score):
    session = start(ivy)
    settings.AGENT_TASK_EXECUTION = "worker"
    answer(ivy, session, STEADY)
    task = AgentTask.objects.filter(task_type="assessment.conduct_assessment", status="queued").latest("created_at")
    stored = AssessmentSession.objects.get(pk=session["id"])
    services.record_answer("assessment", stored, item_id="item-1", answer=STEADY)
    stored.items[0].update(score=stored_score, agreement=0.7, off_task=False,
        estimate=2.6 if stored_score is not None else None, feedback="Already scored")
    services.update_assessment_session("assessment", stored, items=stored.items)
    dispatcher.drain(task.request)
    stored.refresh_from_db()
    assert stored.items[0]["score"] == stored_score
    assert stored.items[0]["feedback"] == "Already scored"
    assert len(stored.items) == 2 and stored.items[1]["prompt"].startswith("[")
    task.refresh_from_db()
    decisions = [row.get("decision") for row in task.trace]
    assert "item_bank_fallback" not in decisions

@pytest.mark.django_db
def test_late_retry_never_publishes_a_rejected_result(agent, ivy, settings):
    session = start(ivy)
    for _ in range(5):
        session = answer(ivy, session, "yes").json()
    settings.AGENT_TASK_EXECUTION = "worker"
    answer(ivy, session, "yes")
    task = AgentTask.objects.filter(task_type="assessment.conduct_assessment", status="queued").latest("created_at")
    ti = dispatcher._task_input(task)
    cls = registry.load_agent_class("assessment")
    cls(registry.build_runtime(cls, ti)).execute_task(ti)
    stored = AssessmentSession.objects.get(pk=session["id"])
    services.update_proficiency("assessment", stored.proficiency, status="changes_requested")
    services.update_assessment_session("assessment", stored, status="completed")
    dispatcher.drain(task.request)
    task.request.refresh_from_db()
    assert task.request.status == "failed"
    assert task.request.error["code"] == "assessment_changes_requested"
    assert not task.request.tasks.filter(task_type="planning.generate_plan").exists()


@pytest.mark.django_db
def test_new_direct_answer_to_closed_session_is_rejected_without_uuid_error(agent, ivy):
    from agents.assessment.agent import AssessmentAgent
    from agents.runtime.testing import make_task, make_runtime
    session = start(ivy)
    for _ in range(4):
        session = answer(ivy, session, STEADY).json()
    task = make_task("assessment.conduct_assessment", {
        "input": {"kind": "initial"}, "previous": {"result": {"session_id": session["id"]}},
        "reply": {"item_id": "item-4", "answer": STEADY},
    }, student_id=str(AssessmentSession.objects.get(pk=session["id"]).student_id))
    result = AssessmentAgent(make_runtime()).execute_task(task)
    assert result.reason == "session_closed"
