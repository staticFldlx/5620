"""Extra users only in the disposable browser-test database, never in demo/live data."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.conf import settings
from django.contrib.auth.models import Group
from django.utils import timezone
from datetime import timedelta
from access_control.identity.models import User
from domain.learning.models import AssessmentSession, ProficiencyProfile, LearningProfile, LearningPlan, PlanStage, Lesson, Course

assert os.environ.get("E2E_PROGRESS_SCENARIOS") == "true"
assert "lingopath-browser-" in str(settings.DATABASES["default"]["NAME"])
teacher = User.objects.get(email="emily.walker@example.com")
for label in ("Progress", "Deviation", "Revision"):
    user = User.objects.create_user(username=f"{label.lower()}-test", email=f"{label.lower()}@test.example", name=f"{label} Learner", password="demo1238")
    user.groups.add(Group.objects.get(name="student"))
    LearningProfile.objects.create(student=user, english_level="B2", learning_goal="Improve academic reading and writing",
        structured_objective={"summary": "Academic reading and writing", "target_level": "C1", "focus_skills": ["Reading", "Writing"]},
        preferences={"weekly_hours": 4, "timezone": "Australia/Sydney", "availability": [{"day": "Tue", "start": "18:00", "end": "20:00"}]})
    session = AssessmentSession.objects.create(student=user, type="initial", status="completed")
    proficiency = ProficiencyProfile.objects.create(session=session, overall_level="B2", status="confirmed", confidence=.95)
    plan = LearningPlan.objects.create(student=user, teacher=teacher, based_on=proficiency, status="active", version=1,
        weekly_hours=4, rationale="Approved test learning plan", approved_by=teacher, approved_at=timezone.now())
    for index, code in enumerate(("CAT-01", "CAT-02")):
        stage = PlanStage.objects.create(plan=plan, stage_number=index+1, title=f"{label} stage {index+1}",
            status="current" if index == 0 else "upcoming", start_week=index*2+1, end_week=index*2+2,
            topics=["Evidence and explanation"], milestone="Demonstrate B2 reading and writing")
        stage.courses.add(Course.objects.get(code=code))
        start = timezone.now() - timedelta(days=4-index)
        Lesson.objects.create(student=user, teacher=teacher, stage=stage, title=f"{label} checkpoint lesson {index+1}",
            starts_at=start, ends_at=start+timedelta(hours=1), status="confirmed")
