"""Workspace envelopes and detail payloads, composed from the domain read models (A8).

Shapes follow frontend/src/api/types.ts. Lists are bounded by WORKSPACE_LIST_LIMIT.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from domain.common import role_of
from domain.governance import selectors as governance
from domain.governance import views as gviews
from domain.governance.models import EscalationCase
from domain.learning import selectors as learning
from domain.learning import views as lviews
from infrastructure import retrieval
from orchestration.task_queue import registry

from . import lookups


def limit() -> int:
    return settings.WORKSPACE_LIST_LIMIT


def user_record(user: Any) -> dict:
    return {"id": str(user.pk), "name": user.name, "email": user.email, "role": (role_of(user) or "").title()}


def _plan_review_id(plan: Any) -> str:
    case = governance.latest_case_for(EscalationCase.Subject.PLAN, plan.pk)
    return str(case.pk) if case else ""


def plan_record(plan: Any) -> dict | None:
    return lviews.plan_view(plan, review_id=_plan_review_id(plan)) if plan else None


def student_record(student: Any) -> dict:
    observation = learning.latest_observation(student)
    return {
        "name": student.name,
        "profile": lviews.profile_view(learning.profile_for(student)),
        "assessments": [lviews.proficiency_view(p) for p in learning.proficiency_records(student)][-limit():],
        "plan": plan_record(learning.active_plan(student)),
        "pending_plan": plan_record(learning.pending_plan(student)),
        "material_records": [lviews.material_completion_view(e) for e in learning.history(student, kinds=("material_completed",))][-limit():],
        "observation": observation.text if observation else "",
    }


def interactions(student: Any) -> list[dict]:
    entries = list(learning.history(student, kinds=learning.INTERACTION_KINDS).order_by("-created_at")[: limit()])[::-1]
    cases = governance.cases_for_subjects(EscalationCase.Subject.QUESTION, [str(e.pk) for e in entries])
    return [lviews.interaction_view(e, case=cases.get(str(e.pk))) for e in entries]


def student_workspace(user: Any) -> dict:
    lessons = list(learning.lessons_for_student(user)[: limit()])
    return {
        "user": user_record(user),
        "students": {str(user.pk): student_record(user)},
        "lessons": [lviews.lesson_view(lesson) for lesson in lessons],
        "materials": [lviews.material_view(m) for m in learning.materials_for_lessons(lessons, approved_only=True)],
        "interactions": interactions(user),
        "assessment_sessions": [assessment_record(s) for s in learning.ongoing_assessments(user)[:limit()]],
    }


def teacher_workspace(user: Any, student: Any = None) -> dict:
    students = [student] if student is not None else lookups.assigned_students(user)
    lessons = list(learning.lessons_for_teacher(user)[: limit()])
    return {
        "user": user_record(user),
        "students": {str(s.pk): student_record(s) for s in students[: limit()]},
        "lessons": [lviews.lesson_view(lesson) for lesson in lessons],
        "materials": [lviews.material_view(m) for m in learning.materials_for_lessons(lessons)],
        "reviews": [gviews.review_view(c) for c in governance.cases_assigned_to(user, limit=limit())],
        "teacher_availability": [lviews.availability_view(s) for s in learning.teacher_windows(user)],
    }


def services() -> list[dict]:
    if settings.LLM_PROVIDER == "fake":
        llm = "offline_demo"
    else:
        llm = "configured" if settings.LLM_BASE_URL else "not_configured"
    return [
        {"name": "Application service", "status": "healthy", "last_backup_at": None},
        {"name": "LLM provider", "status": llm, "last_backup_at": None},
        {"name": "Retrieval index", "status": "healthy" if retrieval.is_enabled() else "disabled", "last_backup_at": None},
        {"name": "Learning records", "status": "healthy", "last_backup_at": None},
    ]


def operations() -> dict:
    """Founder view: operational summaries only, no student chat, answers, goals or lesson notes."""
    states = governance.agent_states()
    cases = [gviews.business_case_view(c) for c in governance.business_cases(limit())]
    cases += [gviews.incident_case_view(i) for i in governance.incidents(limit())]
    return {
        "agents": [
            gviews.agent_view(agent_id, state=states.get(agent_id), latest=governance.latest_task_for_agent(agent_id), implemented=registry.is_implemented(agent_id))
            for agent_id in settings.AGENT_REGISTRY
        ],
        "services": services(),
        "logs": [gviews.log_view(t) for t in governance.recent_tasks(limit())],
        "warnings": [gviews.warning_view(t) for t in governance.recent_failed_tasks(10)],
        "cases": cases,
        "proposals": [gviews.proposal_view(p) for p in governance.proposals(limit())],
        "audit": [gviews.audit_view(a) for a in governance.recent_audit(limit())],
    }


def founder_workspace(user: Any) -> dict:
    return {"user": user_record(user), "operations": operations()}


def review_subject(case: EscalationCase) -> dict | None:
    subject_id = lookups.parse_uuid(case.subject_id)
    if subject_id is None:
        return None
    if case.subject_type == EscalationCase.Subject.PLAN:
        plan = learning.plan(subject_id)
        return lviews.plan_view(plan, review_id=str(case.pk)) if plan else None
    if case.subject_type == EscalationCase.Subject.ASSESSMENT:
        record = learning.proficiency(subject_id)
        return lviews.proficiency_view(record) if record else None
    if case.subject_type == EscalationCase.Subject.QUESTION:
        entry = learning.history_entry(subject_id)
        return lviews.interaction_view(entry, case=case) if entry else None
    return None


def review_detail(case: EscalationCase) -> dict:
    # Only the assigned reviewer reaches this presenter. Never add drafts to interaction_view,
    # which also supplies student workspaces and must retain the holding reply.
    detail = {"review": gviews.review_view(case), "subject": review_subject(case), "evidence": case.trigger}
    if case.subject_type == EscalationCase.Subject.QUESTION:
        entry = learning.history_entry(lookups.parse_uuid(case.subject_id))
        payload = entry.payload if entry else {}
        detail.update(draft_answer=(payload or {}).get("draft_answer"),
                      draft_source_refs=(payload or {}).get("draft_source_refs", []))
    return detail


def assessment_record(session) -> dict:
    related = governance.request_for_assessment(session.pk)
    return {**lviews.session_view(session), "follow_up": gviews.request_envelope(related) if related else None}
