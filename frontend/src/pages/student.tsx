import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router"
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  ChartNoAxesCombined,
  Check,
  ClipboardCheck,
  Clock3,
  MessageSquareText,
  Plus,
  RefreshCw,
  Sparkles,
  Target,
} from "lucide-react"
import { AssessmentAnswers } from "@/components/assessment-answers"
import { api } from "@/api/client"
import { useApp } from "@/app-context"
import type {
  AssessmentSession,
  Interaction,
  Lesson,
  Material,
  RequestEnvelope,
  StudentRecord,
} from "@/api/types"
import {
  AIVisual,
  Empty,
  Metric,
  Page,
  Panel,
  Pill,
  Row,
  Status,
} from "@/components/layout"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

function useStudent() {
  const { user, workspace } = useApp()
  const record = user ? workspace?.students?.[user.id] : undefined
  // A corrected predecessor can remain in the API's pending slot after its replacement activates.
  // It is history, not a new revision awaiting approval.
  const student = record && {
    ...record,
    pending_plan:
      record.plan &&
      record.pending_plan &&
      record.pending_plan.version <= record.plan.version
        ? null
        : record.pending_plan,
  }
  return {
    student,
    lessons: workspace?.lessons || [],
    materials: workspace?.materials || [],
    interactions: workspace?.interactions || [],
    user,
  }
}
const date = (value: string) =>
  new Date(value).toLocaleString("en-AU", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Australia/Sydney",
  })
