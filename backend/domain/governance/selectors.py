"""GovernanceDomain read-only queries, including the shared monitoring metrics (spec 3.4).

tech_operations may only use the operational queries in the "monitoring" section: they expose
task status, duration, reason codes and escalation rates, never payloads or student content.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, F, Q, QuerySet
from django.utils import timezone

from .models import AgentState, AgentTask, AuditLog, EscalationCase, IncidentRecord, ServiceRequest, UpdateProposal

LEARNING_SUBJECTS = ("assessment", "plan", "question")


# --- requests and tasks -----------------------------------------------------------
def service_request(pk: Any) -> ServiceRequest | None:
    return ServiceRequest.objects.select_related("actor", "student").filter(pk=pk).first()


def tasks_for(request: ServiceRequest) -> QuerySet[AgentTask]:
    return request.tasks.order_by("created_at")


def task(pk: Any) -> AgentTask | None:
    return AgentTask.objects.filter(pk=pk).select_related("request").first()


def next_queued_task(request: ServiceRequest | None = None) -> AgentTask | None:
    qs = AgentTask.objects.filter(status=AgentTask.Status.QUEUED)
    if request is not None:
        qs = qs.filter(request=request)
    return qs.order_by("created_at").first()


def awaiting_task(request: ServiceRequest) -> AgentTask | None:
    return request.tasks.filter(status=AgentTask.Status.NEEDS_INPUT).order_by("-created_at").first()


def request_awaiting_session(session_id: str) -> ServiceRequest | None:
    """The assessment request currently waiting for an answer on this session (A14)."""
    waiting = (
        AgentTask.objects.filter(status=AgentTask.Status.NEEDS_INPUT, result__result__session_id=str(session_id))
        .select_related("request")
        .order_by("-created_at")
        .first()
    )
    if waiting and waiting.request and waiting.request.status == ServiceRequest.Status.AWAITING_INPUT:
        return waiting.request
    return None


def latest_task_for_agent(agent_id: str) -> AgentTask | None:
    return AgentTask.objects.filter(target_agent=agent_id).order_by("-created_at").first()


def recent_tasks(limit: int = 50) -> QuerySet[AgentTask]:
    return AgentTask.objects.exclude(status=AgentTask.Status.QUEUED).order_by("-created_at")[:limit]


def recent_failed_tasks(limit: int = 20) -> QuerySet[AgentTask]:
    return AgentTask.objects.filter(status=AgentTask.Status.FAILED).order_by("-created_at")[:limit]


# --- monitoring metrics (shared by UC09 and UC10) ---------------------------------------
def agent_stats(window: timedelta = timedelta(days=7)) -> dict[str, dict]:
    """Per agent: tasks, failure rate, mean duration, escalation rate, low-confidence share."""
    from django.conf import settings

    since = timezone.now() - window
    rows = (
        AgentTask.objects.filter(created_at__gte=since)
        .values("target_agent")
        .annotate(
            tasks=Count("id"),
            failed=Count("id", filter=Q(status=AgentTask.Status.FAILED)),
            escalated=Count("id", filter=Q(status__in=[AgentTask.Status.ESCALATED, AgentTask.Status.AWAITING_APPROVAL])),
            low_confidence=Count("id", filter=Q(confidence__lt=settings.AGENT_CONFIDENCE_THRESHOLD)),
            avg_duration=Avg(F("finished_at") - F("started_at")),
        )
    )
    stats = {}
    for row in rows:
        total = row["tasks"] or 1
        duration = row["avg_duration"]
        stats[row["target_agent"]] = {
            "tasks": row["tasks"],
            "failure_rate": round(row["failed"] / total, 3),
            "escalation_rate": round(row["escalated"] / total, 3),
            "low_confidence_rate": round(row["low_confidence"] / total, 3),
            "avg_duration_ms": int(duration.total_seconds() * 1000) if duration else None,
        }
    return stats


def stuck_tasks(now=None) -> QuerySet[AgentTask]:
    """Running tasks past their deadline (spec 8.5)."""
    return AgentTask.objects.filter(status=AgentTask.Status.RUNNING, deadline_at__lt=now or timezone.now())


def operational_tasks(limit: int = 50) -> QuerySet:
    """Payload-free task rows for the Technical Manager (spec 3.4)."""
    return recent_tasks(limit).values("id", "target_agent", "task_type", "status", "reason", "confidence", "started_at", "finished_at")


# --- escalations ---------------------------------------------------------------------------
def case(pk: Any) -> EscalationCase | None:
    return EscalationCase.objects.select_related("assignee", "student", "resolved_by", "task").filter(pk=pk).first()


def cases_assigned_to(user: Any, *, subjects: tuple[str, ...] = LEARNING_SUBJECTS, limit: int = 50) -> QuerySet[EscalationCase]:
    return EscalationCase.objects.filter(assignee=user, subject_type__in=subjects).order_by("-created_at")[:limit]


def students_with_open_cases(user: Any) -> set[Any]:
    return set(
        EscalationCase.objects.filter(assignee=user, status=EscalationCase.Status.OPEN, student__isnull=False).values_list("student_id", flat=True)
    )


def latest_case_for(subject_type: str, subject_id: Any) -> EscalationCase | None:
    return (
        EscalationCase.objects.filter(subject_type=subject_type, subject_id=str(subject_id))
        .select_related("resolved_by")
        .order_by("-created_at")
        .first()
    )


def cases_for_subjects(subject_type: str, subject_ids: list[str]) -> dict[str, EscalationCase]:
    """Latest case per subject id (one query for a list of records)."""
    found: dict[str, EscalationCase] = {}
    for item in EscalationCase.objects.filter(subject_type=subject_type, subject_id__in=subject_ids).select_related("resolved_by").order_by("created_at"):
        found[item.subject_id] = item
    return found


def business_cases(limit: int = 50) -> QuerySet[EscalationCase]:
    return EscalationCase.objects.filter(subject_type=EscalationCase.Subject.BUSINESS).order_by("-created_at")[:limit]


def open_approval_case_for(subject_type: str, subject_id: Any) -> EscalationCase | None:
    return EscalationCase.objects.filter(subject_type=subject_type, subject_id=str(subject_id), status=EscalationCase.Status.OPEN).first()


def teacher_by_email(email: str) -> Any | None:
    if not email:
        return None
    return get_user_model().objects.filter(email__iexact=email, groups__name="teacher", is_active=True).first()


def first_founder() -> Any | None:
    return get_user_model().objects.filter(groups__name="founder", is_active=True).order_by("date_joined").first()


# --- incidents, proposals, agents, audit ---------------------------------------------------
def incident(pk: Any) -> IncidentRecord | None:
    return IncidentRecord.objects.filter(pk=pk).first()


def incidents(limit: int = 50) -> QuerySet[IncidentRecord]:
    return IncidentRecord.objects.prefetch_related("proposals").order_by("-created_at")[:limit]


def proposal(pk: Any) -> UpdateProposal | None:
    return UpdateProposal.objects.filter(pk=pk).select_related("incident", "decided_by").first()


def proposals(limit: int = 50) -> QuerySet[UpdateProposal]:
    return UpdateProposal.objects.select_related("incident", "decided_by").order_by("created_at")[:limit]


def agent_states() -> dict[str, AgentState]:
    return {state.agent_id: state for state in AgentState.objects.all()}


def agent_state(agent_id: str) -> AgentState | None:
    return AgentState.objects.filter(agent_id=agent_id).first()


def recent_audit(limit: int = 50, *, include_task_events: bool = False) -> QuerySet[AuditLog]:
    qs = AuditLog.objects.all()
    if not include_task_events:
        qs = qs.exclude(action__startswith="task.").exclude(action__startswith="request.").exclude(action__startswith="notification.")
    return qs.order_by("-created_at")[:limit]
