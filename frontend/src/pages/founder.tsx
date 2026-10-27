import { useEffect, useState } from "react"
import { Link } from "react-router"
import {
  Activity,
  ArrowRight,
  ClipboardCheck,
  Radar,
  Pause,
  Play,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react"
import { api } from "@/api/client"
import { displayText, type DisplayReference } from "@/lib/display-text"
import { useApp } from "@/app-context"
import { AIButton } from "@/components/ai-button"
import type { Case, Proposal } from "@/api/types"
import {
  AIVisual,
  Empty,
  Metric,
  Page,
  Panel,
  Pill,
  Row,
} from "@/components/layout"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
const time = (value: string) =>
  new Date(value).toLocaleString("en-AU", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Australia/Sydney",
  })
// Translate machine labels without changing narrative summaries returned by the API.
function readableLabel(value: string) {
  const labels: Record<string, string> = {
    "planning.activate_plan": "Activate learning plan",
    "planning.generate_plan": "Generate learning plan",
    "planning.revise_plan": "Revise learning plan",
    "coordinator.confirm_goal": "Confirm learning goal",
    "assessment.conduct_assessment": "Conduct assessment",
    "tech_operations.execute_proposal": "Execute approved proposal",
    "teaching_support.lesson_briefing": "Prepare lesson briefing",
    healthy: "Healthy",
    degraded: "Needs attention",
    paused: "Paused",
    not_implemented: "Not available",
    pending_review: "Awaiting review",
  }
  if (labels[value]) return labels[value]
  if (/^[a-z_]+(?:\.[a-z_]+)?$/.test(value)) {
    const words = value.split(".").at(-1)!.replaceAll("_", " ")
    return words.charAt(0).toUpperCase() + words.slice(1)
  }
  return displayText(value) || "No recent activity"
}
// Display labels only: original identifiers remain in API calls and audit records.
function governanceLabel(value: string) {
  const labels: Record<string, string> = {
    corpus: "Learning materials update",
    recovery: "Service recovery",
    configuration: "Agent configuration",
    permission: "Access permissions",
    archive: "Record archiving",
    prompt: "AI instructions update",
    manual: "Manual change",
    pending: "Awaiting decision",
    pending_review: "Awaiting review",
    awaiting_approval: "Awaiting approval",
    recovery_pending_verification: "Recovery awaiting verification",
    not_started: "Not started",
    manual_review: "Manual action required",
    pending_implementation: "Not implemented",
    succeeded: "Completed successfully",
    "agent.healthy": "Agent resumed",
    "agent.paused": "Agent paused",
    "agent.correction_requested": "Agent correction requested",
    "user.login": "User signed in",
    "profile.created": "Learning profile created",
    "profile.updated": "Learning profile updated",
    "proficiency.recorded": "Assessment result recorded",
    "proficiency.updated": "Assessment result updated",
    "assessment_session.created": "Assessment started",
    "assessment_session.updated": "Assessment progress updated",
    "escalation.created": "Human review requested",
    "escalation.resolved": "Human review completed",
    "availability.replaced": "Teaching availability updated",
    "proposal.verified": "Proposal execution verified",
    "proposal.rollback_metadata_saved": "Rollback information saved",
    "history.explain": "Learning question recorded",
    "history.resources": "Learning resources recommended",
    "history.practice": "Practice exercise created",
    "history.practice_answer": "Practice feedback recorded",
    "history.progress_decision": "Learning progress decision recorded",
    "history.plan_draft": "Plan draft recorded",
    "history.material_completed": "Learning material completed",
    "teaching_support.corpus_gap": "Missing learning materials reported",
  }
  if (labels[value]) return labels[value]
  // Preserve narrative text; expand new machine labels without dropping the subject.
  if (/^[a-z_]+(?:\.[a-z_]+)*$/.test(value)) {
    const words = value.replaceAll(".", " ").replaceAll("_", " ")
    return words.charAt(0).toUpperCase() + words.slice(1)
  }
  return displayText(value)
}
function Details({
  value,
  references = [],
}: {
  value: string
  references?: DisplayReference[]
}) {
  return (
    <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
      {displayText(value, references)}
    </p>
  )
}
function useOperations() {
  return useApp().workspace?.operations
}
export function FounderOverview() {
  const ops = useOperations()
  const { run, busy } = useApp()
  const [controlNote, setControlNote] = useState("")
  const [showAllLogs, setShowAllLogs] = useState(false)
  const logs = ops?.logs || []
  const visibleLogs = showAllLogs ? logs : logs.slice(0, 10)
  const pending = ops?.proposals.filter((x) => x.status === "pending") || []
  return (
    <Page
      eyebrow="OBSERVABLE OPERATIONS · HUMAN AUTHORITY"
      title="A clear view of the system."
      subtitle="Monitor AI roles and decide where human intervention is needed."
    >
      <div className="metric-grid">
        <Metric
          label="Tasks in recent logs"
          value={logs.length}
          note="Loaded record sample"
          icon={Activity}
        />
        <Metric
          label="Failed tasks"
          value={logs.filter((x) => x.task_status === "failed").length}
          note="From the same log sample"
          icon={TriangleAlert}
        />
        <Metric
          label="Open exceptions"
          value={ops?.cases.filter((x) => x.status !== "resolved").length || 0}
          note="Business and technical cases"
          icon={Radar}
        />
        <Metric
          label="Pending decisions"
          value={pending.length}
          note="From proposal status"
          icon={ClipboardCheck}
        />
      </div>
      <div className="board two-thirds">
        <Panel className="operations-hero" title="Agent controls">
          <p>
            Pause or resume an individual agent. Existing pages and saved
            content remain available.
          </p>
          <label className="field-label">
            Agent decision reason
            <Textarea
              aria-describedby="agent-control-help"
              value={controlNote}
              onChange={(event) => setControlNote(event.target.value)}
              placeholder="Explain why the agent should be paused or resumed"
            />
          </label>
          <p id="agent-control-help">
            Enter a reason to enable the buttons, then choose an agent below.
            The reason is recorded with that action; it is not a command to all
            agents.
          </p>
          <div className="agent-grid">
            {ops?.agents.map((agent) => (
              <div className="agent-card" key={agent.id}>
                <span className="agent-pulse" />
                <strong>{agent.name}</strong>
                <small>{readableLabel(agent.latest_task.output_summary)}</small>
                <span className="agent-status-label">Current status</span>
                <Pill tone={agent.status === "healthy" ? "good" : "warn"}>
                  {readableLabel(agent.status)}
                </Pill>
                <Button
                  className="action primary agent-control-button"
                  aria-describedby="agent-control-help"
                  disabled={
                    busy ||
                    !controlNote.trim() ||
                    agent.status === "not_implemented"
                  }
                  onClick={() =>
                    run(
                      () =>
                        api.decideAgent(
                          agent.id,
                          agent.status === "paused" ? "resume" : "pause",
                          controlNote
                        ),
                      `Agent ${agent.status === "paused" ? "resumed" : "paused"}.`
                    )
                  }
                >
                  {agent.status === "paused" ? (
                    <Play size={15} />
                  ) : (
                    <Pause size={15} />
                  )}
                  {agent.status === "paused" ? "Resume agent" : "Pause agent"}
                </Button>
              </div>
            ))}
          </div>
          <AIVisual variant="signal" />
        </Panel>
        <Panel title="Needs your decision">
          {ops?.cases
            .filter((x) => x.status !== "resolved")
            .slice(0, 3)
            .map((item) => (
              <Row
                key={item.id}
                title={displayText(item.subject)}
                detail={displayText(item.trigger)}
                right={
                  <Link
                    className="text-link"
                    to={item.kind === "technical" ? "/f3" : "/f2"}
                  >
                    Review →
                  </Link>
                }
              />
            ))}
        </Panel>
        <Panel title="Recent agent activity" className="founder-activity">
          <p>
            Escalated tasks in this sample:{" "}
            {logs.filter((log) => log.escalated).length} of {logs.length}.
            Confidence is shown only when provided.
          </p>
          {logs.length ? (
            <>
              <ol className="founder-task-list">
                {visibleLogs.map((log) => (
                  <li key={log.id}>
                    <strong>
                      {ops?.agents.find((agent) => agent.id === log.agent_id)
                        ?.name || readableLabel(log.agent_id)}
                    </strong>
                    <p>{readableLabel(log.event)}</p>
                    <div className="founder-task-meta">
                      <span>Status: {readableLabel(log.task_status)}</span>
                      <span>
                        Confidence:{" "}
                        {log.confidence == null
                          ? "Not available"
                          : `${Math.round(log.confidence * 100)}%`}
                      </span>
                      {log.escalated && <Pill tone="warn">Escalated</Pill>}
                      <time dateTime={log.time}>{time(log.time)}</time>
                    </div>
                  </li>
                ))}
              </ol>
              {logs.length > 10 && (
                <Button
                  className="action secondary"
                  onClick={() => setShowAllLogs(!showAllLogs)}
                >
                  {showAllLogs
                    ? "Show fewer tasks"
                    : `Show all ${logs.length} tasks`}
                </Button>
              )}
            </>
          ) : (
            <Empty>No recent agent activity.</Empty>
          )}
        </Panel>
        <Panel title="Latest agent outputs">
          {ops?.agents.map((agent) => (
            <Row
              key={agent.id}
              title={agent.name}
              detail={readableLabel(agent.latest_task.output_summary)}
              right={
                <Pill
                  tone={
                    agent.latest_task.status === "completed" ? "good" : "warn"
                  }
                >
                  {readableLabel(agent.latest_task.status)}
                </Pill>
              }
            />
          ))}
        </Panel>
      </div>
    </Page>
  )
}
export function FounderCases() {
  const ops = useOperations()
  const { run, busy } = useApp()
  const cases = ops?.cases.filter((x) => x.kind === "business") || []
  const [selected, setSelected] = useState(cases[0]?.id || "")
  const [detail, setDetail] = useState<Case | null>(null)
  const [note, setNote] = useState("")
  useEffect(() => {
    if (selected)
      api
        .getCase(selected)
        .then(setDetail)
        .catch(() => setDetail(null))
  }, [selected, cases.length])
  async function decide(action: string) {
    const result = await run(
      () => api.decideCase(selected, action, note),
      "Case decision recorded.",
      action === "widen_match" ? "plan" : undefined
    )
    if (result) {
      setDetail(await api.getCase(selected))
      setNote("")
    }
  }
  return (
    <Page
      eyebrow="SERVICE EXCEPTIONS"
      title="Resolve what needs a person."
      subtitle="Review the trigger, diagnosis, and evidence before deciding how a business exception proceeds."
    >
      <div className="board teacher-grid">
        <Panel title="Exception queue">
          {cases.map((item) => (
            <button
              className={`select-row ${item.id === selected ? "active" : ""}`}
              key={item.id}
              onClick={() => {
                setSelected(item.id)
                setNote("")
              }}
            >
              <strong>{displayText(item.subject)}</strong>
              <small>{displayText(item.trigger)}</small>
              <Pill tone={item.status === "resolved" ? "good" : "warn"}>
                {governanceLabel(item.status)}
              </Pill>
            </button>
          ))}
        </Panel>
        <Panel title="Case evidence">
          {detail ? (
            <>
              <Pill tone={detail.status === "resolved" ? "good" : "warn"}>
                {governanceLabel(detail.status)}
              </Pill>
              <h3>{displayText(detail.subject)}</h3>
              <Details value={detail.diagnosis} />
              <div className="visual-panel short">
                <AIVisual variant="path" />
              </div>
              <h3>Evidence</h3>
              {detail.evidence.map((item, index) => (
                <section key={`${item.ref}-${index}`}>
                  <h4>Evidence {index + 1}</h4>
                  <Details value={item.summary} />
                </section>
              ))}
              {detail.status !== "decided" && detail.status !== "resolved" && (
                <>
                  <label className="field-label">
                    Decision note
                    <Textarea
                      rows={4}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="Record the reason and next action"
                    />
                  </label>
                  <div className="button-row">
                    {detail.available_actions?.includes("widen_match") && (
                      <Button
                        className="action primary"
                        disabled={busy || !note.trim()}
                        onClick={() => decide("widen_match")}
                      >
                        Widen teacher match
                      </Button>
                    )}
                    <Button
                      className="action primary"
                      disabled={busy || !note.trim()}
                      onClick={() => decide("approve_resolution")}
                    >
                      Approve resolution
                    </Button>
                    <Button
                      className="action secondary"
                      disabled={busy || !note.trim()}
                      onClick={() => decide("request_followup")}
                    >
                      Request follow-up
                    </Button>
                  </div>
                </>
              )}
            </>
          ) : (
            <Empty>Select an exception.</Empty>
          )}
        </Panel>
      </div>
    </Page>
  )
}
export function FounderIncidents() {
  const ops = useOperations()
  const { runAI, busy } = useApp()
  const incidents = ops?.cases.filter((x) => x.kind === "technical") || []
  const [selected, setSelected] = useState(
    incidents.find((x) => x.status !== "resolved")?.id || incidents[0]?.id || ""
  )
  const [detail, setDetail] = useState<Case | null>(null)
  const [note, setNote] = useState("")
  useEffect(() => {
    if (selected)
      api
        .getCase(selected)
        .then(setDetail)
        .catch(() => setDetail(null))
  }, [selected, incidents.length])
  return (
    <Page
      eyebrow="TECHNICAL INCIDENTS"
      title="Diagnose, then recover with control."
      subtitle="Critical recovery waits for a Founder decision. Approval, execution, and verification are separate states."
    >
      <div className="board teacher-grid">
        <Panel title="Incident queue">
          {incidents.map((item) => (
            <button
              className={`select-row ${item.id === selected ? "active" : ""}`}
              key={item.id}
              onClick={() => setSelected(item.id)}
            >
              <strong>{displayText(item.subject)}</strong>
              <small>{displayText(item.trigger)}</small>
              <Pill tone={item.status === "resolved" ? "good" : "warn"}>
                {governanceLabel(item.status)}
              </Pill>
            </button>
          ))}
        </Panel>
        <div className="stack">
          <Panel title="Diagnosis">
            {detail ? (
              <>
                <Pill tone={detail.status === "resolved" ? "good" : "warn"}>
                  {governanceLabel(detail.status)}
                </Pill>
                <h3>{displayText(detail.subject)}</h3>
                <Details value={detail.diagnosis} />
                <div className="visual-panel short">
                  <AIVisual variant="scan" />
                </div>
                <h3>Evidence</h3>
                {detail.evidence.map((item, index) => (
                  <section key={`${item.ref}-${index}`}>
                    <h4>Evidence {index + 1}</h4>
                    <Details value={item.summary} />
                  </section>
                ))}
              </>
            ) : (
              <Empty />
            )}
          </Panel>
          <Panel title="Recovery path">
            <div className="recovery-steps">
              <span>01 · Diagnose</span>
              <span>02 · Approve</span>
              <span>03 · Execute</span>
              <span>04 · Verify</span>
            </div>
            <p>
              {detail?.verification
                ? displayText(detail.verification)
                : "Any controlled recovery must be approved and verified before closure."}
            </p>
            {detail?.proposal_id && (
              <Link className="action primary" to="/f4">
                Review recovery proposal <ArrowRight size={15} />
              </Link>
            )}
            <label className="field-label">
              Correction request note
              <Textarea
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Explain the correction needed"
              />
            </label>
            <AIButton
              pendingLabel="Processing…"
              className="action secondary"
              disabled={busy || !note.trim()}
              onClick={() =>
                runAI(
                  "correction",
                  () =>
                    api.decideAgent("technical", "request_correction", note),
                  "Correction requested and audited."
                )
              }
            >
              Request correction
            </AIButton>
          </Panel>
        </div>
      </div>
    </Page>
  )
}
export function FounderApprovals() {
  const ops = useOperations()
  const { run, busy } = useApp()
  const proposals = ops?.proposals || []
  const [selected, setSelected] = useState(proposals[0]?.id || "")
  const [detail, setDetail] = useState<Proposal | null>(null)
  const [note, setNote] = useState("")
  useEffect(() => {
    if (selected)
      api
        .getProposal(selected)
        .then(setDetail)
        .catch(() => setDetail(null))
  }, [selected, proposals.length])
  async function decide(action: "approve" | "reject") {
    const result = await run(
      () => api.decideProposal(selected, action, note),
      "Decision recorded in the audit log."
    )
    if (result) {
      setDetail(await api.getProposal(selected))
      setNote("")
    }
  }
  return (
    <Page
      eyebrow="APPROVALS & AUDIT"
      title="Every change has a decision trail."
      subtitle="Compare the proposed change, validation plan, and rollback before approval."
    >
      <div className="board teacher-grid">
        <Panel title="Proposal queue">
          {proposals.map((item) => (
            <button
              className={`select-row ${item.id === selected ? "active" : ""}`}
              key={item.id}
              onClick={() => {
                setSelected(item.id)
                setNote("")
              }}
            >
              <strong>{displayText(item.title)}</strong>
              <small>{governanceLabel(item.type)}</small>
              <Pill tone={item.status === "pending" ? "warn" : "good"}>
                {governanceLabel(item.status)}
              </Pill>
            </button>
          ))}
        </Panel>
        <div className="stack">
          <Panel title="Proposal detail">
            {detail ? (
              <>
                <Pill tone={detail.status === "pending" ? "warn" : "good"}>
                  {governanceLabel(detail.status)}
                </Pill>
                <h3>{displayText(detail.title)}</h3>
                <div className="compare">
                  <div>
                    <small>Before</small>
                    <Details value={detail.before} />
                  </div>
                  <div>
                    <small>After</small>
                    <Details value={detail.after} />
                  </div>
                </div>
                <section>
                  <h4>Evidence</h4>
                  {detail.evidence.length ? (
                    detail.evidence.map((evidence, index) => (
                      <Details
                        key={index}
                        value={evidence}
                        references={[
                          ...(ops?.cases.map((item) => ({
                            id: item.id,
                            label: item.subject,
                          })) || []),
                          {
                            id: evidence,
                            label: `Supporting record ${index + 1}`,
                          },
                        ]}
                      />
                    ))
                  ) : (
                    <p>No supporting evidence provided.</p>
                  )}
                </section>
                <section>
                  <h4>Validation</h4>
                  <Details value={detail.validation} />
                </section>
                <section>
                  <h4>Rollback</h4>
                  <Details value={detail.rollback} />
                </section>
                <p>
                  Execution: {governanceLabel(detail.execution.status)}.
                  Approval does not itself verify a recovery.
                </p>
                {detail.status === "pending" && (
                  <>
                    <label className="field-label">
                      Decision rationale
                      <Textarea
                        rows={3}
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder="Record your reason"
                      />
                    </label>
                    <div className="button-row">
                      <Button
                        className="action primary"
                        disabled={busy || !note.trim()}
                        onClick={() => decide("approve")}
                      >
                        Approve proposal <ShieldCheck size={15} />
                      </Button>
                      <Button
                        className="action secondary"
                        disabled={busy || !note.trim()}
                        onClick={() => decide("reject")}
                      >
                        Reject
                      </Button>
                    </div>
                  </>
                )}
              </>
            ) : (
              <Empty>Select a proposal.</Empty>
            )}
          </Panel>
          <Panel title="Audit trail">
            {ops?.audit.map((entry) => (
              <Row
                key={entry.id}
                title={governanceLabel(entry.action)}
                detail={displayText(
                  [
                    proposals.find((item) => item.id === entry.subject_id)
                      ?.title ||
                      ops.cases.find((item) => item.id === entry.subject_id)
                        ?.subject,
                    time(entry.time),
                    entry.actor_name,
                    entry.result,
                  ]
                    .filter(Boolean)
                    .join(" · "),
                  [
                    ...proposals.map((item) => ({
                      id: item.id,
                      label: item.title,
                    })),
                    ...ops.cases.map((item) => ({
                      id: item.id,
                      label: item.subject,
                    })),
                  ]
                )}
              />
            ))}
          </Panel>
        </div>
      </div>
    </Page>
  )
}
