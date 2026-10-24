"""RBAC (NFR-05): role checks and the single object-level rule `can_access_student`.

Permission checks happen here, at the API layer, before any agent is reached (Fig 4).
Agents do not repeat them.
"""

from __future__ import annotations

from typing import Any

from domain.common import DomainError, Role, role_of
from domain.governance import selectors as governance
from domain.governance.services import record_audit
from domain.learning import selectors as learning


class Forbidden(DomainError):
    def __init__(self, code: str = "forbidden", message: str = "You cannot access this record."):
        super().__init__(code, message, status=403)


def require_role(user: Any, *roles: str) -> str:
    role = role_of(user)
    if role not in roles:
        raise Forbidden("forbidden_role", f"This action requires the {' or '.join(roles)} role.")
    return role


def assigned_student_ids(teacher: Any) -> set[Any]:
    """Students a teacher may see: teacher of their active or pending plan, assignee of an open review (A10),
    or the teacher of a plan draft that only waits for the student to pick a lesson time."""
    return (
        learning.students_with_plan_teacher(teacher)
        | governance.students_with_open_cases(teacher)
        | governance.students_awaiting_plan_choice(teacher)
    )


def can_access_student(user: Any, student: Any) -> bool:
    role = role_of(user)
    if role == Role.STUDENT:
        return student.pk == user.pk
    if role == Role.TEACHER:
        return student.pk in assigned_student_ids(user)
    return role == Role.FOUNDER


def ensure_student_access(user: Any, student: Any) -> None:
    """Deny with 403 and log the attempt (UC06 2a)."""
    if not can_access_student(user, student):
        record_audit(user, "access.denied", student, detail={"reason": "not_assigned"})
        raise Forbidden("forbidden_student_access", "You are not assigned to this student.")
