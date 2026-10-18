
"""Read-only student record maintenance summary."""

from domain.learning import selectors as learning_selectors

from .record_integrity import check_student_record
from .plan_integrity import check_plan_versions
from .archive_policy import evaluate_archive_eligibility


def validate_student(student_id: str) -> None:
    """Ensure the student exists, is active, and has Student role."""

    if not student_id:
        raise ValueError("student_id is required")

    student = learning_selectors.student(student_id)

    if student is None:
        raise LookupError("Student not found or inactive")

def get_student_record_health(
    student_id: str,
    *,
    history_limit: int = 20,
) -> dict:
    """Aggregate record integrity, plan versions and history."""

    validate_student(student_id)

    if not 1 <= history_limit <= 100:
        raise ValueError("history_limit must be between 1 and 100")

    snapshot = (
        learning_selectors.student_record_integrity_snapshot(
            student_id
        )
    )

    plans = learning_selectors.student_plan_version_snapshot(
        student_id
    )

    history = learning_selectors.student_learning_history_summary(
        student_id,
        limit=history_limit,
    )

    record_issues = check_student_record(snapshot)
    plan_issues = check_plan_versions(plans)

    issues = [
        issue.to_dict()
        for issue in record_issues + plan_issues
    ]

    return {
        "student_id": student_id,
        "integrity_status": (
            "valid" if not issues else "issues_detected"
        ),
        "issue_count": len(issues),
        "issues": issues,
        "plan_version_count": len(plans),
        "history": history,
    }

def get_student_archive_eligibility(student_id: str) -> dict:
    """Check whether student records have archive blockers."""

    validate_student(student_id)

    snapshot = learning_selectors.student_archive_snapshot(
        student_id
    )

    decision = evaluate_archive_eligibility(
        has_active_plan=snapshot["has_active_plan"],
        has_upcoming_lessons=snapshot["has_upcoming_lessons"],
        has_pending_assessments=snapshot["has_pending_assessments"],
        has_unresolved_reviews=snapshot["has_unresolved_reviews"],
    )

    return {
        "student_id": str(student_id),
        "archive_eligibility": decision.to_dict(),
        "blockers": snapshot,
    }
