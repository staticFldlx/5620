
"""Additional operational audit events for AI Technical Manager."""

from typing import Any

from domain.governance.services import record_audit as record


ACTOR = "tech_operations"


def audit_monitoring_completed(
    *,
    total_agents: int,
    degraded_agents: int,
    unknown_agents: int,
) -> None:
    """Record a completed monitoring cycle."""

    record(
        ACTOR,
        "monitoring.completed",
        ("monitoring", "agent_health"),
        detail={
            "total_agents": total_agents,
            "degraded_agents": degraded_agents,
            "unknown_agents": unknown_agents,
        },
    )


def audit_anomaly_detected(
    *,
    agent_id: str,
    anomaly_type: str,
    severity: str,
) -> None:
    """Record a detected operational anomaly."""

    record(
        ACTOR,
        "anomaly.detected",
        ("agent", agent_id),
        detail={
            "anomaly_type": anomaly_type,
            "severity": severity,
        },
    )


def audit_diagnosis_completed(
    *,
    incident_id: str,
    confidence: float,
    recommended_action: str,
    risk_level: str,
) -> None:
    """Record diagnosis metadata without storing private logs."""

    record(
        ACTOR,
        "incident.diagnosed",
        ("incidentrecord", incident_id),
        detail={
            "confidence": confidence,
            "recommended_action": recommended_action,
            "risk_level": risk_level,
        },
    )
