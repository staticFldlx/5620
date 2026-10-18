
"""Build an incident timeline from existing audit records."""

from uuid import UUID

from django.db.models import Q

from domain.governance.models import (
    AuditLog,
    IncidentRecord,
    UpdateProposal,
)


def get_incident_timeline(
    incident_id: str,
    *,
    limit: int = 100,
) -> dict:
    """Return incident and linked proposal audit events."""

    incident_uuid = UUID(str(incident_id))

    incident = IncidentRecord.objects.get(pk=incident_uuid)

    proposal_ids = [
        str(pk)
        for pk in UpdateProposal.objects.filter(
            incident=incident
        ).values_list("pk", flat=True)
    ]

    filters = Q(
        target_type="incidentrecord",
        target_id=str(incident.pk),
    )

    if proposal_ids:
        filters |= Q(
            target_type="updateproposal",
            target_id__in=proposal_ids,
        )

    limit = max(1, min(limit, 200))

    audit_entries = (
        AuditLog.objects
        .filter(filters)
        .order_by("created_at", "pk")[:limit]
    )

    events = [
        {
            "id": str(entry.pk),
            "timestamp": entry.created_at.isoformat(),
            "action": entry.action,
            "actor": entry.actor,
            "actor_role": entry.actor_role,
            "target_type": entry.target_type,
            "target_id": entry.target_id,
            "detail": entry.detail,
        }
        for entry in audit_entries
    ]

    return {
        "incident_id": str(incident.pk),
        "subject": incident.subject,
        "status": incident.status,
        "severity": incident.severity,
        "proposal_ids": proposal_ids,
        "total_events": len(events),
        "events": events,
    }
