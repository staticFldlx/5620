"""Publish one assessment per ready stage, preserving the shared assessment pipeline."""
from django.db import transaction
from domain.learning import selectors as learning
from domain.learning.models import LearningPlan, PlanStage
from domain.common import save_fields
from domain.governance.models import ServiceRequest
from orchestration.task_queue import dispatcher


def publish_ready_milestone(student, actor, *, retry_rejected=False):
    with transaction.atomic():
        plan = LearningPlan.objects.select_for_update().filter(student=student, status="active").first()
        if plan is None:
            return None
        stage = PlanStage.objects.select_related("milestone_request").filter(plan=plan, stage_number=plan.stage_index + 1).first()
        if stage is None or stage.status == "completed" or not learning.stage_lessons_attended(stage):
            return None
        prior = stage.milestone_request
        if prior and prior.status != ServiceRequest.Status.FAILED:
            return prior
        # A rejected result requires the learner to start a new attempt; never loop automatically.
        if prior and (prior.error or {}).get("code") == "assessment_changes_requested" and not retry_rejected:
            return prior
        request = dispatcher.submit("start_assessment", actor=actor, actor_role="system", student=student,
            input={"kind": "milestone", "focus": f"Stage {stage.stage_number}: {stage.milestone or stage.title}"[:200], "milestone_stage_id": str(stage.pk)})
        save_fields("planning", stage, "stage.milestone_published", {"milestone_request": request})
        return request

