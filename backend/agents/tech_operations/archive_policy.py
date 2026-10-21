
"""Read-only student record archive eligibility policy."""

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ArchiveDecision:
    eligible: bool
    reasons: list[str]
    requires_founder_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_archive_eligibility(
    *,
    has_active_plan: bool,
    has_upcoming_lessons: bool,
    has_pending_assessments: bool,
    has_unresolved_reviews: bool,
) -> ArchiveDecision:
    """Evaluate operational blockers to student record archiving.

    This function never modifies or deletes student data.
    """

    reasons = []

    if has_active_plan:
        reasons.append("Student has an active learning plan.")

    if has_upcoming_lessons:
        reasons.append("Student has upcoming lessons.")

    if has_pending_assessments:
        reasons.append("Student has pending assessments.")

    if has_unresolved_reviews:
        reasons.append("Student has unresolved reviews.")

    return ArchiveDecision(
        eligible=not reasons,
        reasons=reasons,
        requires_founder_approval=True,
    )
