"""Saved assessment evidence is readable without changing grading or leaking rubrics."""
import pytest
from django.test import Client

from access_control.identity import services as identity
from domain.learning.models import ProficiencyProfile
from tests.conftest import Api, key

pytestmark = pytest.mark.django_db


@pytest.fixture
def saved_assessment():
    record = ProficiencyProfile.objects.get(pk=key("A-104"))
    session = record.session
    session.items = [
        {"item_id": "one", "prompt": "Explain the claim.\nUse evidence.",
         "answer": "My answer\nwith 中文 and <script>plain text</script>",
         "expected_points": ["PRIVATE RUBRIC"], "score": 0.4, "estimate": 2},
        {"item_id": "two", "prompt": "Compare the examples.", "answer": "Second answer"},
        {"item_id": "three", "prompt": "Unanswered item", "answer": None},
    ]
    session.save(update_fields=["items"])
    return record, session


def test_student_and_assigned_teacher_read_saved_evidence_by_both_ids(ivy, emily, saved_assessment):
    record, session = saved_assessment
    original = session.items
    for client in (ivy, emily):
        for pk in (record.pk, session.pk):
            result = client.get(f"/assessments/{pk}")
            assert result.status_code == 200
            data = result.json()
            assert data["responses"] == [
                {"number": 1, "prompt": original[0]["prompt"], "answer": original[0]["answer"]},
                {"number": 2, "prompt": original[1]["prompt"], "answer": "Second answer"},
            ]
            assert data["result"]["id"] == str(record.pk)
            assert "PRIVATE RUBRIC" not in result.content.decode()
    session.refresh_from_db()
    assert session.items == original  # viewing never rewrites answers


def test_history_denies_other_students_unassigned_teachers_and_founder(ivy, emily, alex, api, saved_assessment):
    record, _ = saved_assessment
    identity.create_user(name="Other", email="other-student@example.com", password="longenough", role="student")
    identity.create_user(name="Other", email="other-teacher@example.com", password="longenough", role="teacher")
    clients = [api, alex, Api(Client()).login("other-student@example.com", "longenough"),
               Api(Client()).login("other-teacher@example.com", "longenough")]
    for client in clients:
        response = client.get(f"/assessments/{record.pk}")
        assert response.status_code in (401, 403)
        assert "My answer" not in response.content.decode()


def test_old_records_without_items_return_empty_evidence(ivy, saved_assessment):
    record, session = saved_assessment
    session.items = []
    session.save(update_fields=["items"])
    response = ivy.get(f"/assessments/{record.pk}")
    assert response.status_code == 200
    assert response.json()["responses"] == []
    assert response.json()["result"]["id"] == str(record.pk)
