"""Small lookups shared by the routers: ids, users, ownership checks."""

from __future__ import annotations

import uuid
from typing import Any

from access_control.identity.models import User
from access_control.identity.permissions import Forbidden, assigned_student_ids, ensure_student_access
from domain.common import DomainError, Role


def parse_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def not_found(what: str = "Record") -> DomainError:
    return DomainError("not_found", f"{what} not found.", status=404)


def get_or_404(fetch, value: Any, what: str = "Record") -> Any:
    pk = parse_uuid(value)
    found = fetch(pk) if pk is not None else None
    if found is None:
        raise not_found(what)
    return found


def get_student(student_id: Any) -> User:
    pk = parse_uuid(student_id)
    student = User.objects.filter(pk=pk, groups__name=Role.STUDENT).first() if pk else None
    if student is None:
        raise not_found("Student")
    return student


def accessible_student(user: Any, student_id: Any) -> User:
    student = get_student(student_id)
    ensure_student_access(user, student)
    return student


def assigned_students(teacher: Any) -> list[User]:
    return list(User.objects.filter(pk__in=assigned_student_ids(teacher)).order_by("name"))


def require_owner(condition: bool, message: str = "You cannot access this record.") -> None:
    if not condition:
        raise Forbidden("forbidden", message)
