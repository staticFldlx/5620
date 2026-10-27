
"""Persist detected anomalies as operational incidents."""

from django.db import transaction

from domain.governance.models import AgentTask, IncidentRecord
from domain.governance.services import create_incident

from .anomaly_detector import Anomaly


ACTOR = "tech_operations"

# First implementation: these statuses are treated as unresolved.
CLOSED_STATUSES = ("closed", "resolved")


def find_existing_incident(
    anomaly: Anomaly,
) -> IncidentRecord | None:
    """Find an unresolved incident for the same agent and anomaly."""

    subject = (
        f"{anomaly.agent_id}: {anomaly.anomaly_type}"
    )

    latest = (
        IncidentRecord.objects
        .filter(subject=subject)
        .order_by("-created_at")
        .first()
    )
    if latest and latest.status in CLOSED_STATUSES and AgentTask.objects.filter(target_agent=anomaly.agent_id, status="failed", created_at__gt=latest.updated_at).exists():
        return None
    return latest


def create_incident_from_anomaly(
    anomaly: Anomaly,
) -> tuple[IncidentRecord, bool]:
    """
    Create an incident unless an unresolved one already exists.

    Returns:
        (incident, created)
    """

    with transaction.atomic():
        existing = find_existing_incident(anomaly)

        if existing is not None:
            return existing, False

        failed = AgentTask.objects.filter(target_agent=anomaly.agent_id, status="failed").order_by("-created_at").first()
        incident = create_incident(
            actor=ACTOR,
            subject=(
                f"{anomaly.agent_id}: {anomaly.anomaly_type}"
            ),
            severity=anomaly.severity,
            status="detected",
            affected_components=[anomaly.agent_id],
            trigger=anomaly.message,
            evidence=[
                {
                    "ref": f"agent:{anomaly.agent_id}",
                    "summary": str(anomaly.evidence),
                }
            ] + ([{"ref": f"task:{failed.pk}", "summary": "Failed task eligible for policy validation."},
                  {"ref": f"agent:{anomaly.agent_id}:failure", "summary": failed.reason}] if failed else []),
            risk=IncidentRecord.Risk.UNKNOWN,
        )

        return incident, True


def persist_anomalies(
    anomalies: list[Anomaly],
) -> dict:
    """Persist a batch of detected anomalies."""

    created = []
    existing = []

    for anomaly in anomalies:
        incident, is_created = create_incident_from_anomaly(
            anomaly
        )

        record = {
            "incident_id": str(incident.pk),
            "agent_id": anomaly.agent_id,
            "anomaly_type": anomaly.anomaly_type,
            "severity": incident.severity,
            "status": incident.status,
        }

        if is_created:
            created.append(record)
        else:
            existing.append(record)

    return {
        "created_count": len(created),
        "existing_count": len(existing),
        "created": created,
        "existing": existing,
    }
