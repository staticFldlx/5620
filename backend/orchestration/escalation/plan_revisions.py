"""Student revision details and withdrawal of an unapproved, student-owned draft."""
from django.db import transaction

from domain.common import DomainError
from domain.governance import selectors as governance, services as gov
from domain.learning import selectors as learning, services as learning_services


def revision_details(plan):
    case = governance.latest_case_for("plan", plan.pk)
    request = case.task.request if case and case.task else None
    if not request or request.type != "revise_plan":
        return None
    active = learning.active_plan(plan.student)
    pending = learning.pending_plan(plan.student)
    own_request = request.actor_id == plan.student_id and request.actor_role == "student"
    return {
        "reason": str(request.input.get("reason", "")),
        "submitted_at": request.created_at.isoformat(),
        "can_withdraw": bool(own_request and case.status == "open"
            and plan.status == "pending_review" and request.status == "awaiting_approval"
            and active and plan.version > active.version and pending and pending.pk == plan.pk),
    }


@transaction.atomic
def withdraw_revision(plan, *, by):
    if plan.student_id != by.pk:
        raise DomainError("forbidden", "This plan belongs to another student.", status=403)
    details = revision_details(plan)
    if not details or not details["can_withdraw"]:
        raise DomainError("revision_not_withdrawable", "This revision can no longer be withdrawn. Refresh your plan.")
    case = governance.latest_case_for("plan", plan.pk)
    # resolve_case locks and rechecks persisted status: approval and withdrawal cannot both win.
    gov.resolve_case("escalation_manager", case,
        decision={"action": "withdraw", "note": "Student withdrew the revision request."}, by=by)
    request = case.task.request
    learning_services.update_plan("planning", plan, status="withdrawn")
    # A teacher may have requested corrections within this same revision. Do not let its
    # older draft reappear as pending after the latest draft is withdrawn.
    predecessor = plan.previous_version
    while predecessor and predecessor.status == "changes_requested":
        learning_services.update_plan("planning", predecessor, status="withdrawn")
        predecessor = predecessor.previous_version
    gov.transition_request("task_queue", request, "completed", phase="withdrawn",
        result={"withdrawn": True, "plan_id": str(plan.pk)}, remaining_steps=[])
    learning_services.append_history("planning", student=by, kind="plan_revision_withdrawn",
        payload={"plan_id": str(plan.pk), "version": plan.version, "request_id": str(request.pk)})
    gov.record_audit(by, "plan.revision_withdrawn", plan, request_id=str(request.pk))
    return {"withdrawn": True}
