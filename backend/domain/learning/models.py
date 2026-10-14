"""LearningDomain (Fig 6b) plus the supplementary fields listed in docs/shared-conventions.md.

`status` values are owned by the writing agent's state machine (SM2 assessment, SM3 plan,
SM4 lesson); the shared layer only guarantees the field exists. Values already used by the
frontend are listed in the conventions document.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from domain.common import DomainModel

User = settings.AUTH_USER_MODEL


class LearningProfile(DomainModel):
    WRITERS = frozenset({"coordinator", "role:student"})
    student = models.OneToOneField(User, on_delete=models.CASCADE, related_name="learning_profile")
    learning_goal = models.TextField(blank=True)  # goal_text
    english_level = models.CharField(max_length=16, blank=True)  # self-reported level (self_level)
    structured_objective = models.JSONField(default=dict, blank=True)  # {summary, focus_skills[], target_level}
    preferences = models.JSONField(default=dict, blank=True)  # {weekly_hours, timezone, availability[]}
    learning_needs = models.TextField(blank=True)


class AssessmentSession(DomainModel):
    WRITERS = frozenset({"assessment"})

    class Type(models.TextChoices):
        INITIAL = "initial"
        MILESTONE = "milestone"
        DIRECTED = "directed"

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assessment_sessions")
    type = models.CharField(max_length=16, choices=Type.choices)
    difficulty = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=32, default="in_progress")  # SM2; frontend shows next item only for "in_progress"
    items = models.JSONField(default=list, blank=True)  # [{item_id, prompt, answer|null, ...}]
    requested_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    focus = models.CharField(max_length=200, blank=True)
    max_items = models.PositiveSmallIntegerField(default=3)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]


class ProficiencyProfile(DomainModel):
    WRITERS = frozenset({"assessment"})
    session = models.OneToOneField(AssessmentSession, on_delete=models.CASCADE, related_name="proficiency")
    overall_level = models.CharField(max_length=16)
    strengths = models.JSONField(default=list, blank=True)
    weak_areas = models.JSONField(default=list, blank=True)
    gap_to_goal = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=32, default="pending_review")  # pending_review | confirmed | changes_requested
    feedback = models.TextField(blank=True)
    review_note = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def is_low_confidence(self, threshold: float) -> bool:
        return self.confidence is not None and self.confidence < threshold


class LearningMaterial(DomainModel):
    """Shared teaching-material corpus (design assumption 1)."""

    WRITERS = frozenset({"tech_operations"})
    title = models.CharField(max_length=200)
    type = models.CharField(max_length=32, blank=True)  # reading | listening | vocabulary | exercise ...
    source = models.CharField(max_length=200, blank=True)
    difficulty_level = models.CharField(max_length=16, blank=True)
    file = models.FileField(upload_to="materials/", blank=True)
    source_type = models.CharField(max_length=16, default="internal")  # internal | open
    license = models.CharField(max_length=100, blank=True)
    url = models.URLField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    stage_topics = models.JSONField(default=list, blank=True)


class Course(DomainModel):
    WRITERS = frozenset({"tech_operations", "role:founder"})
    code = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=200)
    skill = models.CharField(max_length=64, blank=True)
    level = models.CharField(max_length=16, blank=True)
    prerequisites = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="unlocks")
    materials = models.ManyToManyField(LearningMaterial, blank=True, related_name="courses")


class LearningPlan(DomainModel):
    WRITERS = frozenset({"planning"})
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="learning_plans")
    teacher = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="taught_plans")
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=32, default="pending_review")  # SM3: pending_review | active | changes_requested | superseded | completed
    weekly_hours = models.FloatField(default=0)
    based_on = models.ForeignKey(ProficiencyProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    previous_version = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="next_versions")
    rationale = models.TextField()  # NFR-04: every version records why
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    stage_index = models.PositiveSmallIntegerField(default=0)  # 0-based index of the current stage

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["student"], condition=Q(status="active"), name="one_active_plan_per_student"),
        ]


class PlanStage(DomainModel):
    WRITERS = frozenset({"planning"})
    plan = models.ForeignKey(LearningPlan, on_delete=models.CASCADE, related_name="stages")
    stage_number = models.PositiveSmallIntegerField()  # 1-based
    title = models.CharField(max_length=200)
    topics = models.JSONField(default=list, blank=True)
    milestone = models.TextField(blank=True)
    status = models.CharField(max_length=32, default="upcoming")  # upcoming | current | completed
    start_week = models.PositiveSmallIntegerField(default=1)
    end_week = models.PositiveSmallIntegerField(default=1)
    courses = models.ManyToManyField(Course, blank=True, related_name="stages")
    materials = models.ManyToManyField(LearningMaterial, blank=True, related_name="stages")

    class Meta:
        ordering = ["stage_number"]
        constraints = [models.UniqueConstraint(fields=["plan", "stage_number"], name="unique_stage_number")]


class AvailabilitySlot(DomainModel):
    """Weekly recurring teaching window (deviation from spec: no 1:1 link to Lesson)."""

    WRITERS = frozenset({"role:teacher"})
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="availability_slots")
    day = models.CharField(max_length=3)  # Mon..Sun
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["created_at"]


class Lesson(DomainModel):
    # planning books and moves lessons; the teacher records attendance afterwards (SM4).
    WRITERS = frozenset({"planning", "role:teacher"})
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="lessons")
    teacher = models.ForeignKey(User, on_delete=models.PROTECT, related_name="taught_lessons")
    stage = models.ForeignKey(PlanStage, null=True, blank=True, on_delete=models.SET_NULL, related_name="lessons")
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=32, default="proposed")  # SM4: proposed | confirmed | completed | rescheduling_required | cancelled
    classroom_url = models.URLField(null=True, blank=True)
    attendance = models.CharField(max_length=32, default="not_recorded")  # not_recorded | attended | absent

    class Meta:
        ordering = ["starts_at"]


class LessonMaterial(DomainModel):
    """Material saved to a lesson (UC08 step 5). This is the frontend `Material` record."""

    WRITERS = frozenset({"teaching_support", "role:teacher"})
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="lesson_materials")
    title = models.CharField(max_length=200)
    locator = models.CharField(max_length=200, blank=True)
    content = models.TextField(blank=True)
    citations = models.JSONField(default=list, blank=True)  # source_refs
    status = models.CharField(max_length=16, default="draft")  # draft | approved
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["created_at"]


class TeacherComment(DomainModel):
    """Post-lesson feedback (lesson set) or a general observation about a student (lesson empty)."""

    WRITERS = frozenset({"teaching_support", "role:teacher"})

    class Kind(models.TextChoices):
        LESSON_FEEDBACK = "lesson_feedback"
        OBSERVATION = "observation"

    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="teacher_comments")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_comments")
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.CASCADE, related_name="comments")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    text = models.TextField()

    class Meta:
        ordering = ["created_at"]


class Conversation(DomainModel):
    """Carrier of SM1 Student Service Request messages (owned by the Coordinator)."""

    WRITERS = frozenset({"coordinator"})
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conversations")
    status = models.CharField(max_length=32, default="open")
    awaiting_task = models.ForeignKey("governance.AgentTask", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")


class ChatMessage(DomainModel):
    WRITERS = frozenset({"coordinator", "role:student"})
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=16)  # student | coordinator
    text = models.TextField()
    task = models.ForeignKey("governance.AgentTask", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["created_at"]


class LearningHistoryEntry(DomainModel):
    """AD3 :LearningHistory. Append-only; each agent writes only rows whose source_agent is itself."""

    WRITERS = frozenset({"coordinator", "assessment", "planning", "teaching_support"})
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="learning_history")
    source_agent = models.CharField(max_length=32)
    kind = models.CharField(max_length=32)  # explain | resources | practice | material_completed | ...
    payload = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    escalated = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "learning history entries"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("LearningHistoryEntry is append-only")
        super().save(*args, **kwargs)
