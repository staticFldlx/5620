import { useMemo, useState } from "react"
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
  Sparkles,
  Target,
} from "lucide-react"
import { api } from "@/api/client"
import { useApp } from "@/app-context"
import type {
  Assessment,
  Interaction,
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
  return {
    student: user ? workspace?.students?.[user.id] : undefined,
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
  const next = lessons.find((x) => x.status === "confirmed") || lessons.at(-1)
  const plan = student?.plan
  const confirmed = latestConfirmed(student)
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
          value={confirmed?.level || "—"}
          note={student?.profile.goal_summary}
          icon={Target}
        />
        <Metric
          label="Learning stage"
          value={plan ? `${plan.stage_index + 1}/${plan.stages.length}` : "—"}
          note={plan?.stages[plan.stage_index]?.title || "Awaiting plan"}
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
            <span className="eyebrow">YOUR NEXT LESSON</span>
            <Pill tone="good">{next?.status || "No lesson"}</Pill>
            <h2>{next?.title || "Your learning journey starts here"}</h2>
            <p>
              {next
                ? `${next.teacher.name} · ${date(next.starts_at)}`
                : plan
                  ? "Your first lesson will appear when a time is confirmed."
                  : student?.profile.goal_text
                    ? "Complete assessment and teacher review to build your plan."
                    : "Set a goal to start planning."}
            </p>
            <div className="hero-actions">
              <Link
                className="action primary"
                to={next ? "/s5" : plan ? "/s4" : "/s2"}
              >
                {next
                  ? "View lesson"
                  : plan
                    ? "View learning plan"
                    : "Set learning goal"}{" "}
                <ArrowRight size={15} />
              </Link>
              <Link className="action secondary" to="/s6">
                Ask assistant
              </Link>
            </div>
          </div>
          <AIVisual />
        </Panel>
        <Panel title="Your learning path">
          <p className="muted">
            {student?.profile.goal_summary || "Set your goal"}
          </p>
          <div className="stage-track">
            {plan?.stages.map((stage, i) => (
              <span
                key={stage.title}
                className={i <= plan.stage_index ? "filled" : ""}
              />
            ))}
          </div>
          <p>
            Stage {plan ? plan.stage_index + 1 : 0} of{" "}
            {plan?.stages.length || 0}
          </p>
          <div className="key-values">
            <span>
              Your teacher<strong>{plan?.teacher.name || "—"}</strong>
            </span>
            <span>
              Weekly time<strong>{plan?.weekly_hours || 0} hours</strong>
            </span>
          </div>
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
          {!student?.profile.goal_text ? (
            <Row
              title="Set your learning goal"
              detail="Describe your needs and confirm the summary"
              right={
                <Link className="text-link" to="/s2">
                  Start →
                </Link>
              }
            />
          ) : !confirmed ? (
            <Row
              title="Complete your first assessment"
              detail="Your teacher confirms low-confidence results"
              right={
                <Link className="text-link" to="/s3">
                  Start →
                </Link>
              }
            />
          ) : !plan ? (
            <Row
              title="First plan with your teacher"
              detail={
                student?.pending_plan
                  ? "Pending teacher approval"
                  : "Preparing a plan from your goal and level"
              }
              right={
                <Link className="text-link" to="/s4">
                  View →
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
  const { run, busy } = useApp()
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
  const [assessmentNext, setAssessmentNext] = useState(false)
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
    setAssessmentNext(false)
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
    if (result) setAssessmentNext(result.phase === "initial_assessment_next")
  }
  return (
    <Page
      eyebrow="LEARNING PROFILE"
      title="Make your goal clear."
      subtitle="Tell the Coordinator what you want to achieve. Your teacher can use this profile when reviewing your plan."
    >
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
              Current level
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
              {assessmentNext && (
                <Link className="text-link" to="/s3">
                  Start your placement assessment →
                </Link>
              )}
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
  const { run, busy } = useApp()
  const [session, setSession] = useState<{
    id: string
    current_item: string
    answered: number
    max_items: number
    status: string
  } | null>(null)
  const [answer, setAnswer] = useState("")
  const [filter, setFilter] = useState("all")
  const [pausedId, setPausedId] = useState(() =>
    user ? localStorage.getItem(`lingopath-assessment-${user.id}`) : null
  )
  const assessments = useMemo(
    () =>
      (student?.assessments || []).filter(
        (x) => filter === "all" || x.status === filter
      ),
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
      setPausedId(result.id)
      localStorage.setItem(`lingopath-assessment-${user.id}`, result.id)
    }
  }
  async function submit() {
    if (!session || !answer.trim()) return
    const result = await run(() =>
      api.answerAssessment(session.id, `item-${session.answered + 1}`, answer)
    )
    if (result) {
      setSession(result as typeof session)
      setAnswer("")
      if (result.status !== "in_progress") {
        localStorage.removeItem(`lingopath-assessment-${user?.id}`)
        setPausedId(null)
      }
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
                  disabled={busy || !student?.profile.goal_text}
                >
                  Start assessment <ArrowRight size={15} />
                </Button>
                {pausedId && (
                  <Button
                    className="action secondary"
                    disabled={busy}
                    onClick={async () => {
                      const result = await run(() =>
                        api.getAssessment(pausedId)
                      )
                      if (result) setSession(result as typeof session)
                    }}
                  >
                    Resume saved assessment
                  </Button>
                )}
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
              <Pill tone="warn">Pending teacher review</Pill>
              <h3>Assessment submitted</h3>
              <p>
                Your provisional result is visible below. Your teacher will
                confirm it before it becomes your current level.
              </p>
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
            assessments.map((item: Assessment) => (
              <div className="record-card" key={item.id}>
                <div>
                  <strong>
                    {item.kind} assessment · {item.id}
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
  return (
    <Page
      eyebrow="PERSONALISED PLAN"
      title="A path shaped around your goal."
      subtitle="The current plan remains active while any major revision awaits teacher approval."
    >
      <div className="board two-thirds">
        <Panel
          title={
            displayPlan
              ? `Plan ${displayPlan.id} · version ${displayPlan.version}`
              : "Learning plan"
          }
        >
          {displayPlan ? (
            <>
              <div className="notice-strip">
                <Pill tone={plan ? "good" : "warn"}>
                  {plan ? "Active" : "Pending review"}
                </Pill>
                <span>{displayPlan.reason}</span>
              </div>
              <div className="stages">
                {displayPlan.stages.map((stage, i) => (
                  <div
                    className={`stage-card ${i === displayPlan.stage_index ? "current" : ""}`}
                    key={stage.title}
                  >
                    <span>{String(i + 1).padStart(2, "0")}</span>
                    <div>
                      <h3>{stage.title}</h3>
                      <small>
                        Weeks {stage.start_week}–{stage.end_week} ·{" "}
                        {stage.topics.join(" · ")}
                      </small>
                      <p>Milestone: {stage.milestone}</p>
                    </div>
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
                  </div>
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
                  ? "Your approved plan is active."
                  : "Complete your goal and assessment. Your teacher will review the first plan."}
            </p>
            <div className="key-values">
              <span>
                Teacher<strong>{displayPlan?.teacher.name || "—"}</strong>
              </span>
              <span>
                Weekly hours<strong>{displayPlan?.weekly_hours || 0}</strong>
              </span>
            </div>
          </Panel>
          {plan ? (
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
export function StudentLessons() {
  const { lessons, materials } = useStudent()
  const { run, busy } = useApp()
  const [selected, setSelected] = useState(
    lessons.find((x) => x.status === "confirmed")?.id || lessons[0]?.id || ""
  )
  const [slot, setSlot] = useState("")
  const [proposedSlot, setProposedSlot] = useState("")
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
                  <h3>Change this time</h3>
                  <label className="field-label">
                    Proposed slot
                    <Input
                      type="datetime-local"
                      value={slot}
                      onChange={(e) => {
                        setSlot(e.target.value)
                        setProposedSlot("")
                      }}
                    />
                  </label>
                  <div className="button-row">
                    <Button
                      className="action secondary"
                      disabled={busy || !slot}
                      onClick={async () => {
                        const result = await run(
                          () =>
                            api.request(
                              "reschedule",
                              { lesson_id: current.id, slot },
                              undefined,
                              current.id
                            ),
                          "Proposed time is ready for confirmation."
                        )
                        if (result) setProposedSlot(slot)
                      }}
                    >
                      Check slot
                    </Button>
                    <Button
                      className="action primary"
                      disabled={busy || !slot || proposedSlot !== slot}
                      onClick={() =>
                        run(
                          () =>
                            api.request("confirm_slot", {
                              lesson_id: current.id,
                              slot,
                              starts_at: new Date(slot).toISOString(),
                            }),
                          "Specific lesson time confirmed."
                        )
                      }
                    >
                      Confirm time
                    </Button>
                  </div>
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
            Active stage:{" "}
            {student?.plan?.stages[student.plan.stage_index]?.title ||
              "Awaiting plan"}
          </p>
          <Link className="action secondary" to="/s4">
            View plan <ArrowRight size={15} />
          </Link>
        </Panel>
      </div>
    </Page>
  )
}
