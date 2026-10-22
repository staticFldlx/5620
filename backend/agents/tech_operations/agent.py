
"""AI Technical Manager Agent."""

from agents.runtime import (
    AIAgent,
    AgentResult,
    AgentStatus,
    TaskInput,
)

from domain.governance import selectors as governance
from domain.governance.services import record_proposal_execution
from domain.governance.views import proposal_view

from . import fake
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
from .correction import draft_correction, validate_correction
from .correction_proposal import (
    create_correction_proposal,
    create_manual_proposal,
)
from .recovery_executor import (
    execute_approved_recovery,
    resume_approved_agent,
)

from .configuration_workflow import (
    execute_configuration_workflow,
)

class TechOperationsAgent(AIAgent):
    agent_id = "tech_operations"

    # LLM_PROVIDER=fake: scripted replies for offline demos (spec 8.10).
    fake_script = staticmethod(fake.script)

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
        """Detect anomalies, create incidents and diagnose the new ones (UC10 steps 1-4)."""
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

        except Exception:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="anomaly_detection_failed",
                payload={
                    "message": "Unable to complete anomaly detection.",
                },
            )

        # Only new incidents are diagnosed; an open incident keeps its earlier diagnosis.
        diagnoses = [
            self._diagnose_new_incident(item["incident_id"])
            for item in persistence["created"]
        ]

        return AgentResult(
            status=AgentStatus.OK,
            payload={
                "result": {
                    "detected_count": len(anomalies),
                    "incidents": persistence,
                    "diagnoses": diagnoses,
                },
            },
        )

    def _diagnose_new_incident(self, incident_id: str) -> dict:
        """A failed diagnosis is recorded but never fails the detection run."""

        if self.runtime is None:
            return {"incident_id": incident_id, "status": "not_diagnosed"}

        try:
            return diagnose_and_record(
                runtime=self.runtime,
                incident_id=incident_id,
            )
        except Exception as exc:
            self.runtime.note(
                "diagnosis_failed",
                incident_id=incident_id,
                error=f"{type(exc).__name__}: {exc}"[:300],
            )
            return {"incident_id": incident_id, "status": "diagnosis_failed"}

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
        """Founder-requested correction (UC09 5a): draft a controlled update proposal (AR12)."""

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

        try:
            # 1. Structured requests are validated as they are.
            if all(field in payload for field in required_fields):
                try:
                    correction = validate_correction(payload)
                except (ValueError, TypeError):
                    return AgentResult(
                        status=AgentStatus.FAILED,
                        reason="invalid_correction_request",
                    )

                proposal, created = create_correction_proposal(
                    correction
                )

            # 2. The Founder page sends a free-text note: the LLM drafts the proposal.
            else:
                note = payload.get("note")

                if not isinstance(note, str) or not note.strip():
                    return AgentResult(
                        status=AgentStatus.FAILED,
                        reason="missing_correction_note",
                    )

                proposal, created = self._propose_from_note(
                    note.strip()
                )

        except Exception as exc:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="proposal_creation_failed",
                payload={"message": f"Could not create the proposal: {exc}"},
            )

        view = proposal_view(proposal)

        # An identical proposal is already waiting: no second approval case.
        if not created:
            return AgentResult(
                status=AgentStatus.OK,
                payload={
                    "result": {"proposal": view},
                    "message": "An identical proposal is already waiting for approval.",
                },
            )

        # 3. Nothing changes until the Founder approves (Fig 8b). The control keys link the
        # approval case to the proposal, so approving it resumes execute_proposal here.
        return AgentResult(
            status=AgentStatus.AWAITING_APPROVAL,
            reason="founder_approval_required",
            payload={
                "result": {"proposal": view},
                "subject_type": "proposal",
                "subject_id": str(proposal.pk),
                "resume": "tech_operations.execute_proposal",
                "trigger": "Founder approval is required before the correction is applied.",
                "summary": proposal.title,
            },
        )

    def _propose_from_note(self, note: str):
        """Timeout changes become executable configuration proposals; anything else a manual one."""

        draft = draft_correction(self.runtime, note)

        if draft is None:
            # LLM unavailable: keep the request visible as a manual proposal built from the note.
            self.runtime.note("correction_draft_unavailable")
            return create_manual_proposal(
                note,
                title=f"Correction request: {note[:80]}",
                before="As described in the Founder's note.",
                after=note,
                validation="The Founder checks the change after it is made.",
                rollback="Restore the previous state manually.",
            )

        if draft.kind == "timeout":
            try:
                correction = validate_correction({
                    "agent_id": draft.agent_id,
                    "setting": "timeout_seconds",
                    "new_value": draft.new_value,
                    "reason": note,
                })
            except ValueError as exc:
                self.runtime.note("correction_not_executable", error=str(exc))
            else:
                self.runtime.note(
                    "correction_drafted",
                    kind="configuration",
                    agent_id=correction.agent_id,
                    new_value=correction.new_value,
                )
                return create_correction_proposal(correction)

        self.runtime.note("correction_drafted", kind="manual", title=draft.title)
        return create_manual_proposal(
            note,
            title=draft.title,
            before=draft.before,
            after=draft.after,
            validation=draft.validation,
            rollback=draft.rollback,
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

        proposal = governance.proposal(proposal_id)

        if proposal is None:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="proposal_not_found",
                payload={"message": "The approved proposal could not be found."},
            )

        if proposal.status != "approved":
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="founder_approval_required",
                payload={"message": "The proposal has not been approved."},
            )

        action = (proposal.payload or {}).get("action")

        try:
            # Approved configuration updates and rollbacks.
            if proposal.change_type == "configuration":
                result = execute_configuration_workflow(str(proposal.pk))

            # Predefined recovery actions (UC10 step 5).
            elif proposal.change_type == "recovery" and action == "resume_agent":
                result = resume_approved_agent(str(proposal.pk))

            elif proposal.change_type == "recovery" and action == "retry_request":
                result = execute_approved_recovery(str(proposal.pk))

            # Founder review, corpus, prompt and manual changes have no executor:
            # approval is recorded and a person makes the change.
            else:
                result = self._record_manual_change(proposal, action)

        except PermissionError as exc:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="founder_approval_required",
                payload={"message": str(exc)},
            )

        except (ValueError, LookupError) as exc:
            return AgentResult(
                status=AgentStatus.FAILED,
                reason="invalid_proposal_execution",
                payload={"message": f"The proposal could not be executed: {exc}"},
            )

        return AgentResult(
            status=AgentStatus.OK,
            payload={"result": result},
        )

    @staticmethod
    def _record_manual_change(proposal, action) -> dict:
        if proposal.execution_status == "not_started":
            record_proposal_execution(
                "tech_operations",
                proposal,
                execution_status="manual_review",
            )

        return {
            "proposal_id": str(proposal.pk),
            "action": action or proposal.change_type,
            "execution_status": "manual_review",
            "message": (
                "Approval recorded. This change is made by a person; "
                "no automatic action was run."
            ),
        }
