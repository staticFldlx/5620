"""API regressions for frontend issues 1, 2, 4, 7, 8, 9 and 11; isolated test DB."""
import pytest
from django.test import Client
from access_control.identity import services as identity
from domain.governance.models import ServiceRequest
from domain.learning.models import AssessmentSession, LearningHistoryEntry
from orchestration.task_queue import dispatcher
from tests.conftest import Api, key

pytestmark = pytest.mark.django_db

@pytest.mark.parametrize('mode', ['inline', 'worker'])
def test_directed_assessment_discovered_owned_resumable_and_current(ivy, emily, settings, mode):
    settings.AGENT_TASK_EXECUTION = mode
    response = emily.post('/assessments', {'student_id':key('student-ivy'), 'kind':'directed', 'focus':'Evidence linking'})
    assert response.status_code == (202 if mode == 'worker' else 200), response.content
    if mode == 'worker':
        request = ServiceRequest.objects.get(pk=response.json()['id']); dispatcher.drain(request)
    saved = ivy.get('/workspace').json()['assessment_sessions']
    session = next(s for s in saved if s['focus'] == 'Evidence linking')
    assert session['kind'] == 'directed' and session['current_item_id']
    other = Api(Client()).login('sophia.chen@example.com')
    assert session['id'] not in [s['id'] for s in other.get('/workspace').json()['assessment_sessions']]
    assert other.get(f"/assessments/{session['id']}").status_code == 403
    again = Api(Client()).login('ivy.lin@example.com')
    response = again.post(f"/assessments/{session['id']}/answers", {'item_id':session['current_item_id'], 'answer':' '.join(['evidence'] * 16)})
    assert response.status_code == (202 if mode == 'worker' else 200), response.content
    if mode == 'worker':
        # Must return a queued request, not the old unanswered item as a 200 session.
        assert response.json()['status'] == 'queued'
        request = ServiceRequest.objects.get(pk=response.json()['id']); dispatcher.drain(request)
    updated = again.get(f"/assessments/{session['id']}").json()
    assert updated['answered'] == 1
    assert updated['current_item_id'] != session['current_item_id']
    retry = again.post(f"/assessments/{session['id']}/answers", {'item_id':session['current_item_id'], 'answer':'duplicate'})
    assert retry.json()['answered'] == 1


def test_completed_assessment_survives_downstream_failure(ivy):
    response = ivy.post('/assessments', {'student_id':key('student-ivy'), 'kind':'milestone'})
    assert response.status_code == 200
    session = AssessmentSession.objects.get(pk=response.json()['id'])
    request = ServiceRequest.objects.get(pk=response.json()['follow_up']['id'])
    session.status = 'completed'; session.save()
    request.status='failed'; request.error={'code':'plan_update_failed','message':'Plan cannot be created yet.'}; request.save()
    from access_control.gateway.routers.assessments import _session_response
    result = _session_response(request)
    assert result.status_code == 200
    assert result.value['status'] == 'completed'
    assert result.value['follow_up']['error']['code'] == 'plan_update_failed'
    assert ivy.get(f'/assessments/{session.pk}').json()['follow_up']['status'] == 'failed'


def test_draft_is_available_only_in_assigned_review_not_student_payload(ivy, emily, alex):
    entry = LearningHistoryEntry.objects.get(pk=key('RQ-09'))
    entry.payload = {**entry.payload, 'draft_answer':'Private draft before teacher approval.', 'draft_source_refs':[{'material_id':'M-01','title':'Writing guide','locator':'Section 1'}]}
    entry = LearningHistoryEntry.objects.create(student=entry.student, kind=entry.kind, payload=entry.payload, escalated=True, confidence=0.5)
    from domain.governance.models import EscalationCase
    EscalationCase.objects.filter(pk=key('RV-Q09')).update(subject_id=str(entry.pk))
    detail = emily.get(f"/reviews/{key('RV-Q09')}")
    assert detail.status_code == 200
    assert detail.json()['draft_answer'] == entry.payload['draft_answer']
    assert detail.json()['draft_source_refs'][0]['title'] == 'Writing guide'
    assert 'draft_answer' not in detail.json()['subject']
    assert 'Private draft' not in ivy.get('/workspace').content.decode()
    assert ivy.get(f"/reviews/{key('RV-Q09')}").status_code == 403
    assert alex.get(f"/reviews/{key('RV-Q09')}").status_code == 403
    identity.create_user(name='Other Teacher', email='other-teacher@example.com', password='learning123', role='teacher')
    other = Api(Client()).login('other-teacher@example.com','learning123')
    assert other.get(f"/reviews/{key('RV-Q09')}").status_code == 403


def test_material_completion_contract_is_an_object_array(ivy):
    rows = ivy.get('/workspace').json()['students'][key('student-ivy')]['material_records']
    assert rows and set(rows[0]) == {'material_id','completed_at'}
