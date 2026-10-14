"""Identity writes: registration, credential checks and role assignment (NFR-05)."""

from __future__ import annotations

import re

from django.contrib.auth.models import Group
from django.db import transaction

from domain.common import DomainError, Role
from domain.governance.services import record_audit
from domain.learning.services import create_profile

from .models import TeacherProfile, User

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


def find_by_email(email: str) -> User | None:
    return User.objects.filter(email__iexact=email.strip()).first()


def authenticate(email: str, password: str) -> User | None:
    user = find_by_email(email or "")
    if user is None or not user.is_active or not user.check_password(password or ""):
        return None
    return user


def create_user(*, name: str, email: str, password: str, role: str) -> User:
    if role not in Role.values:
        raise DomainError("invalid_role", f"Unknown role: {role}", status=400)
    user = User(username=email.lower(), email=email.lower(), name=name.strip())
    user.set_password(password)
    user.save()
    user.groups.add(Group.objects.get(name=role))
    if role == Role.TEACHER:
        TeacherProfile.objects.get_or_create(user=user)
    return user


def register_student(*, name: str, email: str, password: str) -> User:
    """Public registration always creates a Student (frontend /p02)."""
    if not name.strip() or not EMAIL.match(email or "") or len(password or "") < MIN_PASSWORD:
        raise DomainError("invalid_registration", "Enter a name, valid email and at least 8 characters.", status=400)
    if find_by_email(email):
        raise DomainError("email_taken", "Email already exists.")
    with transaction.atomic():
        user = create_user(name=name, email=email, password=password, role=Role.STUDENT)
        record_audit(user, "user.registered", user)
        create_profile(user, student=user)
    return user
