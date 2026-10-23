from ninja import Router

from access_control.identity.permissions import require_role
from domain.common import Role
from domain.governance import selectors as governance
from domain.learning import selectors as learning
from orchestration.escalation.plan_revisions import withdraw_revision
from domain.governance.models import EscalationCase
from domain.governance.views import request_envelope, review_view
from orchestration.escalation import escalation_manager

from .. import lookups, presenters
from ..schemas import ReviewDecisionIn, ReviewDecisionOut, ReviewDetailOut

router = Router(tags=["reviews"])
LEARNING = {EscalationCase.Subject.ASSESSMENT, EscalationCase.Subject.PLAN, EscalationCase.Subject.QUESTION}


def _assigned_case(user, review_id: str) -> EscalationCase:
    require_role(user, Role.TEACHER, Role.FOUNDER)
    case = lookups.get_or_404(governance.case, review_id, "Review")
    if case.subject_type not in LEARNING:
        raise lookups.not_found("Review")
    lookups.require_owner(case.assignee_id == user.pk, "This review is assigned to another teacher.")
    return case


@router.get("/reviews/{review_id}", response=ReviewDetailOut)
def get_review(request, review_id: str):
    return presenters.review_detail(_assigned_case(request.auth, review_id))


@router.post("/reviews/{review_id}/decision", response=ReviewDecisionOut)
def decide_review(request, review_id: str, body: ReviewDecisionIn):
    """Teacher decision; the paused flow resumes (e.g. plan activation, assessment confirmation)."""
    user = request.auth
    case = _assigned_case(user, review_id)
    follow_up = escalation_manager.decide_review(case, action=body.action, note=body.note, by=user, corrected_level=body.corrected_level)
    case.refresh_from_db()
    return {
        "review": review_view(case),
        "updated_subject": presenters.review_subject(case),
        "follow_up": request_envelope(follow_up) if follow_up is not None else None,
    }


@router.post("/plans/{plan_id}/withdraw", response=dict)
def withdraw_plan_revision(request, plan_id: str):
    """Withdraw only the caller's student-requested, unapproved revision."""
    require_role(request.auth, Role.STUDENT)
    plan = lookups.get_or_404(learning.plan, plan_id, "Plan")
    return withdraw_revision(plan, by=request.auth)
