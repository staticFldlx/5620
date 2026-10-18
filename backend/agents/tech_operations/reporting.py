
"""Maintenance report generation for AI Technical Manager."""

from datetime import timedelta

from django.utils import timezone

from domain.governance.models import IncidentRecord
from .monitoring import collect_agent_health


CLOSED_STATUSES = ("closed", "resolved")


def generate_maintenance_report(days: int = 7) -> dict:
    """Generate a structured operational maintenance report."""

    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")

    now = timezone.now()
    start = now - timedelta(days=days)

    # Reuse the existing agent monitoring service.
    agents = collect_agent_health()

    degraded = [
        agent for agent in agents
        if agent["status"] == "degraded"
    ]

    unknown = [
        agent for agent in agents
        if agent["status"] == "unknown"
    ]

    # Query incidents created within the requested period.
    incidents = IncidentRecord.objects.filter(
        created_at__gte=start,
        created_at__lte=now,
    ).order_by("-created_at")

    incident_list = [
        {
            "incident_id": str(incident.pk),
            "subject": incident.subject,
            "severity": incident.severity,
            "status": incident.status,
            "affected_components": incident.affected_components,
            "created_at": incident.created_at.isoformat(),
        }
        for incident in incidents
    ]

    unresolved = [
        incident for incident in incident_list
        if incident["status"] not in CLOSED_STATUSES
    ]

    return {
        "report_type": "maintenance",
        "generated_at": now.isoformat(),
        "period_days": days,
        "period_start": start.isoformat(),
        "period_end": now.isoformat(),
        "summary": {
            "total_agents": len(agents),
            "degraded_agents": len(degraded),
            "unknown_agents": len(unknown),
            "incidents_in_period": len(incident_list),
            "unresolved_incidents_in_period": len(unresolved),
        },
        "agent_health": agents,
        "incidents": incident_list,
        "warnings": [
            {
                "agent_id": agent["agent_id"],
                "warnings": agent["warnings"],
            }
            for agent in degraded
        ],
    }
