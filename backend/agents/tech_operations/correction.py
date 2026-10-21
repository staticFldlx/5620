
"""Validate controlled Agent correction requests."""

from dataclasses import dataclass, asdict
from typing import Any


ALLOWED_AGENTS = frozenset({
    "assessment",
    "planning",
    "teaching_support",
    "coordinator",
})

ALLOWED_SETTINGS = {
    "timeout_seconds": {
        "min": 5,
        "max": 120,
    },
    "max_retries": {
        "min": 0,
        "max": 3,
    },
}


@dataclass(frozen=True)
class CorrectionRequest:
    agent_id: str
    setting: str
    new_value: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_correction(
    data: dict[str, Any],
) -> CorrectionRequest:
    """Validate a controlled Agent configuration change."""

    agent_id = data.get("agent_id")
    setting = data.get("setting")
    new_value = data.get("new_value")
    reason = data.get("reason", "")

    if agent_id not in ALLOWED_AGENTS:
        raise ValueError("Unsupported agent")

    if setting not in ALLOWED_SETTINGS:
        raise ValueError("Unsupported setting")

    if type(new_value) is not int:
        raise ValueError("Setting value must be an integer")

    limits = ALLOWED_SETTINGS[setting]

    if not limits["min"] <= new_value <= limits["max"]:
        raise ValueError("Setting value outside allowed range")

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Correction reason is required")

    return CorrectionRequest(
        agent_id=agent_id,
        setting=setting,
        new_value=new_value,
        reason=reason.strip(),
    )
