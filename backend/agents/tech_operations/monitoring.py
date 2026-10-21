
"""Operational monitoring for the AI Technical Manager."""

from dataclasses import dataclass, asdict
from typing import Any

from domain.governance import selectors as governance


@dataclass
class AgentHealth:
    agent_id: str
    status: str
    total_tasks: int
    failure_rate: float
    escalation_rate: float
    avg_duration_ms: int | None
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_agent_health(
    agent_id: str,
    stats: dict[str, Any],
) -> AgentHealth:
    """Evaluate an agent using operational statistics."""

    tasks = stats.get("tasks", 0)
    failure_rate = stats.get("failure_rate", 0.0)
    escalation_rate = stats.get("escalation_rate", 0.0)
    avg_duration = stats.get("avg_duration_ms")

    warnings = []

    if tasks == 0:
        return AgentHealth(
            agent_id=agent_id,
            status="unknown",
            total_tasks=0,
            failure_rate=0.0,
            escalation_rate=0.0,
            avg_duration_ms=None,
            warnings=["No recent execution data"],
        )

    # Initial demonstration thresholds.
    # These can be tuned after collecting real metrics.
    if failure_rate >= 0.3:
        warnings.append("High failure rate")

    if avg_duration is not None and avg_duration > 10000:
        warnings.append("High average response time")

    status = "degraded" if warnings else "healthy"

    return AgentHealth(
        agent_id=agent_id,
        status=status,
        total_tasks=tasks,
        failure_rate=failure_rate,
        escalation_rate=escalation_rate,
        avg_duration_ms=avg_duration,
        warnings=warnings,
    )


def collect_agent_health() -> list[dict[str, Any]]:
    """Collect operational metrics without reading student data."""

    stats = governance.agent_stats()

    agent_ids = [
        "coordinator",
        "assessment",
        "planning",
        "teaching_support",
    ]

    results = []

    for agent_id in agent_ids:
        agent_stats = stats.get(agent_id, {})
        health = get_agent_health(agent_id, agent_stats)
        results.append(health.to_dict())

    return results
