
"""Student record integrity checks.

This module validates a prepared record snapshot.
It does not read or modify student records directly.
"""

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class IntegrityIssue:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_student_record(
    record: dict[str, Any],
) -> list[IntegrityIssue]:
    """Check a structured student record for missing references."""

    issues = []

    student_id = record.get("student_id")

    if not student_id:
        issues.append(
            IntegrityIssue(
                code="missing_student_id",
                severity="high",
                message="Student identifier is missing.",
            )
        )

    if not record.get("profile_exists", False):
        issues.append(
            IntegrityIssue(
                code="missing_learning_profile",
                severity="high",
                message="Student learning profile is unavailable.",
            )
        )

    if (
        record.get("active_plan_id")
        and not record.get("assessment_exists", False)
    ):
        issues.append(
            IntegrityIssue(
                code="plan_without_assessment",
                severity="medium",
                message=(
                    "An active learning plan exists without "
                    "a corresponding assessment record."
                ),
            )
        )

    if (
        record.get("assessment_exists", False)
        and not record.get("proficiency_exists", False)
    ):
        issues.append(
            IntegrityIssue(
                code="assessment_without_proficiency",
                severity="medium",
                message=(
                    "A completed assessment exists, but no "
                    "completed proficiency profile was found."
                ),
            )
        )

    if (
        record.get("active_plan_id")
        and not record.get("plan_assessment_valid", True)
    ):
        issues.append(
            IntegrityIssue(
                code="invalid_plan_assessment_reference",
                severity="high",
                message=(
                    "The active learning plan does not reference "
                    "a valid completed assessment for this student."
                ),
            )
        )


    return issues
