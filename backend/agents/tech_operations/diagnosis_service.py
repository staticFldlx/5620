
"""Incident diagnosis and persistence."""

import json

from django.db import transaction

from domain.governance.models import IncidentRecord
from domain.governance.services import update_incident

from .diagnosis import diagnose_incident
from .recovery import evaluate_recovery
from .approval_service import request_recovery_approval


def diagnose_and_record(runtime, incident_id: str) -> dict:
    """Diagnose an incident and persist the recommended action."""

    incident = IncidentRecord.objects.get(pk=incident_id)

    # Send only operational evidence to the LLM.
    safe_evidence = [
        {
            "ref": str(item.get("ref", ""))[:100],
            "summary": str(item.get("summary", ""))[:500],
        }
        for item in (incident.evidence or [])[:20]
        if isinstance(item, dict)
        and str(item.get("ref", "")).startswith("agent:")
    ]

    incident_data = {
        "incident_id": str(incident.pk),
        "subject": incident.subject,
        "severity": incident.severity,
        "affected_components": incident.affected_components,
        "trigger": incident.trigger,
        "evidence": safe_evidence,
    }

    diagnosis = diagnose_incident(runtime, incident_data)

    # Case 1: LLM diagnosis unavailable.
    if diagnosis is None:
        with transaction.atomic():
            update_incident(
                "tech_operations",
                incident,
                status="escalated",
                diagnosis=(
                    "LLM diagnosis unavailable; "
                    "Founder review required."
                ),
                risk=IncidentRecord.Risk.UNKNOWN,
                recovery_action="request_founder_review",
            )

        return {
            "incident_id": str(incident.pk),
            "status": "escalated",
            "reason": "diagnosis_unavailable",
            "proposal_id": None,
        }

    # Case 2: Valid structured LLM diagnosis.
    decision = evaluate_recovery(diagnosis)

    risk_mapping = {
        "low": IncidentRecord.Risk.LOW_RISK,
        "critical": IncidentRecord.Risk.CRITICAL,
        "unknown": IncidentRecord.Risk.UNKNOWN,
    }

    next_status = (
        "awaiting_approval"
        if decision.execution_mode == "approval_required"
        else "diagnosed"
    )

    proposal_id = None

    with transaction.atomic():
        update_incident(
            "tech_operations",
            incident,
            status=next_status,
            diagnosis=json.dumps(
                diagnosis.model_dump(),
                ensure_ascii=False,
            ),
            risk=risk_mapping[diagnosis.risk_level],
            recovery_action=decision.action,
        )

        if decision.execution_mode == "approval_required":
            proposal, _ = request_recovery_approval(
                str(incident.pk),
                action=decision.action,
                rationale=(
                    f"Probable cause: {diagnosis.probable_cause}. "
                    f"Confidence: {diagnosis.confidence:.2f}. "
                    f"Reason: {decision.reason}"
                ),
            )

            proposal_id = str(proposal.pk)

    return {
        "incident_id": str(incident.pk),
        "status": next_status,
        "proposal_id": proposal_id,
        "diagnosis": diagnosis.model_dump(),
        "recovery": {
            "action": decision.action,
            "execution_mode": decision.execution_mode,
            "reason": decision.reason,
        },
    }
