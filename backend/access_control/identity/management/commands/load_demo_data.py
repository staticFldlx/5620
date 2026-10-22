"""Load demo data (spec 8.8).

fixtures/demo_*.json are loaded in name order; each record has a symbolic `key` that becomes a
deterministic UUID (uuid5), so ids are stable across reloads. Agent owners add their own data as
fixtures/<agent_id>_*.json in Django's standard fixture format; those are loaded afterwards.

Seeding is not a business action, so it runs with auditing suppressed and writes rows directly.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from access_control.identity.models import TeacherProfile, User
from domain.common import AGENT_IDS, AGENT_NAMES, audit_suppressed
from domain.governance.models import AgentState, AgentTask, AuditLog, EscalationCase, IncidentRecord, UpdateProposal
from domain.governance.services import touch
from domain.learning.models import (
    AssessmentSession,
    AvailabilitySlot,
    Course,
    LearningHistoryEntry,
    LearningMaterial,
    LearningPlan,
    LearningProfile,
    Lesson,
    LessonMaterial,
    PlanStage,
    ProficiencyProfile,
    TeacherComment,
)
from infrastructure.scheduling import parse_hhmm

NAMESPACE = uuid.UUID("6b1c3f9e-5620-4c1a-9d00-1ee15620a001")
FIXTURES = Path(settings.BASE_DIR) / "fixtures"


def uid(key: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, key)


def when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class Command(BaseCommand):
    help = "Load demo accounts and records from fixtures/ (skipped when already loaded, unless --reset)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="flush the database first")

    def handle(self, *args, reset: bool, **options):
        if reset:
            call_command("flush", interactive=False, verbosity=0)
            for name in ("student", "teacher", "founder"):  # flush also removes the role groups
                Group.objects.get_or_create(name=name)
        elif User.objects.filter(pk=uid("founder-alex")).exists():
            self.stdout.write("demo data already loaded (use --reset to reload)")
            return
        with audit_suppressed(), transaction.atomic():
            for path in sorted(FIXTURES.glob("demo_*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                for section, loader in self.loaders():
                    if section in data:
                        loader(data[section])
                self.stdout.write(f"loaded {path.name}")
        for agent_id in sorted(AGENT_IDS):
            for path in sorted(FIXTURES.glob(f"{agent_id}_*.json")):
                call_command("loaddata", str(path), verbosity=0)
                self.stdout.write(f"loaded {path.name}")

    def loaders(self):
        return [
            ("users", self.users),
            ("learning_materials", self.learning_materials),
            ("courses", self.courses),
            ("profiles", self.profiles),
            ("assessments", self.assessments),
            ("plans", self.plans),
            ("lessons", self.lessons),
            ("lesson_materials", self.lesson_materials),
            ("observations", self.observations),
            ("history", self.history),
            ("agent_states", self.agent_states),
            ("tasks", self.tasks),
            ("reviews", self.reviews),
            ("business_cases", self.business_cases),
            ("incidents", self.incidents),
            ("proposals", self.proposals),
            ("audit", self.audit),
        ]

    # --- identity and catalogue --------------------------------------------------------------
    def users(self, rows):
        for row in rows:
            user = User(pk=uid(row["key"]), username=row["email"], email=row["email"], name=row["name"])
            user.set_password(row["password"])
            user.save()
            user.groups.add(Group.objects.get(name=row["role"]))
            if row["role"] == "teacher":
                TeacherProfile.objects.create(user=user, timezone=row.get("timezone", "Australia/Sydney"), subject_areas=row.get("subject_areas", []))
                for w in row.get("availability", []):
                    AvailabilitySlot.objects.create(teacher=user, day=w["day"], start_time=parse_hhmm(w["start"]), end_time=parse_hhmm(w["end"]))

    def learning_materials(self, rows):
        for row in rows:
            fields = {k: v for k, v in row.items() if k != "key"}
            LearningMaterial.objects.create(pk=uid(row["key"]), **fields)

    def courses(self, rows):
        for row in rows:
            course = Course.objects.create(pk=uid(row["key"]), code=row["key"], title=row["title"], skill=row.get("skill", ""), level=row.get("level", ""))
            course.materials.set([uid(k) for k in row.get("materials", [])])
        for row in rows:
            Course.objects.get(pk=uid(row["key"])).prerequisites.set([uid(k) for k in row.get("prerequisites", [])])

    # --- learning records ----------------------------------------------------------------------
    def profiles(self, rows):
        for row in rows:
            fields = {k: v for k, v in row.items() if k != "student"}
            LearningProfile.objects.create(student_id=uid(row["student"]), **fields)

    def assessments(self, rows):
        for row in rows:
            created = when(row["created_at"])
            session = AssessmentSession.objects.create(
                pk=uid(row["key"] + ":session"),
                student_id=uid(row["student"]),
                type=row["type"],
                status=row["status"],
                focus=row.get("focus", ""),
                items=row["items"],
                max_items=len(row["items"]),
                started_at=created,
                completed_at=created,
            )
            touch(session, created)
            record = ProficiencyProfile.objects.create(pk=uid(row["key"]), session=session, **row["proficiency"])
            touch(record, created)

    def plans(self, rows):
        for row in rows:
            plan = LearningPlan.objects.create(
                pk=uid(row["key"]),
                student_id=uid(row["student"]),
                teacher_id=uid(row["teacher"]),
                version=row["version"],
                status=row["status"],
                weekly_hours=row["weekly_hours"],
                stage_index=row["stage_index"],
                based_on_id=uid(row["based_on"]) if row.get("based_on") else None,
                previous_version_id=uid(row["previous_version"]) if row.get("previous_version") else None,
                rationale=row["rationale"],
                approved_by_id=uid(row["approved_by"]) if row.get("approved_by") else None,
                approved_at=when(row.get("approved_at")),
            )
            touch(plan, when(row["created_at"]))
            for number, stage in enumerate(row["stages"], start=1):
                created = PlanStage.objects.create(
                    pk=uid(f"{row['key']}:stage:{number}"),
                    plan=plan,
                    stage_number=number,
                    title=stage["title"],
                    topics=stage["topics"],
                    milestone=stage["milestone"],
                    status=stage["status"],
                    start_week=stage["start_week"],
                    end_week=stage["end_week"],
                )
                created.courses.set([uid(stage["course"])])

    def lessons(self, rows):
        for row in rows:
            lesson = Lesson.objects.create(
                pk=uid(row["key"]),
                student_id=uid(row["student"]),
                teacher_id=uid(row["teacher"]),
                stage_id=uid(f"{row['plan']}:stage:{row['stage_number']}"),
                title=row["title"],
                starts_at=when(row["starts_at"]),
                ends_at=when(row["ends_at"]),
                status=row["status"],
                attendance=row["attendance"],
            )
            if row.get("feedback"):
                comment = TeacherComment.objects.create(
                    teacher_id=uid(row["teacher"]), student_id=uid(row["student"]), lesson=lesson, kind=TeacherComment.Kind.LESSON_FEEDBACK, text=row["feedback"]
                )
                touch(comment, when(row["ends_at"]))

    def lesson_materials(self, rows):
        for row in rows:
            LessonMaterial.objects.create(
                pk=uid(row["key"]),
                lesson_id=uid(row["lesson"]),
                title=row["title"],
                locator=row["locator"],
                content=row["content"],
                citations=row["citations"],
                status=row["status"],
                approved_by_id=uid(row["approved_by"]) if row.get("approved_by") else None,
            )

    def observations(self, rows):
        for row in rows:
            comment = TeacherComment.objects.create(
                teacher_id=uid(row["teacher"]), student_id=uid(row["student"]), kind=TeacherComment.Kind.OBSERVATION, text=row["text"]
            )
            touch(comment, when(row["created_at"]))

    def history(self, rows):
        for row in rows:
            payload = dict(row["payload"])
            if "source_refs" in payload:
                payload["source_refs"] = [self._material_ref(ref["material_key"]) for ref in payload["source_refs"]]
            if "material_key" in payload:
                payload["material_id"] = str(uid(payload.pop("material_key")))
            entry = LearningHistoryEntry.objects.create(
                pk=uid(row["key"]),
                student_id=uid(row["student"]),
                source_agent=row["source_agent"],
                kind=row["kind"],
                payload=payload,
                confidence=row.get("confidence"),
                escalated=row.get("escalated", False),
            )
            touch(entry, when(row["created_at"]))

    @staticmethod
    def _material_ref(key: str) -> dict:
        material = LessonMaterial.objects.get(pk=uid(key))
        return {"material_id": str(material.pk), "title": material.title, "locator": material.locator}

    # --- governance --------------------------------------------------------------------------------
    def agent_states(self, rows):
        for row in rows:
            AgentState.objects.create(**row)

    def tasks(self, rows):
        # `student` and `subject` link a task to the record it submitted, so a seeded review case
        # can be resumed like a real one (planning.activate_plan checks the submitting task).
        for row in rows:
            time = when(row["time"])
            result = {"summary": row["summary"]}
            if row.get("subject"):
                result["subject_id"] = str(uid(row["subject"]))
            task = AgentTask.objects.create(
                pk=uid(row["key"]),
                task_type=row["task_type"],
                target_agent=row["task_type"].split(".", 1)[0],
                student_id=uid(row["student"]) if row.get("student") else None,
                status=row["status"],
                confidence=row.get("confidence"),
                reason=row.get("reason", ""),
                result=result,
                attempts=1,
                started_at=time,
                finished_at=time,
            )
            touch(task, time)

    def reviews(self, rows):
        for row in rows:
            case = EscalationCase.objects.create(
                pk=uid(row["key"]),
                task_id=uid(row["task"]) if row.get("task") else None,
                kind=row["kind"],
                trigger=row["trigger"],
                confidence=row.get("confidence"),
                assignee_id=uid(row["assignee"]),
                resume_task_type=row.get("resume", ""),
                student_id=uid(row["student"]),
                subject_type=row["subject_type"],
                subject_id=str(uid(row["subject"])),
            )
            touch(case, when(row["created_at"]))

    def business_cases(self, rows):
        for row in rows:
            case = EscalationCase.objects.create(
                pk=uid(row["key"]),
                kind=EscalationCase.Kind.REVIEW,
                trigger=row["trigger"],
                assignee_id=uid(row["assignee"]),
                resume_task_type=row.get("resume", ""),
                student_id=uid(row["student"]) if row.get("student") else None,
                subject_type=EscalationCase.Subject.BUSINESS,
                subject_id=row["key"],
                summary=row["summary"],
                diagnosis=row["diagnosis"],
                evidence=row["evidence"],
            )
            touch(case, when(row["created_at"]))

    def incidents(self, rows):
        for row in rows:
            fields = {k: v for k, v in row.items() if k not in ("key", "created_at")}
            incident = IncidentRecord.objects.create(pk=uid(row["key"]), **fields)
            touch(incident, when(row["created_at"]))

    def proposals(self, rows):
        for row in rows:
            fields = {k: v for k, v in row.items() if k not in ("key", "incident", "created_at")}
            proposal = UpdateProposal.objects.create(pk=uid(row["key"]), incident_id=uid(row["incident"]) if row.get("incident") else None, **fields)
            touch(proposal, when(row["created_at"]))

    def audit(self, rows):
        for row in rows:
            AuditLog.objects.create(
                pk=uid(row["key"]),
                created_at=when(row["time"]),
                actor=row["actor"],
                actor_role="agent",
                actor_name=AGENT_NAMES.get(row["actor"], row["actor"]),
                action=row["action"],
                target_type="incidentrecord",
                target_id=str(uid(row["target"])),
                detail={"summary": row["result"]},
            )
