"""AI Course Coordinator: goal intake with follow-up questions, profile confirmation, completed materials,
and the onboarding loop UC01 -> UC02 -> UC03 with the real agents.

The real CoordinatorAgent runs with LLM_PROVIDER=fake, so orchestration/coordinator/fake.py supplies the
model replies (keyword rules: a short goal gets a purpose question, missing lesson times a time question).
"""

from zoneinfo import ZoneInfo

import pytest
from django.test import Client

from agents.runtime.testing import make_runtime
from domain.governance.models import EscalationCase
from domain.learning import selectors as learning
from domain.learning.models import LearningHistoryEntry
from orchestration.coordinator import fake
from orchestration.task_queue import registry
from tests.conftest import Api, key

pytestmark = pytest.mark.django_db

STEADY = " ".join(["evidence"] * 16)  # the offline assessment script scores answers by length


def new_student(email="nova@example.com") -> tuple[Api, str]:
    api = Api(Client())
    response = api.post("/auth/register", {"name": "Nova Lee", "email": email, "password": "longenough"})
    assert response.status_code == 200, response.content
    api.headers = {"HTTP_AUTHORIZATION": f"Bearer {response.json()['session']}"}
    return api, response.json()["user"]["id"]


def collect(api, goal, skills=("Reading", "Writing")):
    response = api.post("/requests", {"type": "collect_goal", "input": {"goal_text": goal, "focus_skills": list(skills)}})
    assert response.status_code == 200, response.content
    return response.json()


def answer(api, envelope, text):
    response = api.post("/requests", {"type": "collect_goal", "context_id": envelope["id"], "input": {"answer": text}})
    assert response.status_code == 200, response.content
    return response.json()


def confirm(api, summary, **overrides):
    body = {"goal_text": "I need English", "goal_summary": summary, "focus_skills": ["Reading", "Writing"], "weekly_hours": 4, "self_level": "B2", "target_level": "C1"}
    return api.post("/requests", {"type": "confirm_goal", "input": {**body, **overrides}})


def onboard(api):
    """A vague goal, then the purpose and the lesson times through two follow-up questions."""
    first = collect(api, "I need English")
    assert (first["status"], first["phase"]) == ("awaiting_confirmation", "follow_up_question")
    assert first["result"]["question"] == fake.PURPOSE_QUESTION
    second = answer(api, first, "I will study a Master's in Philosophy in the UK next year")
    assert second["id"] == first["id"] and second["result"]["question"] == fake.TIMES_QUESTION
    final = answer(api, second, "Tuesday and Thursday evenings, 18:00-20:00")
    assert final["id"] == first["id"] and final["status"] == "completed"
    assert final["result"]["question"] is None  # the merged result no longer carries the last question
    return final


# --- collect_goal (UC01 steps 1-3, 3a) -----------------------------------------------------------
def test_new_student_is_asked_for_purpose_and_times_then_confirms(client):
    api, student_id = new_student()
    final = onboard(api)
    summary = final["result"]["summary"]
    assert summary.startswith("Academic English") and len(summary) <= 90

    saved = confirm(api, summary)
    assert saved.status_code == 200, saved.content
    body = saved.json()
    assert body["phase"] == "initial_assessment_next"  # UC01 step 6: no confirmed level yet
    profile = body["result"]["profile"]
    assert (profile["goal_summary"], profile["weekly_hours"], profile["self_level"], profile["target_level"]) == (summary, 4, "B2", "C1")
    assert profile["availability"] == [{"day": "Tue", "start": "18:00", "end": "20:00"}, {"day": "Thu", "start": "18:00", "end": "20:00"}]
    assert learning.profile_for(learning.student(student_id)).learning_needs  # the intake draft was kept


def test_returning_student_with_lesson_times_gets_a_summary_straight_away(ivy):
    envelope = collect(ivy, "I want to study a Master's degree in Philosophy overseas and argue clearly in seminars.")
    assert envelope["status"] == "completed" and envelope["result"]["summary"].startswith("Academic English")
    saved = confirm(ivy, envelope["result"]["summary"], goal_text="Philosophy Master's overseas")
    assert saved.json()["phase"] == "profile_updated"  # Ivy already has a confirmed level
    ivy_profile = saved.json()["result"]["profile"]
    assert len(ivy_profile["availability"]) == 2  # the existing lesson times are kept (JSON fields merge)


