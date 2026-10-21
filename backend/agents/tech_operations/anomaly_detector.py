
"""Rule-based anomaly detection for AI Technical Manager."""

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class AnomalyThresholds:
    failure_rate: float = 0.30
    avg_duration_ms: int = 10000
    min_tasks: int = 5


@dataclass
class Anomaly:
    agent_id: str
    anomaly_type: str
    severity: str
    message: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_anomalies(
    agent_id: str,
    stats: dict[str, Any],
    thresholds: AnomalyThresholds | None = None,
) -> list[Anomaly]:
    """Detect anomalies using aggregated operational metrics."""

    thresholds = thresholds or AnomalyThresholds()
    anomalies = []

    tasks = stats.get("tasks", 0)
    failure_rate = stats.get("failure_rate", 0.0)
    avg_duration = stats.get("avg_duration_ms")

    # Insufficient evidence for rate-based detection.
    if tasks < thresholds.min_tasks:
        return anomalies

    if failure_rate >= thresholds.failure_rate:
        severity = "critical" if failure_rate >= 0.70 else "high"

        anomalies.append(
            Anomaly(
                agent_id=agent_id,
                anomaly_type="high_failure_rate",
                severity=severity,
                message="Agent failure rate exceeds threshold.",
                evidence={
                    "tasks": tasks,
                    "failure_rate": failure_rate,
                    "threshold": thresholds.failure_rate,
                },
            )
        )

    if (
        avg_duration is not None
        and avg_duration > thresholds.avg_duration_ms
    ):
        anomalies.append(
            Anomaly(
                agent_id=agent_id,
                anomaly_type="high_latency",
                severity="medium",
                message="Agent average response time exceeds threshold.",
                evidence={
                    "tasks": tasks,
                    "avg_duration_ms": avg_duration,
                    "threshold_ms": thresholds.avg_duration_ms,
                },
            )
        )

    return anomalies


def detect_all_anomalies(
    stats_by_agent: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect anomalies across all agents."""

    results = []

    for agent_id, stats in stats_by_agent.items():
        anomalies = detect_anomalies(agent_id, stats)

        results.extend(
            anomaly.to_dict()
            for anomaly in anomalies
        )

    return results
