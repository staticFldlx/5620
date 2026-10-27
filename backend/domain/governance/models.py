"""GovernanceDomain (Fig 6c): tasks, escalations, audit, incidents, proposals.

Goal / Intention / Belief / PlatformEnvironment are conceptual (spec 3.2):
Goal = AgentTask.task_type + payload; Intention = a running AgentTask and its trace;
Belief = confidence-bearing domain state (e.g. ProficiencyProfile); PlatformEnvironment = this app.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from domain.common import DomainModel

User = settings.AUTH_USER_MODEL


class ServiceRequest(DomainModel):
    """SM1 Student Service Request. Backs the frontend request envelope (GET /requests/{id})."""

    WRITERS = frozenset({"task_queue"})

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        AWAITING_INPUT = "awaiting_input"
        ESCALATED = "escalated"
        AWAITING_APPROVAL = "awaiting_approval"
        COMPLETED = "completed"
        FAILED = "failed"

    type = models.CharField(max_length=64)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="service_requests")
    actor_role = models.CharField(max_length=16)  # student | teacher | founder | system
    student = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="student_requests")
    context_id = models.CharField(max_length=64, blank=True)
    input = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    phase = models.CharField(max_length=64, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.JSONField(null=True, blank=True)  # {code, message}
    remaining_steps = models.JSONField(default=list, blank=True)  # task types still to run
    hops = models.PositiveIntegerField(default=0)
    replans = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]


class AgentTask(DomainModel):
    WRITERS = frozenset({"task_queue"})

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        SUCCEEDED = "succeeded"
        NEEDS_INPUT = "needs_input"
        ESCALATED = "escalated"
        AWAITING_APPROVAL = "awaiting_approval"
        FAILED = "failed"

    request = models.ForeignKey(ServiceRequest, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    conversation = models.ForeignKey("learning.Conversation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    task_type = models.CharField(max_length=96)
    target_agent = models.CharField(max_length=32)
    student = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    result = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    reason = models.CharField(max_length=64, blank=True)
    hops = models.PositiveIntegerField(default=0)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    trace = models.JSONField(default=list, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["target_agent", "created_at"]),
        ]


class EscalationCase(DomainModel):
    WRITERS = frozenset({"escalation_manager"})

    class Kind(models.TextChoices):
        REVIEW = "review"  # human checks afterwards (Fig 8a)
        APPROVAL = "approval"  # human decides first (Fig 8b)

    class Status(models.TextChoices):
        OPEN = "open"
        RESOLVED = "resolved"
        CLOSED = "closed"

    class Subject(models.TextChoices):
        ASSESSMENT = "assessment"
        PLAN = "plan"
        QUESTION = "question"
        BUSINESS = "business"
        PROPOSAL = "proposal"

    task = models.ForeignKey(AgentTask, null=True, blank=True, on_delete=models.SET_NULL, related_name="escalations")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    trigger = models.TextField()
    confidence = models.FloatField(null=True, blank=True)
    outcome = models.CharField(max_length=64, blank=True)
    assignee = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_cases")
    decision = models.JSONField(null=True, blank=True)  # {action, note, ...}
    resume_task_type = models.CharField(max_length=96, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    student = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="escalations_about")
    subject_type = models.CharField(max_length=16, choices=Subject.choices)
    subject_id = models.CharField(max_length=64, blank=True)
    summary = models.CharField(max_length=200, blank=True)  # business cases: short subject line
    diagnosis = models.TextField(blank=True)
    evidence = models.JSONField(default=list, blank=True)  # [{ref, summary}]

    class Meta:
        ordering = ["-created_at"]


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("AuditLog is append-only")

    def delete(self):
        raise PermissionError("AuditLog is append-only")


class AuditLog(models.Model):
    """NFR-07. Append-only: existing rows can never be changed or deleted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.CharField(max_length=64)  # agent/component id or user id
    actor_role = models.CharField(max_length=32)  # agent | component | student | teacher | founder
    actor_name = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=96)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    task_id = models.CharField(max_length=64, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    model = models.CharField(max_length=96, blank=True)
    tokens = models.JSONField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("AuditLog is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("AuditLog is append-only")


class IncidentRecord(DomainModel):
    WRITERS = frozenset({"tech_operations"})

    class Risk(models.TextChoices):
        SAFE = "safe"
        LOW_RISK = "lowRisk"
        REVERSIBLE = "reversible"
        CRITICAL = "critical"
        UNKNOWN = "unknown"

    severity = models.CharField(max_length=16, default="medium")
    status = models.CharField(max_length=32, default="detected")  # SM5 values, owned by tech_operations
    affected_components = models.JSONField(default=list, blank=True)
    diagnosis = models.TextField(blank=True)
    risk = models.CharField(max_length=16, choices=Risk.choices, default=Risk.UNKNOWN)
    recovery_action = models.CharField(max_length=96, blank=True)
    subject = models.CharField(max_length=200)
    trigger = models.TextField(blank=True)
    evidence = models.JSONField(default=list, blank=True)  # [{ref, summary}]
    verification = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class UpdateProposal(DomainModel):
    # tech_operations drafts and executes; the approval outcome is written by the EscalationManager.
    WRITERS = frozenset({"tech_operations", "escalation_manager"})
    change_type = models.CharField(max_length=32)  # corpus | recovery | configuration | permission | archive | prompt
    title = models.CharField(max_length=200)
    rationale = models.TextField(blank=True)
    status = models.CharField(max_length=32, default="pending")  # pending | approved | rejected
    payload = models.JSONField(default=dict, blank=True)
    evidence_refs = models.JSONField(default=list, blank=True)
    incident = models.ForeignKey(IncidentRecord, null=True, blank=True, on_delete=models.SET_NULL, related_name="proposals")
    before = models.TextField(blank=True)
    after = models.TextField(blank=True)
    validation = models.TextField(blank=True)
    rollback = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)  # approval is bound to the reviewed version
    decided_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    execution_status = models.CharField(max_length=32, default="not_started")
    verification = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        ordering = ["created_at"]


class Notification(DomainModel):
    WRITERS = frozenset({"escalation_manager"})
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=32)
    ref = models.CharField(max_length=64)
    read_at = models.DateTimeField(null=True, blank=True)


class AgentState(DomainModel):
    """Operational switch per agent (UC09 5a pause)."""

    WRITERS = frozenset({"role:founder", "tech_operations"})
    agent_id = models.CharField(max_length=32, unique=True)
    status = models.CharField(max_length=16, default="healthy")  # healthy | degraded | paused
    note = models.TextField(blank=True)

class AgentRuntimeOverride(models.Model):
    """Persistent, agent-specific runtime configuration."""

    agent_id = models.CharField(
        max_length=100,
        unique=True,
    )

    timeout_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "governance_agent_runtime_override"

    def __str__(self):
        return f"{self.agent_id}: {self.timeout_seconds}"


class RecoveryAttempt(DomainModel):
    """At most one controlled retry per failed task, including concurrent monitor runs."""
    WRITERS = frozenset({"task_queue"})
    incident = models.ForeignKey(IncidentRecord, on_delete=models.PROTECT, related_name="recovery_attempts")
    source_task = models.OneToOneField(AgentTask, on_delete=models.PROTECT, related_name="recovery_attempt")
    retry_task = models.OneToOneField(AgentTask, null=True, on_delete=models.PROTECT, related_name="recovery_execution")