function latestConfirmed(student?: StudentRecord) {
  return student?.assessments.filter((x) => x.status === "confirmed").at(-1)
}
function studentNextStep(
  student: StudentRecord | undefined,
  sessions: AssessmentSession[]
) {
  if (student?.plan?.status === "completed" && !student.pending_plan)
    return {
      href: "/s4",
      label: "View completed plan",
      title: "Your learning plan is complete",
      description:
        "All stages are complete. View your milestones and recorded assessment results.",
    }
  if (
    student?.plan &&
    sessions.some(
      (session) =>
        session.kind === "milestone" && session.status === "in_progress"
    )
  )
    return {
      href: "/s3",
      label: "Continue milestone assessment",
      title: "Your milestone assessment is ready",
      description:
        "Complete the assessment for your current stage. A confirmed result is needed before moving to the next stage.",
    }
  if (student?.plan || student?.pending_plan || latestConfirmed(student))
    return {
      href: "/s4",
      label: "View learning plan",
      title: student?.plan
        ? "Your learning plan is active"
        : student?.pending_plan
          ? "Your plan is awaiting teacher approval"
          : "Your assessment is confirmed",
      description: student?.plan
        ? "Follow your approved stages and lesson schedule."
        : student?.pending_plan
          ? "Your teacher must approve the draft before your learning stages and lessons become active."
          : "Check your plan status and any next action. A plan becomes active after teacher approval.",
    }
  if (!student?.profile.goal_text)
    return {
      href: "/s2",
      label: "Set learning goal",
      title: "Set your learning goal",
      description:
        "Describe your needs and confirm your goal before starting an assessment.",
    }
  if (
    sessions.some((session) =>
      ["awaiting_review", "pending_review"].includes(session.status)
    ) ||
    student.assessments.some(
      (assessment) => assessment.status === "pending_review"
    )
  )
    return {
      href: "/s3",
      label: "View assessment status",
      title: "Your assessment is awaiting teacher review",
      description:
        "Your answers are saved. Your teacher will confirm the result before it becomes your current level.",
    }
  if (sessions.some((session) => session.status === "in_progress"))
    return {
      href: "/s3",
      label: "Continue assessment",
      title: "Continue your placement assessment",
      description:
        "Your submitted answers are saved. Open Assessments to continue your existing session.",
    }
  return {
    href: "/s3",
    label: "Start placement assessment",
    title: "Your learning goal is saved",
    description:
      "Next, complete your placement assessment. Your confirmed result will be used to prepare a plan for teacher approval.",
  }
}
function MaterialButton({ material }: { material: Material }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<Material | null>(null)
  const { run } = useApp()
  return (
    <div className="material-item">
      <button
        onClick={async () => {
          if (open) return setOpen(false)
          const result = await run(() => api.getMaterial(material.id))
          if (result) {
            setDetail(result)
            setOpen(true)
          }
        }}
      >
        <BookOpen size={16} />
        <span>
          <strong>{material.title}</strong>
          <small>{material.locator}</small>
        </span>
        <ArrowRight size={15} />
      </button>
      {open && detail && <p>{detail.content}</p>}
    </div>
  )
}
export function StudentOverview() {
  const { student, lessons, materials, user } = useStudent()
  const [quickOpen, setQuickOpen] = useState(false)
  const [quickView, setQuickView] = useState<"details" | "materials">("details")
  const next = lessons.find((x) => x.status === "confirmed") || lessons.at(-1)
  const plan = student?.plan
  const confirmed = latestConfirmed(student)
  const { workspace } = useApp()
  const nextStep = studentNextStep(
    student,
    workspace?.assessment_sessions || []
  )
  return (
    <Page
      eyebrow="PERSONALISED LEARNING · HUMAN GUIDANCE"
      title={`Welcome back, ${user?.name.split(" ")[0] || "learner"}.`}
      subtitle="Your next lesson, your next step, your longer-term goal."
      action={
        <Link className="action secondary" to="/s2">
          Edit learning goal <ArrowRight size={15} />
        </Link>
      }
    >
      <div className="metric-grid">
        <Metric
          label="Current level"
          value={
            confirmed?.level ||
            (student?.assessments.some(
              (assessment) => assessment.status === "pending_review"
            )
              ? "Pending review"
              : "Not assessed")
          }
          note={
            confirmed
              ? "Confirmed assessment result"
              : student?.profile.self_level
                ? `Self-assessed: ${student.profile.self_level}. Awaiting confirmed assessment.`
                : "Complete an assessment to confirm your level"
          }
          icon={Target}
        />
        <Metric
          label="Learning stage"
          value={
            plan
              ? plan.status === "completed"
                ? "Completed"
                : `${plan.stage_index + 1}/${plan.stages.length}`
              : "Not started"
          }
          note={
            plan?.stages[plan.stage_index]?.title ||
            (student?.pending_plan
              ? "Awaiting plan approval"
              : "Available after plan approval")
          }
          icon={ChartNoAxesCombined}
        />
        <Metric
          label="Upcoming lessons"
          value={lessons.filter((x) => x.status === "confirmed").length}
          note="Confirmed sessions"
          icon={CalendarDays}
        />
        <Metric
          label="Weekly commitment"
          value={`${student?.profile.weekly_hours || 0} hours`}
          note="From your learning goal"
          icon={Clock3}
        />
      </div>
      {!plan && student?.profile.goal_text && (
        <section
          className="notice-strip onboarding-notice"
          aria-label="Your next step"
        >
          <ClipboardCheck size={17} />
          <div>
            <strong>{nextStep.title}</strong>
            <p>{nextStep.description}</p>
          </div>
          <Link className="action primary" to={nextStep.href}>
            {nextStep.label} <ArrowRight size={15} />
          </Link>
        </section>
      )}
      {student?.pending_plan && (
        <div className="notice-strip">
          <ClipboardCheck size={17} />
          Plan version {student.pending_plan.version} is with your teacher.
          {plan
            ? " Your current plan stays active until approval."
            : " It will activate after approval."}
          <Pill tone="warn">Pending review</Pill>
        </div>
      )}
      <div className="board two-thirds">
        <Panel className="hero-panel">
          <div className="hero-content">
            <span className="eyebrow">
              {next || plan ? "YOUR NEXT LESSON" : "YOUR NEXT STEP"}
            </span>
            <Pill tone="good">{next?.status || "No lesson"}</Pill>
            <h2>
              {next?.title ||
                (plan ? "Your learning journey starts here" : nextStep.title)}
            </h2>
            <p>
              {next
                ? `${next.teacher.name} · ${date(next.starts_at)}`
                : plan
                  ? "Your first lesson will appear when a time is confirmed."
                  : nextStep.description}
            </p>
            <div className="hero-actions">
              <Link
                className="action primary"
                to={next ? "/s5" : nextStep.href}
              >
                {next ? "View lesson" : nextStep.label} <ArrowRight size={15} />
              </Link>
              <Link className="action secondary" to="/s6">
                Ask assistant
              </Link>
              {next && (
                <button
                  className="action secondary lesson-plus"
                  type="button"
                  aria-label={
                    quickOpen ? "Close lesson actions" : "Expand lesson actions"
                  }
                  aria-expanded={quickOpen}
                  aria-controls="overview-lesson-actions"
                  onClick={() => setQuickOpen((open) => !open)}
                >
                  <Plus size={19} />
                </button>
              )}
            </div>
            {next && quickOpen && (
              <section
                id="overview-lesson-actions"
                className="overview-lesson-actions"
                aria-label="Lesson quick actions"
              >
                <div className="quick-action-row">
                  <button
                    className="choice"
                    aria-pressed={quickView === "details"}
                    onClick={() => setQuickView("details")}
                  >
                    Details
                  </button>
                  <button
                    className="choice"
                    aria-pressed={quickView === "materials"}
                    onClick={() => setQuickView("materials")}
                  >
                    Materials
                  </button>
                  {next.status === "confirmed" && (
                    <Link className="action secondary" to="/s5">
                      Change time <ArrowRight size={14} />
                    </Link>
                  )}
                </div>
                {quickView === "details" ? (
                  <div className="quick-action-content">
                    <strong>{next.title}</strong>
                    <p>
                      {date(next.starts_at)} – {date(next.ends_at)} (Sydney
                      time)
                    </p>
                    <p>Teacher: {next.teacher.name}</p>
                    {next.feedback && <p>{next.feedback}</p>}
                  </div>
                ) : (
                  <div className="quick-action-content">
                    <strong>Approved materials</strong>
                    {materials.some((material) =>
                      next.material_ids.includes(material.id)
                    ) ? (
                      materials
                        .filter((material) =>
                          next.material_ids.includes(material.id)
                        )
                        .map((material) => (
                          <MaterialButton
                            key={material.id}
                            material={material}
                          />
                        ))
                    ) : (
                      <p>No approved materials for this lesson yet.</p>
                    )}
                  </div>
                )}
              </section>
            )}
          </div>
          <AIVisual />
        </Panel>
        <Panel title="Your learning path" className="overview-path">
          <p className="muted">
            {student?.profile.goal_summary || "Set your goal"}
          </p>
          {plan ? (
            <>
              <div className="path-stage-list" aria-label="Learning stages">
                {plan.stages.map((stage, i) => (
                  <details
                    key={`${plan.id}:${i}`}
                    className={`path-stage ${stage.status}`}
                    open={stage.status === "current"}
                  >
                    <summary>
                      <span className="path-stage-number" aria-hidden="true">
                        {stage.status === "completed" ? (
                          <Check size={14} />
                        ) : (
                          String(i + 1).padStart(2, "0")
                        )}
                      </span>
                      <span className="path-stage-title">
                        {stage.title}
                        <small>
                          {stage.status === "current"
                            ? "Current stage"
                            : stage.status === "completed"
                              ? "Completed"
                              : "Upcoming"}{" "}
                          · Weeks {stage.start_week}–{stage.end_week}
                        </small>
                      </span>
                      <span className="path-stage-toggle" aria-hidden="true" />
                    </summary>
                    <div className="path-stage-detail">
                      {stage.topics.length > 0 && (
                        <p>{stage.topics.join(" · ")}</p>
                      )}
                      <p>Milestone: {stage.milestone}</p>
                    </div>
                  </details>
                ))}
              </div>
              <p className="path-progress-note">
                {plan.status === "completed"
                  ? `All ${plan.stages.length} stages completed`
                  : `Stage ${plan.stage_index + 1} of ${plan.stages.length}`}
              </p>
              <div className="key-values">
                <span>
                  Your teacher<strong>{plan.teacher.name}</strong>
                </span>
                <span>
                  Weekly time<strong>{plan.weekly_hours} hours</strong>
                </span>
              </div>
            </>
          ) : (
            <>
              <Pill tone="info">
                {student?.pending_plan
                  ? "Plan awaiting approval"
                  : "No active plan yet"}
              </Pill>
              <p>{nextStep.description}</p>
              <div className="key-values">
                <span>
                  Your teacher<strong>Not assigned yet</strong>
                </span>
                <span>
                  Planned weekly time<strong>Not active yet</strong>
                </span>
              </div>
            </>
          )}
          <Link className="action secondary" to="/s4">
            View learning plan <ArrowRight size={15} />
          </Link>
        </Panel>
        <Panel title="Recent feedback">
          <p>
            {lessons.filter((x) => x.feedback).at(-1)?.feedback ||
              confirmed?.review_note ||
              confirmed?.feedback ||
              "No feedback yet."}
          </p>
          <Link className="text-link" to="/s8">
            View learning record <ArrowRight size={14} />
          </Link>
        </Panel>
        <Panel title="Your next steps">
          {!plan ? (
            <Row
              title={nextStep.title}
              detail={nextStep.description}
              right={
                <Link className="text-link" to={nextStep.href}>
                  {nextStep.label} →
                </Link>
              }
            />
          ) : materials.length === 0 ? (
            <>
              <Row
                title="Follow your active plan"
                detail={plan.stages[plan.stage_index]?.title || "Current stage"}
                right={
                  <Link className="text-link" to="/s4">
                    View →
                  </Link>
                }
              />
              <Row
                title="Ask the learning assistant"
                detail="Personalised support for your current stage"
                right={
                  <Link className="text-link" to="/s6">
                    Ask →
                  </Link>
                }
              />
              <Row
                title="Check lesson schedule"
                detail="Your teacher will confirm a time"
                right={
                  <Link className="text-link" to="/s5">
                    View →
                  </Link>
                }
              />
            </>
          ) : (
            <>
              <Row
                title="Read the argument guide"
                detail="Approved lesson material"
                right={
                  <Link className="text-link" to="/s5">
                    Read →
                  </Link>
                }
              />
              <Row
                title="Stage assessment"
                detail="Milestone review when ready"
                right={
                  <Link className="text-link" to="/s3">
                    Start →
                  </Link>
                }
              />
              <Row
                title="Evidence-linking practice"
                detail="Light practice · instant feedback"
                right={
                  <Link className="text-link" to="/s6">
                    Practice →
                  </Link>
                }
              />
            </>
          )}
        </Panel>
      </div>
    </Page>
  )
}
export function StudentGoal() {
  const { student } = useStudent()
  const { run, busy, workspace } = useApp()
  const nextStep = studentNextStep(
    student,
    workspace?.assessment_sessions || []
  )
  const [goal, setGoal] = useState(student?.profile.goal_text || "")
  const [skills, setSkills] = useState(student?.profile.focus_skills || [])
  const [hours, setHours] = useState(student?.profile.weekly_hours || 3)
  const [selfLevel, setSelfLevel] = useState(student?.profile.self_level || "")
  const [targetLevel, setTargetLevel] = useState(
    student?.profile.target_level || "B2"
  )
  const [summary, setSummary] = useState("")
  // The Coordinator may ask a follow-up question first (UC01 3a); the answer goes back to the same request.
  const [question, setQuestion] = useState<{ id: string; text: string } | null>(
    null
  )
  const [answer, setAnswer] = useState("")
  function show(envelope: RequestEnvelope) {
    if (
      envelope.status === "awaiting_confirmation" &&
      envelope.phase === "follow_up_question"
    ) {
      setQuestion({ id: envelope.id, text: String(envelope.result.question) })
      setSummary("")
    } else {
      setQuestion(null)
      setSummary(String(envelope.result.summary || goal.slice(0, 90)))
    }
  }
  async function organise() {
    if (!goal.trim()) return
    const result = await run(() =>
      api.request("collect_goal", { goal_text: goal, focus_skills: skills })
    )
    if (result) show(result)
  }
  async function reply() {
    if (!question || !answer.trim()) return
    const result = await run(() =>
      api.request("collect_goal", { answer }, undefined, question.id)
    )
    if (result) {
      setAnswer("")
      show(result)
    }
  }
  async function confirm() {
    const result = await run(
      () =>
        api.request("confirm_goal", {
          goal_text: goal,
          goal_summary: summary,
          focus_skills: skills,
          weekly_hours: hours,
          self_level: selfLevel,
          target_level: targetLevel,
        }),
      "Learning goal saved."
    )
    if (result?.status === "completed") setSummary("")
  }
  return (
    <Page
      eyebrow="LEARNING PROFILE"
      title="Make your goal clear."
      subtitle="Tell the Coordinator what you want to achieve. Your teacher can use this profile when reviewing your plan."
    >
      {student?.profile.goal_text && !student.plan && (
        <section
          className="notice-strip onboarding-notice"
          aria-label="Next step for your saved profile"
        >
          <div>
            <strong>{nextStep.title}</strong>
            <p>{nextStep.description}</p>
          </div>
          <Link className="action primary" to={nextStep.href}>
            {nextStep.label} <ArrowRight size={15} />
          </Link>
        </section>
      )}
      <div className="board two">
        <Panel title="Your learning direction">
          <label className="field-label">
            What are you learning English for?
            <Textarea
              value={goal}
              onChange={(e) => {
                setGoal(e.target.value)
                setSummary("")
                setQuestion(null)
              }}
              rows={6}
              placeholder="Describe your goal and needs"
            />
          </label>
          <span className="field-label">Focus skills</span>
          <div className="choice-row">
            {["Reading", "Writing", "Speaking", "Listening"].map((skill) => (
              <button
                key={skill}
                className={`choice ${skills.includes(skill) ? "active" : ""}`}
                onClick={() => {
                  setSkills(
                    skills.includes(skill)
                      ? skills.filter((x) => x !== skill)
                      : [...skills, skill]
                  )
                  setSummary("")
                }}
              >
                {skill}
              </button>
            ))}
          </div>
          <div className="level-fields">
            <label className="field-label">
              Current level (self-assessed)
              <select
                value={selfLevel}
                onChange={(e) => setSelfLevel(e.target.value)}
              >
                <option value="">Not sure yet</option>
                {["A1", "A2", "B1", "B2", "C1", "C2"].map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-label">
              Target level
              <select
                value={targetLevel}
                onChange={(e) => setTargetLevel(e.target.value)}
              >
                {["A1", "A2", "B1", "B2", "C1", "C2"].map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="field-label">
            Hours per week
            <Input
              type="number"
              min={1}
              max={20}
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            />
          </label>
          <div className="button-row">
            <Button
              className="action secondary"
              onClick={organise}
              disabled={busy || !goal.trim()}
            >
              Organise my goal <Sparkles size={15} />
            </Button>
            <Button
              className="action primary"
              disabled={busy || !summary}
              onClick={confirm}
            >
              Confirm goal <Check size={15} />
            </Button>
          </div>
        </Panel>
        <Panel title="Goal summary">
          <div className="visual-panel">
            <AIVisual variant="path" />
          </div>
          {question ? (
            <>
              <Pill tone="warn">The Coordinator needs one more detail</Pill>
              <h3>{question.text}</h3>
              <Textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                rows={3}
                placeholder="Your answer"
              />
              <div className="button-row">
                <Button
                  className="action secondary"
                  onClick={reply}
                  disabled={busy || !answer.trim()}
                >
                  Answer <ArrowRight size={15} />
                </Button>
              </div>
            </>
          ) : summary ? (
            <>
              <Pill tone="info">Ready for your confirmation</Pill>
              <h3>{summary}</h3>
              <p>
                Skills: {skills.join(", ") || "To be discussed"} · {hours} hours
                a week
              </p>
            </>
          ) : (
            <>
              <Pill>Current profile</Pill>
              <h3>
                {student?.profile.goal_summary || "Your goal will appear here"}
              </h3>
              <p>
                Organise your edited goal to see a new summary before confirming
                it.
              </p>
            </>
          )}
        </Panel>
      </div>
    </Page>
  )
}
export function StudentAssessments() {
  const { student, user } = useStudent()
  const { run, busy, workspace, refresh } = useApp()
  const [session, setSession] = useState<AssessmentSession | null>(null)
  const [answer, setAnswer] = useState("")
  const [filter, setFilter] = useState("all")
  const ongoing = workspace?.assessment_sessions || []
  // Keep an already displayed provisional result current after a teacher confirms it elsewhere.
  const sessionId = session?.id
  const awaitingReview =
    session?.status === "awaiting_review" ||
    session?.status === "pending_review"
  useEffect(() => {
    if (!sessionId || !awaitingReview) return
    let active = true
    const update = () => {
      void api
        .getAssessment(sessionId)
        .then((next) => {
          if (active) {
            setSession(next)
            void refresh().catch(() => {})
          }
        })
        .catch(() => {})
    }
    const timer = window.setInterval(update, 5000)
    window.addEventListener("focus", update)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener("focus", update)
    }
  }, [sessionId, awaitingReview, refresh])
  const assessments = useMemo(
    () =>
      [...(student?.assessments || [])]
        .sort(
          (a, b) =>
            (Date.parse(a.created_at) || 0) - (Date.parse(b.created_at) || 0) ||
            a.id.localeCompare(b.id)
        )
        .map((item, index) => ({ ...item, displayNumber: index + 1 }))
        .filter((item) => filter === "all" || item.status === filter),
    [student?.assessments, filter]
  )
  async function start() {
    if (!user) return
    const result = await run(() =>
      api.startAssessment(
        user.id,
        student?.assessments.length ? "milestone" : "initial"
      )
    )
    if (result) {
      setSession(result)
    }
  }
  async function submit() {
    if (!session || !answer.trim()) return
    const result = await run(() =>
      api.answerAssessment(
        session.id,
        session.current_item_id || `item-${session.answered + 1}`,
        answer
      )
    )
    if (result) {
      setSession(result as typeof session)
      setAnswer("")
    }
  }
  return (
    <Page
      eyebrow="ADAPTIVE ASSESSMENT"
      title="Measure what you can do."
      subtitle="Formal results become part of your learning record. Low-confidence results wait for teacher review."
    >
      <div className="board two">
        <Panel title="Current assessment">
          <div className="visual-panel">
            <AIVisual variant="scan" />
          </div>
          {!session ? (
            <>
              <p>
                {student?.profile.goal_text
                  ? "Start a short adaptive check. Your progress is saved after each answer."
                  : "Confirm your learning goal before starting an assessment."}
              </p>
              <div className="button-row">
                <Button
                  className="action primary"
                  onClick={start}
                  disabled={
                    busy || !student?.profile.goal_text || ongoing.length > 0
                  }
                >
                  Start assessment <ArrowRight size={15} />
                </Button>
                {ongoing.map((saved) => (
                  <Button
                    key={saved.id}
                    className="action secondary"
                    disabled={busy}
                    onClick={async () => {
                      const result = await run(() =>
                        api.getAssessment(saved.id)
                      )
                      if (result) {
                        setSession(result)
                        setAnswer("")
                      }
                    }}
                  >
                    Continue{" "}
                    {saved.kind === "directed"
                      ? "teacher-directed"
                      : saved.kind}{" "}
                    assessment
                    {saved.focus ? ` · ${saved.focus}` : ""}
                  </Button>
                ))}
                <Button
                  className="action secondary"
                  disabled={busy}
                  onClick={() => run(refresh)}
                >
                  Refresh assessments
                </Button>
              </div>
            </>
          ) : session.status === "in_progress" ? (
            <>
              <Pill tone="info">
                Question {session.answered + 1} of {session.max_items}
              </Pill>
              <h3>{session.current_item}</h3>
              <Textarea
                rows={5}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="Write your answer"
              />
              <div className="button-row">
                <Button
                  className="action primary"
                  onClick={submit}
                  disabled={busy || !answer.trim()}
                >
                  Submit answer <ArrowRight size={15} />
                </Button>
                <Button
                  className="action secondary"
                  onClick={() => setSession(null)}
                >
                  Pause
                </Button>
              </div>
            </>
          ) : (
            <>
              <Pill tone={session.status === "completed" ? "good" : "warn"}>
                {session.status === "completed"
                  ? "Result confirmed"
                  : awaitingReview
                    ? "Pending teacher review"
                    : session.status.replaceAll("_", " ")}
              </Pill>
              <h3>
                {session.status === "completed"
                  ? "Assessment complete"
                  : "Assessment submitted"}
              </h3>
              <p>
                {session.status === "completed"
                  ? "Your confirmed result is saved in your learning record. Plan approval is a separate step."
                  : awaitingReview
                    ? "Your provisional result is saved. Your teacher will review it before it becomes your current level."
                    : "Refresh to check the latest assessment status."}
              </p>
              <Button
                className="action secondary"
                disabled={busy}
                onClick={async () => {
                  const latest = await run(() => api.getAssessment(session.id))
                  if (latest) setSession(latest)
                }}
              >
                <RefreshCw size={16} aria-hidden="true" />
                Refresh result
              </Button>
            </>
          )}
        </Panel>
        <Panel
          title="Assessment records"
          action={
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Filter assessments"
            >
              <option value="all">All records</option>
              <option value="confirmed">Confirmed</option>
              <option value="pending_review">Pending review</option>
            </select>
          }
        >
          {assessments.length ? (
            assessments.map((item) => (
              <div className="record-card" key={item.id}>
                <div>
                  <strong>
                    Assessment {item.displayNumber} ·{" "}
                    {item.kind === "initial"
                      ? "Initial"
                      : item.kind === "milestone"
                        ? "Milestone"
                        : item.kind === "directed"
                          ? "Teacher-directed"
                          : item.kind.replaceAll("_", " ")}
                  </strong>
                  <Pill tone={item.status === "confirmed" ? "good" : "warn"}>
                    {item.status.replace("_", " ")}
                  </Pill>
                </div>
                <p>
                  Level {item.level} · Confidence{" "}
                  {Math.round(item.confidence * 100)}%
                </p>
                <small>{item.feedback}</small>
                <AssessmentAnswers key={item.id} assessmentId={item.id} />
              </div>
            ))
          ) : (
            <Empty>No assessment records in this filter.</Empty>
          )}
        </Panel>
      </div>
    </Page>
  )
}
export function StudentPlan() {
  const { student } = useStudent()
  const { run, busy } = useApp()
  const [reason, setReason] = useState("")
  const plan = student?.plan
  const displayPlan = plan || student?.pending_plan
  const pending = student?.pending_plan
  const [withdrawId, setWithdrawId] = useState<string | null>(null)
  return (
    <Page
      eyebrow="PERSONALISED PLAN"
      title="A path shaped around your goal."
      subtitle={
        plan?.status === "completed"
          ? "Your completed stages and milestones remain available in your learning record."
          : "The current plan remains active while any major revision awaits teacher approval."
      }
    >
      <div className="board two-thirds">
        <Panel
          title={
            displayPlan
              ? `Learning plan · Version ${displayPlan.version}`
              : "Learning plan"
          }
        >
          {displayPlan ? (
            <>
              <div className="notice-strip">
                <Pill tone={plan ? "good" : "warn"}>
                  {plan
                    ? plan.status === "completed"
                      ? "Completed"
                      : "Active"
                    : "Pending review"}
                </Pill>
                <span>{displayPlan.reason}</span>
              </div>
              <div className="stages">
                {displayPlan.stages.map((stage, i) => (
                  <details
                    open={
                      stage.status === "current" ||
                      i === displayPlan.stage_index
                    }
                    className={`stage-card ${stage.status === "current" ? "current" : ""}`}
                    key={stage.title}
                  >
                    <summary>
                      <span>
                        {String(i + 1).padStart(2, "0")} · {stage.title}
                      </span>
                      <Pill
                        tone={
                          stage.status === "completed"
                            ? "good"
                            : i === displayPlan.stage_index
                              ? "info"
                              : "neutral"
                        }
                      >
                        {stage.status}
                      </Pill>
                    </summary>
                    <div className="stage-body">
                      <small>
                        Weeks {stage.start_week}–{stage.end_week} ·{" "}
                        {stage.topics.join(" · ")}
                      </small>
                      <p>Milestone: {stage.milestone}</p>
                      {stage.target_level && (
                        <p>Milestone target: {stage.target_level}</p>
                      )}
                      {stage.status === "current" && (
                        <p>
                          Complete all lessons with recorded attendance, then
                          pass the confirmed milestone assessment to advance.
                        </p>
                      )}
                      {stage.milestone_status &&
                        stage.status !== "completed" &&
                        stage.milestone_status !== "lessons_pending" && (
                          <p>
                            Milestone assessment:{" "}
                            {(
                              {
                                queued: "Preparing assessment",
                                running: "Preparing assessment",
                                awaiting_input:
                                  "Ready to continue in Assessments",
                                escalated: "Awaiting teacher review",
                                awaiting_approval: "Awaiting teacher review",
                                completed: "Result recorded",
                                failed: "Start a new attempt in Assessments",
                                ready: "Ready to start in Assessments",
                              } as Record<string, string>
                            )[stage.milestone_status] || "In progress"}
                            .
                          </p>
                        )}
                    </div>
                  </details>
                ))}
              </div>
            </>
          ) : (
            <Empty>
              Your plan will appear after assessment and teacher approval.
            </Empty>
          )}
        </Panel>
        <div className="stack">
          <Panel title="Plan status">
            <AIVisual variant="path" />
            <p>
              {student?.pending_plan
                ? `Version ${student.pending_plan.version} is pending teacher review.`
                : plan
                  ? plan.status === "completed"
                    ? "Your learning plan is complete."
                    : "Your approved plan is active."
                  : "Complete your goal and assessment. Your teacher will review the first plan."}
            </p>
            {plan?.progress_message && (
              <p role="status">{plan.progress_message}</p>
            )}
            <div className="key-values">
              <span>
                Teacher<strong>{displayPlan?.teacher.name || "—"}</strong>
              </span>
              <span>
                Weekly hours<strong>{displayPlan?.weekly_hours || 0}</strong>
              </span>
            </div>
          </Panel>
          {plan && pending ? (
            <Panel title="Your change request">
              <Pill tone="warn">
                Awaiting teacher review · Version {pending.version}
              </Pill>
              <p>
                Version {plan.version} remains active. You can submit another
                request after this review
                {pending.revision_request?.can_withdraw
                  ? " or withdraw your request below"
                  : ""}
                .
              </p>
              <h3>Requested change</h3>
              <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {pending.revision_request?.reason ||
                  "Your teacher is reviewing this proposed update. See the proposed plan below."}
              </p>
              {pending.revision_request?.submitted_at && (
                <p>
                  Submitted{" "}
                  {new Date(
                    pending.revision_request.submitted_at
                  ).toLocaleString()}
                </p>
              )}
              <details>
                <summary>
                  View proposed plan · Version {pending.version}
                </summary>
                <p>Proposed weekly hours: {pending.weekly_hours}</p>
                <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                  {pending.reason}
                </p>
                {pending.stages.map((stage, index) => (
                  <div className="record-card" key={index}>
                    <strong>
                      {index + 1}. {stage.title}
                    </strong>
                    <p>
                      Weeks {stage.start_week}–{stage.end_week} ·{" "}
                      {stage.topics.join(" · ")}
                    </p>
                    <p>Milestone: {stage.milestone}</p>
                  </div>
                ))}
              </details>
              {pending.revision_request?.can_withdraw &&
                (withdrawId === pending.id ? (
                  <div>
                    <p>
                      Withdraw this request? Your current plan will stay active.
                    </p>
                    <div className="button-row">
                      <Button
                        className="action secondary"
                        disabled={busy}
                        onClick={() => setWithdrawId(null)}
                      >
                        Keep request
                      </Button>
                      <Button
                        className="action primary"
                        disabled={busy}
                        onClick={async () => {
                          const result = await run(
                            () => api.withdrawPlanRevision(pending.id),
                            "Request withdrawn. Your current plan is unchanged."
                          )
                          if (result) {
                            setWithdrawId(null)
                            setReason("")
                          }
                        }}
                      >
                        Confirm withdrawal
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Button
                    className="action secondary"
                    disabled={busy}
                    onClick={() => setWithdrawId(pending.id)}
                  >
                    Withdraw request
                  </Button>
                ))}
            </Panel>
          ) : plan?.status === "active" ? (
            <Panel title="Request a change">
              <p>
                Tell your teacher what needs adjusting. Approval is required
                before a new plan becomes active.
              </p>
              <Textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={4}
                placeholder="What changed, and why?"
              />
              <Button
                className="action primary"
                disabled={busy || !reason.trim() || !!student?.pending_plan}
                onClick={async () => {
                  const result = await run(
                    () => api.request("revise_plan", { reason }),
                    "Revision sent for teacher review."
                  )
                  if (result) setReason("")
                }}
              >
                Request revision <ArrowRight size={15} />
              </Button>
            </Panel>
          ) : plan?.status === "completed" ? (
            <Panel title="Plan completed">
              <p>
                All stages and their milestone assessments are complete. Your
                results remain in your learning record.
              </p>
              <Link className="action secondary" to="/s7">
                View learning record
              </Link>
            </Panel>
          ) : (
            <Panel title="Next step">
              <p>
                {student?.pending_plan
                  ? "The draft plan is waiting for your teacher's decision."
                  : "Confirm your learning goal and complete an assessment. Your teacher will review the result and first plan."}
              </p>
              <Link
                className="action secondary"
                to={student?.profile.goal_text ? "/s3" : "/s2"}
              >
                {student?.profile.goal_text
                  ? "Open assessment"
                  : "Set learning goal"}{" "}
                <ArrowRight size={15} />
              </Link>
            </Panel>
          )}
        </div>
      </div>
    </Page>
  )
}
type CheckedTime = { id: string; starts_at: string; ends_at: string }
type SlotCheck = {
  requestId: string
  slots: CheckedTime[]
  message: string
  requested_available?: boolean
  teacher_availability?: { day: string; start: string; end: string }[]
  teacher_timezone?: string
}
function LessonTimeChange({
  lesson,
  timezone,
}: {
  lesson: Lesson
  timezone: string
}) {
  const { run, busy } = useApp()
  const [slot, setSlot] = useState("")
  const [check, setCheck] = useState<SlotCheck | null>(null)
  const [chosen, setChosen] = useState("")
  const formatTime = (value: string) =>
    new Intl.DateTimeFormat("en-AU", {
      timeZone: timezone,
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(value))
  return (
    <>
      <h3>Change this time</h3>
      <label className="field-label">
        Proposed slot (optional · {timezone})
        <Input
          type="datetime-local"
          value={slot}
          disabled={busy}
          onChange={(e) => {
            setSlot(e.target.value)
            setCheck(null)
            setChosen("")
          }}
        />
      </label>
      <p>
        Leave the time blank and click Check slot to find available times. Your
        lesson stays unchanged until you confirm.
      </p>
      <div className="button-row">
        <Button
          className="action secondary"
          disabled={busy}
          onClick={async () => {
            setCheck(null)
            setChosen("")
            const response = await run(
              () =>
                api.request("reschedule", {
                  lesson_id: lesson.id,
                  ...(slot ? { slot } : {}),
                }),
              "Time check complete. Review the available times below."
            )
            if (response?.status === "awaiting_confirmation") {
              const result = response.result as unknown as Omit<
                SlotCheck,
                "requestId"
              >
              const options = result.slots || []
              setCheck({ ...result, slots: options, requestId: response.id })
              if (result.requested_available && options.length === 1)
                setChosen(options[0].id)
            }
          }}
        >
          Check slot
        </Button>
        <Button
          className="action primary"
          disabled={busy || !check || !chosen}
          onClick={async () => {
            if (!check || !chosen) return
            const response = await run(
              () =>
                api.request("confirm_slot", {
                  lesson_id: lesson.id,
                  slot_request_id: check.requestId,
                  slot_id: chosen,
                }),
              "Lesson time updated."
            )
            // A failed final check requires a fresh availability check; never reuse a stale selection.
            if (!response || response.status === "completed") {
              setCheck(null)
              setChosen("")
            }
          }}
        >
          Confirm time
        </Button>
      </div>
      {check && (
        <section aria-label="Time check result" aria-live="polite">
          <p>{check.message}</p>
          {!!check.teacher_availability?.length && (
            <p>
              Teacher availability ({check.teacher_timezone}):{" "}
              {check.teacher_availability
                .map((w) => `${w.day} ${w.start}–${w.end}`)
                .join("; ")}
            </p>
          )}
          {check.slots.length > 0 && (
            <fieldset>
              <legend>
                {check.requested_available
                  ? "Available time"
                  : "Choose an alternative time"}{" "}
                ({timezone})
              </legend>
              {check.slots.map((option) => (
                <label
                  className="record-card"
                  key={option.id}
                  style={{ display: "flex", alignItems: "center", gap: 12 }}
                >
                  <input
                    type="radio"
                    style={{ width: 18, height: 18, flexShrink: 0, margin: 0 }}
                    name={`lesson-time-${lesson.id}`}
                    value={option.id}
                    checked={chosen === option.id}
                    disabled={busy}
                    onChange={() => setChosen(option.id)}
                  />
                  <span>
                    {formatTime(option.starts_at)} –{" "}
                    {formatTime(option.ends_at)}
                  </span>
                </label>
              ))}
            </fieldset>
          )}
        </section>
      )}
    </>
  )
}

export function StudentLessons() {
  const { lessons, materials, student } = useStudent()
  const [selected, setSelected] = useState(
    lessons.find((x) => x.status === "confirmed")?.id || lessons[0]?.id || ""
  )
  const current = lessons.find((x) => x.id === selected) || lessons[0]
  return (
    <Page
      eyebrow="LESSONS & TIME"
      title="Your lessons, in view."
      subtitle="See your confirmed sessions, open approved resources, and request a specific new time."
    >
      <div className="board two">
        <Panel title="Lesson schedule">
          {lessons.length ? (
            lessons.map((lesson) => (
              <Row
                key={lesson.id}
                title={lesson.title}
                detail={`${date(lesson.starts_at)} · ${lesson.teacher.name}`}
                right={
                  <Pill tone={lesson.status === "completed" ? "good" : "info"}>
                    {lesson.status}
                  </Pill>
                }
                onClick={() => setSelected(lesson.id)}
              />
            ))
          ) : (
            <Empty>No lessons scheduled yet.</Empty>
          )}
          <div className="visual-panel short">
            <AIVisual variant="path" />
          </div>
        </Panel>
        <Panel title={current?.title || "Lesson detail"}>
          {current ? (
            <>
              <Pill tone={current.status === "confirmed" ? "good" : "neutral"}>
                {current.status}
              </Pill>
              <h3>{date(current.starts_at)}</h3>
              <p>Teacher: {current.teacher.name}</p>
              {current.feedback && <blockquote>{current.feedback}</blockquote>}
              <div className="divider" />
              <h3>Approved materials</h3>
              {materials
                .filter((x) => current.material_ids.includes(x.id))
                .map((material) => (
                  <MaterialButton key={material.id} material={material} />
                ))}
              {current.status === "confirmed" && (
                <>
                  <div className="divider" />
                  <LessonTimeChange
                    key={`${current.id}:${current.starts_at}`}
                    lesson={current}
                    timezone={student?.profile.timezone || "Australia/Sydney"}
                  />
                </>
              )}
            </>
          ) : (
            <Empty />
          )}
        </Panel>
      </div>
    </Page>
  )
}
export function StudentAssistant() {
  const { interactions, materials } = useStudent()
  const { run, busy } = useApp()
  const [question, setQuestion] = useState("")
  const [practice, setPractice] = useState("")
  const [practiceAnswer, setPracticeAnswer] = useState("")
  const [feedback, setFeedback] = useState("")
  async function send(resources = false) {
    const result = await run(() =>
      api.request(resources ? "resources" : "explain", {
        question: question || "Find learning resources for my current stage",
      })
    )
    if (result) setQuestion("")
  }
  return (
    <Page
      eyebrow="PERSONALISED LEARNING · HUMAN GUIDANCE"
      title="Learning support, connected."
      subtitle="Ask, explore sources, and practise at your level."
    >
      <div className="board two-thirds">
        <Panel title="A little help, right when you need it">
          <div className="chat-list">
            {interactions.map((item: Interaction) => (
              <div className="chat-pair" key={item.id}>
                <div className="chat-question">{item.question}</div>
                <div className="chat-answer">
                  <small>
                    {item.status === "escalated"
                      ? "Teacher review"
                      : "Teaching Assistant · via Coordinator"}
                  </small>
                  <p>{item.answer}</p>
                  {item.source_refs.map((source) => (
                    <span key={source.material_id} className="source-chip">
                      {source.title} · {source.locator}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="chat-compose">
            <label className="field-label">
              Ask a question
              <Textarea
                rows={3}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Can you explain this in another way?"
              />
            </label>
            <div className="button-row">
              <Button
                className="action secondary"
                disabled={busy}
                onClick={() => send(true)}
              >
                Find resources
              </Button>
              <Button
                className="action primary"
                disabled={busy || !question.trim()}
                onClick={() => send()}
              >
                Send <ArrowRight size={15} />
              </Button>
            </div>
          </div>
        </Panel>
        <Panel title="Sources & practice">
          <AIVisual variant="signal" />
          <div className="source-list">
            {materials.map((material) => (
              <MaterialButton key={material.id} material={material} />
            ))}
          </div>
          <div className="divider" />
          <h3>Practice, just for you</h3>
          {practice ? (
            <>
              <p>{practice}</p>
              <Textarea
                rows={3}
                value={practiceAnswer}
                onChange={(e) => setPracticeAnswer(e.target.value)}
                placeholder="Write a short response"
              />
              <Button
                className="action primary"
                disabled={busy || !practiceAnswer.trim()}
                onClick={async () => {
                  const result = await run(() =>
                    api.request("practice_answer", { answer: practiceAnswer })
                  )
                  if (result) setFeedback(String(result.result.feedback))
                }}
              >
                Check answer
              </Button>
              {feedback && <Status>{feedback}</Status>}
            </>
          ) : (
            <>
              <p>
                Short exercises give feedback and stay separate from formal
                assessment.
              </p>
              <Button
                className="action primary"
                disabled={busy}
                onClick={async () => {
                  const result = await run(() => api.request("practice"))
                  if (result) setPractice(String(result.result.question))
                }}
              >
                Start a short practice <Sparkles size={15} />
              </Button>
            </>
          )}
        </Panel>
      </div>
    </Page>
  )
}
export function StudentRecordPage() {
  const { student, lessons, interactions } = useStudent()
  const records = [
    ...(student?.assessments || []).map((x) => ({
      date: x.created_at,
      title: `${x.kind} assessment`,
      detail: `${x.level} · ${x.status.replace("_", " ")}`,
      tone: x.status === "confirmed" ? "good" : ("warn" as "good" | "warn"),
    })),
    ...lessons
      .filter((x) => x.status === "completed")
      .map((x) => ({
        date: x.starts_at,
        title: x.title,
        detail: x.feedback,
        tone: "good" as const,
      })),
  ].sort((a, b) => b.date.localeCompare(a.date))
  return (
    <Page
      eyebrow="LEARNING RECORD"
      title="See how far you've come."
      subtitle="Milestones are drawn from confirmed assessments, lessons, and learning interactions."
    >
      <div className="metric-grid three">
        <Metric
          label="Confirmed assessments"
          value={
            student?.assessments.filter((x) => x.status === "confirmed")
              .length || 0
          }
          icon={ClipboardCheck}
        />
        <Metric
          label="Completed lessons"
          value={lessons.filter((x) => x.status === "completed").length}
          icon={CalendarDays}
        />
        <Metric
          label="Learning interactions"
          value={interactions.length}
          icon={MessageSquareText}
        />
      </div>
      <div className="board two-thirds">
        <Panel title="Your timeline">
          {records.length ? (
            records.map((record, i) => (
              <div className="timeline-row" key={`${record.title}-${i}`}>
                <span className="timeline-dot" />
                <div>
                  <small>{date(record.date)}</small>
                  <h3>{record.title}</h3>
                  <p>{record.detail}</p>
                </div>
                <Pill tone={record.tone}>
                  {record.tone === "good" ? "Recorded" : "Provisional"}
                </Pill>
              </div>
            ))
          ) : (
            <Empty>Your learning milestones will appear here.</Empty>
          )}
        </Panel>
        <Panel title="Current direction">
          <AIVisual variant="path" />
          <h3>{student?.profile.goal_summary || "Set your learning goal"}</h3>
          <p>Target level: {student?.profile.target_level || "—"}</p>
          <p>
            {student?.plan?.status === "completed"
              ? "All stages completed"
              : `Active stage: ${student?.plan?.stages[student.plan.stage_index]?.title || "Awaiting plan"}`}
          </p>
          <Link className="action secondary" to="/s4">
            View plan <ArrowRight size={15} />
          </Link>
        </Panel>
      </div>
    </Page>
  )
}
