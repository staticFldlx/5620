
"""Recovery policy for AI Technical Manager."""

from dataclasses import dataclass
from typing import Literal

from .diagnosis import DiagnosisResult


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    execution_mode: Literal[
        "automatic",
        "approval_required",
        "no_action",
    ]
    reason: str


def evaluate_recovery(
    diagnosis: DiagnosisResult,
) -> RecoveryDecision:
    """Evaluate a recovery recommendation.

    Automatic mode is only an eligibility decision.
    Actual execution is handled separately.
    """

    action = diagnosis.recommended_action

    if action == "no_action":
        return RecoveryDecision(
            action=action,
            execution_mode="no_action",
            reason="No recovery action recommended.",
        )

    if (
        action == "retry_request"
        and diagnosis.risk_level == "low"
        and diagnosis.confidence >= 0.8
    ):
        return RecoveryDecision(
            action=action,
            execution_mode="automatic",
            reason="Eligible for predefined low-risk recovery.",
        )

    return RecoveryDecision(
        action=action,
        execution_mode="approval_required",
        reason="Human Founder review is required.",
    )
