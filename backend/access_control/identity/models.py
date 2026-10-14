"""Identity (Fig 6a): Student, HumanTeacher and FounderOperator are one User table plus role groups."""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from domain.common import DomainModel


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)

    def __str__(self) -> str:
        return self.email


class TeacherProfile(DomainModel):
    """HumanTeacher attributes. Weekly availability lives in learning.AvailabilitySlot."""

    WRITERS = frozenset({"role:teacher", "role:founder"})
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
    subject_areas = models.JSONField(default=list)
    timezone = models.CharField(max_length=64, default="Australia/Sydney")
