"""Shared domain conventions (spec 3.3).

* Every model inherits DomainModel: UUID primary key, timestamps, and a WRITERS set.
* Writes go through `services.py` functions whose first argument is the actor:
  an agent id ("assessment"), an internal component ("task_queue", "escalation_manager"),
  "system" (management commands only), or a logged-in User (matched as "role:<role>").
* `@writes(Model, "action")` checks the actor against Model.WRITERS and records an audit entry.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from typing import Any, ClassVar

from django.db import models, transaction


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    TEACHER = "teacher", "Teacher"
    FOUNDER = "founder", "Founder"


SYSTEM = "system"
AGENT_NAMES = {
    "coordinator": "Course Coordinator",
    "assessment": "Assessment Agent",
    "planning": "Course Consultant",
    "teaching_support": "Teaching Assistant",
    "tech_operations": "Technical Manager",
}
AGENT_IDS = frozenset(AGENT_NAMES)
COMPONENT_NAMES = {"task_queue": "Task Orchestrator", "escalation_manager": "Escalation Manager", SYSTEM: "System"}


class DomainModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    WRITERS: ClassVar[frozenset[str]] = frozenset()

    class Meta:
        abstract = True


class DomainError(Exception):
    """Expected business rule violation. The gateway maps it to an HTTP error (default 409)."""

    def __init__(self, code: str, message: str, *, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class WriterNotAllowed(DomainError):
    def __init__(self, actor_label: str, model: type[models.Model]):
        super().__init__("writer_not_allowed", f"{actor_label} may not write {model.__name__}", status=403)


def role_of(user: Any) -> str | None:
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    cached = getattr(user, "_role_cache", None)
    if cached is None:
        names = set(user.groups.values_list("name", flat=True))
        cached = next((r.value for r in Role if r.value in names), "")
        user._role_cache = cached
    return cached or None


def actor_label(actor: Any) -> str:
    if isinstance(actor, str):
        return actor
    role = role_of(actor)
    return f"role:{role}" if role else "role:unknown"


def check_writer(actor: Any, model: type[DomainModel]) -> None:
    label = actor_label(actor)
    if label == SYSTEM:
        return
    if label not in model.WRITERS:
        raise WriterNotAllowed(label, model)


# --- audit context ------------------------------------------------------------
_trace: ContextVar[dict] = ContextVar("lingopath_trace", default={})


@contextmanager
def trace_context(**values: Any) -> Iterator[None]:
    """Attach request_id / task_id to every audit record written inside the block."""
    token = _trace.set({**_trace.get(), **{k: v for k, v in values.items() if v is not None}})
    try:
        yield
    finally:
        _trace.reset(token)


def current_trace() -> dict:
    return _trace.get()


@contextmanager
def audit_suppressed() -> Iterator[None]:
    """Only for seeding demo data: loading fixtures is not a business action."""
    with trace_context(audit_suppressed=True):
        yield


def writes(model: type[DomainModel], action: str) -> Callable:
    """Decorator for service functions: writer check, atomic transaction, automatic audit."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(actor: Any, *args: Any, **kwargs: Any) -> Any:
            check_writer(actor, model)
            from domain.governance.services import record_audit  # late import: governance builds on this module

            with transaction.atomic():
                result = fn(actor, *args, **kwargs)
                target = result if isinstance(result, models.Model) else None
                record_audit(actor, action, target)
            return result

        wrapper.writes_model = model  # type: ignore[attr-defined]
        return wrapper

    return decorator


def save_fields(actor: Any, obj: models.Model, action: str, fields: dict[str, Any], detail: dict | None = None) -> Any:
    """Update an existing row: writer check, atomic save, audit (the update-side twin of @writes)."""
    check_writer(actor, type(obj))
    from domain.governance.services import record_audit

    for name, value in fields.items():
        setattr(obj, name, value)
    with transaction.atomic():
        obj.save()
        record_audit(actor, action, obj, detail=detail)
    return obj


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def ref(model_or_none: Any) -> str | None:
    return str(model_or_none.pk) if model_or_none is not None else None
