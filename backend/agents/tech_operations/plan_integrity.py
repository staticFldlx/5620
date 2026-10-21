
"""Learning plan version consistency checks."""

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class PlanVersionIssue:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_plan_versions(
    plans: list[dict],
) -> list[PlanVersionIssue]:
    """Check version uniqueness and previous-version references."""

    issues = []

    versions = [
        plan["version"]
        for plan in plans
    ]

    if len(versions) != len(set(versions)):
        issues.append(
            PlanVersionIssue(
                code="duplicate_plan_version",
                severity="high",
                message="Duplicate learning plan versions detected.",
            )
        )

    plan_ids = {
        plan["plan_id"]
        for plan in plans
    }

    for plan in plans:
        previous_id = plan.get("previous_version_id")

        if previous_id and previous_id not in plan_ids:
            issues.append(
                PlanVersionIssue(
                    code="invalid_previous_version",
                    severity="medium",
                    message=(
                        "Learning plan references a previous "
                        "version outside the student's plan history."
                    ),
                )
            )

    active_count = sum(
        plan["status"] == "active"
        for plan in plans
    )

    if active_count > 1:
        issues.append(
            PlanVersionIssue(
                code="multiple_active_plans",
                severity="high",
                message="Multiple active learning plans detected.",
            )
        )

    return issues