def test_follow_ups_stop_after_two_questions():
    api, _ = new_student()
    first = collect(api, "help")
    second = answer(api, first, "dunno")
    response = api.post("/requests", {"type": "collect_goal", "context_id": second["id"], "input": {"answer": "not sure"}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "availability_required"  # never silently skip times


def test_llm_outage_keeps_the_students_own_words(monkeypatch):
    monkeypatch.setattr(registry, "build_runtime", lambda cls, task: make_runtime([]))  # every LLM call fails
    api, _ = new_student()
    envelope = collect(api, "I need English")
    assert envelope["result"]["question"] == fake.TIMES_QUESTION
    envelope = answer(api, envelope, "Tuesday 18:00-20:00")
    assert envelope["status"] == "completed" and envelope["result"]["summary"] == "I need English"


def test_model_cannot_skip_missing_availability(monkeypatch):
    from orchestration.coordinator import prompts

    reading = prompts.GoalReading(enough=True, summary="Academic English for school", availability=["Tue 18:00-20:00"])
    monkeypatch.setattr(registry, "build_runtime", lambda cls, task: make_runtime([reading.model_dump()]))
    api, _ = new_student()
    first = collect(api, "I need Academic English for my school exams next year")
    assert first["result"]["question"] == fake.TIMES_QUESTION
    final = answer(api, first, "Tuesday 18:00-20:00")
    assert final["status"] == "completed"
    assert confirm(api, final["result"]["summary"]).json()["result"]["profile"]["availability"] == [
        {"day": "Tue", "start": "18:00", "end": "20:00"}
    ]


# --- confirm_goal (UC01 steps 4-6) ---------------------------------------------------------------
def test_confirm_without_selected_skills_keeps_the_suggested_ones():
    api, _ = new_student()
    envelope = collect(api, "I want to pass the IELTS exam with 7.0 in March. I can take lessons on Tuesday 18:00-20:00.", skills=())
    assert envelope["result"]["summary"].startswith("Exam preparation") and envelope["result"]["focus_skills"]
    profile = confirm(api, envelope["result"]["summary"], focus_skills=[]).json()["result"]["profile"]
    assert profile["focus_skills"] == envelope["result"]["focus_skills"]



@pytest.mark.parametrize("overrides", [{"goal_summary": ""}, {"weekly_hours": 100}, {"self_level": "expert"}])
def test_confirm_rejects_an_invalid_profile(ivy, overrides):
    response = confirm(ivy, "Academic English for postgraduate study", **overrides)
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_goal"


# --- complete_material ---------------------------------------------------------------------------------
def test_completed_material_is_recorded_once(ivy):
    first = ivy.post("/requests", {"type": "complete_material", "input": {"material_id": key("M-02")}}).json()
    material = first["result"]["material"]
    assert (material["id"], material["title"], first["status"]) == (key("M-02"), "Evidence & Commentary", "completed")
    again = ivy.post("/requests", {"type": "complete_material", "input": {"material_id": key("M-02")}}).json()
    assert again["result"]["material"]["completed_at"] == material["completed_at"]
    assert LearningHistoryEntry.objects.filter(kind="material_completed", payload__material_id=key("M-02")).count() == 1
    records = ivy.get("/workspace").json()["students"][key("student-ivy")]["material_records"]
    assert key("M-02") in {r["material_id"] for r in records}


# --- onboarding loop: Coordinator -> Assessment Agent -> Course Consultant -> teacher ---------------
def test_onboarding_reaches_an_active_plan(emily):
    api, student_id = new_student("loop@example.com")
    summary = onboard(api)["result"]["summary"]
    assert confirm(api, summary).status_code == 200

    session = api.post("/assessments", {"student_id": student_id, "kind": "initial"}).json()
    while session["status"] == "in_progress":
        response = api.post(f"/assessments/{session['id']}/answers", {"item_id": session["current_item_id"], "answer": STEADY})
        assert response.status_code == 200, response.content
        session = response.json()
    assert session["result"]["status"] == "confirmed"

    # The summary names the domain, so the Consultant matches Emily (Academic English) without the Founder.
    review = EscalationCase.objects.get(student_id=student_id, subject_type="plan", status="open")
    assert str(review.assignee_id) == key("teacher-emily")
    decided = emily.post(f"/reviews/{review.pk}/decision", {"action": "approve", "note": "Good first plan."}).json()
    assert decided["follow_up"]["status"] == "completed", decided["follow_up"]["error"]

    student = learning.student(student_id)
    assert learning.active_plan(student) is not None
    lessons = list(learning.lessons_for_student(student))
    sydney = ZoneInfo("Australia/Sydney")  # the stated times are in the profile's default timezone
    assert lessons and all(lesson.starts_at.astimezone(sydney).strftime("%a %H:%M") in ("Tue 18:00", "Thu 18:00", "Tue 19:00", "Thu 19:00") for lesson in lessons)
