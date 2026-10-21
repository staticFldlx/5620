
"""AI Technical Manager Agent."""

from agents.runtime import (
    AIAgent,
    AgentResult,
    AgentStatus,
    TaskInput,
)

from domain.governance import selectors as governance

from .audit import (
    audit_monitoring_completed,
    audit_anomaly_detected,
)
from .monitoring import collect_agent_health
from .anomaly_detector import (
    Anomaly,
    detect_all_anomalies,
)
from .incident_detector import persist_anomalies
from .diagnosis_service import diagnose_and_record
from .reporting import generate_maintenance_report

from domain.learning import selectors as learning_selectors

from .record_integrity import check_student_record
from .plan_integrity import check_plan_versions
from .correction import validate_correction
from .correction_proposal import create_correction_proposal
from domain.governance.models import UpdateProposal

from .configuration_workflow import (
    execute_configuration_workflow,
)

class TechOperationsAgent(AIAgent):
    agent_id = "tech_operations"

    task_types = (
        "tech_operations.monitor_agents",
        "tech_operations.detect_anomalies",
        "tech_operations.diagnose_incident",
        "tech_operations.generate_report",
        "tech_operations.apply_correction",
        "tech_operations.check_student_records",
        "tech_operations.check_plan_versions",
        "tech_operations.execute_proposal",
    )

    def execute_task(self, task: TaskInput) -> AgentResult:

        # Restrict management tasks to authorised callers.
        allowed_roles = ("founder", "system")

        if task.ctx.actor_role not in allowed_roles:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="permission_denied",
                payload={
                    "message": (
                        "Technical management tasks require "
                        "Founder or system authorisation."
                    )
                },
            )

        if task.task_type == "tech_operations.monitor_agents":
            return self.monitor_agents()

        if task.task_type == "tech_operations.detect_anomalies":
            return self.detect_system_anomalies()

        if task.task_type == "tech_operations.diagnose_incident":
            return self.handle_diagnosis(task)

        if task.task_type == "tech_operations.generate_report":
            return self.handle_generate_report(task)

        if task.task_type == "tech_operations.apply_correction":
            return self.handle_correction(task)

        if task.task_type == "tech_operations.check_student_records":
            return self.handle_record_integrity(task)

        if task.task_type == "tech_operations.check_plan_versions":
            return self.handle_plan_version_check(task)

        if task.task_type == "tech_operations.execute_proposal":
            return self.handle_execute_proposal(task)

        return AgentResult(
            status=AgentStatus.FAILED,
            reason="unsupported_task_type",
            payload={
                "message": f"Unsupported task: {task.task_type}",
            },
        )

    def monitor_agents(self) -> AgentResult:
        """Collect agent health and record a monitoring audit event."""

        try:
            health = collect_agent_health()

            degraded_count = sum(
                item["status"] == "degraded"
                for item in health
            )

            unknown_count = sum(
                item["status"] == "unknown"
                for item in health
            )

            audit_monitoring_completed(
                total_agents=len(health),
                degraded_agents=degraded_count,
                unknown_agents=unknown_count,
            )

            return AgentResult(
                status=AgentStatus.OK,
                payload={
                    "agents": health,
                    "total_agents": len(health),
                },
            )

        except Exception:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="monitoring_failed",
                payload={
                    "message": "Unable to collect monitoring data.",
                },
            )

    def detect_system_anomalies(self) -> AgentResult:
        """Detect anomalies and create operational incidents."""
        try:
            stats = governance.agent_stats()

            detected = detect_all_anomalies(stats)

            anomalies = [
                Anomaly(**item)
                for item in detected
            ]

            persistence = persist_anomalies(anomalies)

            # Record detected anomalies in the audit trail.
            for anomaly in anomalies:
                audit_anomaly_detected(
                    agent_id=anomaly.agent_id,
                    anomaly_type=anomaly.anomaly_type,
                    severity=anomaly.severity,
                )

            return AgentResult(
                status=AgentStatus.OK,
                payload={
                    "detected_count": len(anomalies),
                    "incidents": persistence,
                },
            )

        except Exception:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="anomaly_detection_failed",
                payload={
                    "message": "Unable to complete anomaly detection.",
                },
            )

    def handle_diagnosis(self, task: TaskInput) -> AgentResult:
        """Diagnose an existing technical incident."""

        # Only the Founder or internal system may request diagnosis.
        if task.ctx.actor_role not in ("founder", "system"):
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="permission_denied",
            )

        incident_id = task.payload.get("incident_id")

        if not incident_id:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="missing_incident_id",
            )

        if self.runtime is None:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="runtime_unavailable",
            )

        try:
            result = diagnose_and_record(
                runtime=self.runtime,
                incident_id=str(incident_id),
            )

            if result["status"] == "escalated":
                return AgentResult(
                    status=AgentStatus.NEEDS_ESCALATION,
                    reason="diagnosis_unavailable",
                    payload=result,
                )

            if result["status"] == "awaiting_approval":
                return AgentResult(
                    status=AgentStatus.AWAITING_APPROVAL,
                    reason="founder_approval_required",
                    payload=result,
                )

            return AgentResult(
                status=AgentStatus.OK,
                payload=result,
            )

        except Exception:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="incident_diagnosis_failed",
            )

    def handle_generate_report(self, task: TaskInput) -> AgentResult:
        """Generate a maintenance report for the Founder."""

        if task.ctx.actor_role not in ("founder", "system"):
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="permission_denied",
            )

        try:
            days = int(task.payload.get("days", 7))

            report = generate_maintenance_report(days=days)

            return AgentResult(
                status=AgentStatus.OK,
                payload=report,
            )

        except (ValueError, TypeError):
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="invalid_report_period",
            )

        except Exception:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="report_generation_failed",
            )

    def handle_correction(self, task: TaskInput) -> AgentResult:
        """Handle Founder-requested controlled corrections."""

        # Only authorised callers may request technical corrections.
        if task.ctx.actor_role not in ("founder", "system"):
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="permission_denied",
            )

        raw_payload = task.payload or {}

        # The Task Queue wraps the original request inside "input".
        nested_input = raw_payload.get("input")

        if isinstance(nested_input, dict):
            payload = nested_input
        else:
            payload = raw_payload

        required_fields = (
            "agent_id",
            "setting",
            "new_value",
            "reason",
        )

        # 1. Handle unstructured Founder requests.
        if not all(field in payload for field in required_fields):
            note = payload.get("note")

            if not isinstance(note, str) or not note.strip():
                return AgentResult(
                    status=AgentStatus.FAILED,
                    reason="missing_correction_note",
                )

            return AgentResult(
                status=AgentStatus.NEEDS_ESCALATION,
                reason="correction_requires_review",
                payload={
                    "requested_action": "apply_correction",
                    "note": note.strip(),
                    "message": (
                        "Unstructured correction request received. "
                        "Manual review is required."
                    ),
                },
            )

        # 2. Validate structured correction requests.
        try:
            correction = validate_correction(payload)
        except (ValueError, TypeError):
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="invalid_correction_request",
            )

        # 3. Create a real UpdateProposal.
        try:
            proposal, created = create_correction_proposal(
                correction
            )
        except Exception:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="proposal_creation_failed",
            )

        # 4. Return approval-required status.
        return AgentResult(
            status=AgentStatus.AWAITING_APPROVAL,
            reason="founder_approval_required",
            payload={
                "proposal_id": str(proposal.pk),
                "proposal_status": proposal.status,
                "proposal_created": created,
                "correction": correction.to_dict(),
            },
        )

    def handle_record_integrity(self, task: TaskInput) -> AgentResult:
        """Check student record integrity using minimal metadata."""

        if task.ctx.actor_role not in ("founder", "system"):
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="permission_denied",
            )

        student_id = task.payload.get("student_id")

        if not student_id:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="missing_student_id",
            )

        try:
            snapshot = (
                learning_selectors.student_record_integrity_snapshot(
                    str(student_id)
                )
            )

            issues = check_student_record(snapshot)

            return AgentResult(
                status=AgentStatus.OK,
                payload={
                    "student_id": str(student_id),
                    "integrity_status": (
                        "valid" if not issues else "issues_detected"
                    ),
                    "issue_count": len(issues),
                    "issues": [
                        issue.to_dict()
                        for issue in issues
                    ],
                },
            )

        except Exception:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="record_integrity_check_failed",
            )

    def handle_plan_version_check(self, task: TaskInput) -> AgentResult:
        """Check learning plan version integrity."""

        if task.ctx.actor_role not in ("founder", "system"):
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="permission_denied",
            )

        student_id = task.payload.get("student_id")

        if not student_id:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="missing_student_id",
            )

        try:
            plans = learning_selectors.student_plan_version_snapshot(
                str(student_id)
            )

            issues = check_plan_versions(plans)

            return AgentResult(
                status=AgentStatus.OK,
                payload={
                    "student_id": str(student_id),
                    "total_plans": len(plans),
                    "issue_count": len(issues),
                    "issues": [
                        issue.to_dict()
                        for issue in issues
                    ],
                },
            )

        except Exception:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="plan_version_check_failed",
            )

    def handle_execute_proposal(self, task: TaskInput) -> AgentResult:
        """Handle Founder-approved technical proposal follow-up."""

        if task.ctx.actor_role not in ("founder", "system"):
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="permission_denied",
            )

        raw_payload = task.payload or {}

        proposal_id = (
                raw_payload.get("subject_id")
                or raw_payload.get("proposal_id")
        )

        if not proposal_id:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="missing_proposal_id",
            )

        try:
            proposal = UpdateProposal.objects.get(pk=proposal_id)

            if proposal.status != "approved":
                return AgentResult(
                    status=AgentStatus.FAILED,
                    reason="founder_approval_required",
                )

            action = (proposal.payload or {}).get("action")

            # Manual review does not execute recovery.
            if (
                    proposal.change_type == "recovery"
                    and action == "request_founder_review"
            ):
                return AgentResult(
                    status=AgentStatus.OK,
                    payload={
                        "proposal_id": str(proposal.pk),
                        "action": action,
                        "execution_status": "manual_review",
                        "message": (
                            "Founder review approved. "
                            "No automatic recovery executed."
                        ),
                    },
                )

            # Approved configuration updates and rollbacks.
            if proposal.change_type == "configuration":
                result = execute_configuration_workflow(
                    str(proposal.pk)
                )

                return AgentResult(
                    status=AgentStatus.OK,
                    payload=result,
                )

            return AgentResult(
                status=AgentStatus.FAILED,
                reason="unsupported_proposal_action",
            )

        except UpdateProposal.DoesNotExist:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="proposal_not_found",
            )

        except PermissionError:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="founder_approval_required",
            )

        except ValueError:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="invalid_proposal_execution",
            )
