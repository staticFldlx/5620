import { useEffect, useState } from "react"
import { Link } from "react-router"
import {
  ArrowRight,
  CalendarDays,
  ClipboardCheck,
  Sparkles,
  Users,
} from "lucide-react"
import { api } from "@/api/client"
import { useApp } from "@/app-context"
import type {
  Assessment,
  Interaction,
  Material,
  Plan,
  ReviewDetail,
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
const fmt = (value: string) =>
  new Date(value).toLocaleString("en-AU", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Australia/Sydney",
  })
function useTeacher() {
  const { workspace } = useApp()
  return {
    students: workspace?.students || {},
    lessons: workspace?.lessons || [],
    reviews: workspace?.reviews || [],
    materials: workspace?.materials || [],
    availability: workspace?.teacher_availability || [],
  }
}
const displayName = (id: string, student?: StudentRecord) =>
  student?.name ||
  (id === "student-ivy"
    ? "Ivy Lin"
    : id === "student-sophia"
      ? "Sophia Chen"
      : id)
export function TeacherOverview() {
  const { students, lessons, reviews } = useTeacher()
  const next = lessons.find((x) => x.status === "confirmed")
  return (
    <Page
      eyebrow="AI SUPPORT · HUMAN JUDGEMENT"
      title="Good morning, Emily."
      subtitle="Your students, lessons, and decisions in one place."
    >
      <div className="metric-grid three">
        <Metric
          label="My students"
          value={Object.keys(students).length}
          note="Assigned learners"
          icon={Users}
        />
        <Metric
          label="Pending reviews"
          value={reviews.filter((x) => x.status === "pending").length}
          note="Plans, results and questions"
          icon={ClipboardCheck}
        />
        <Metric
          label="Upcoming lessons"
          value={lessons.filter((x) => x.status === "confirmed").length}
          note="Confirmed teaching sessions"
          icon={CalendarDays}
        />
      </div>
      <div className="board two-thirds">
        <Panel className="hero-panel" title="Your next lesson">
          <div className="hero-content">
            <Pill tone="good">Confirmed</Pill>
            <h2>{next?.title || "No upcoming lesson"}</h2>
            <p>
              {next
                ? `${displayName(next.student_id, students[next.student_id])} · ${fmt(next.starts_at)}`
                : "Review your timetable for new bookings."}
            </p>
            <Link className="action primary" to="/t3">
              Open lesson <ArrowRight size={15} />
            </Link>
          </div>
          <AIVisual variant="signal" />
        </Panel>
        <Panel title="Needs your judgement">
          {reviews
            .filter((x) => x.status === "pending")
            .slice(0, 4)
            .map((review) => (
              <Row
                key={review.id}
                title={`${displayName(review.student_id, students[review.student_id])} · ${review.kind}`}
                detail={review.trigger}
                right={<Pill tone="warn">Review</Pill>}
              />
            ))}
          <Link className="action secondary" to="/t4">
            Open review queue <ArrowRight size={15} />
          </Link>
        </Panel>
        <Panel title="My students">
          {Object.entries(students).map(([id, student]) => (
            <Row
              key={id}
              title={displayName(id, student)}
              detail={`${student.profile.goal_summary} · ${student.profile.self_level || "level pending"}`}
              right={
                <Link className="text-link" to="/t2">
                  Open →
                </Link>
              }
            />
          ))}
        </Panel>
        <Panel title="Teaching preparation">
          <p>
            Prepare a lesson briefing from the current plan and approved
            materials.
          </p>
          <div className="visual-panel short">
            <AIVisual variant="paper" />
          </div>
          <Link className="action secondary" to="/t5">
            Open preparation <ArrowRight size={15} />
          </Link>
        </Panel>
      </div>
    </Page>
  )
}
export function TeacherStudents() {
  const { students } = useTeacher()
  const { run, busy } = useApp()
  const ids = Object.keys(students)
  const [selected, setSelected] = useState(ids[0] || "")
  const student = students[selected]
  const [note, setNote] = useState(students[ids[0]]?.observation || "")
  const [recommendation, setRecommendation] = useState("")
  const [focus, setFocus] = useState("")
  return (
    <Page
      eyebrow="STUDENT PROGRESS"
      title="Teach with the full picture."
      subtitle="Use recorded goals, assessment evidence, and lesson feedback before changing a plan."
    >
      <div className="board teacher-grid">
        <Panel title="My students">
          <div className="list-stack">
            {ids.map((id) => (
              <button
                className={`select-row ${selected === id ? "active" : ""}`}
                key={id}
                onClick={() => {
                  setSelected(id)
                  setNote(students[id].observation || "")
                  setRecommendation("")
                }}
              >
                <strong>{displayName(id, students[id])}</strong>
                <small>{students[id].profile.goal_summary}</small>
              </button>
            ))}
          </div>
        </Panel>
        <div className="stack">
          <Panel
            title={
              student
                ? `${displayName(selected, student)} · learning record`
                : "Student record"
            }
          >
            {student ? (
              <>
                <div className="metric-grid in-panel three">
                  <Metric
                    label="Current level"
                    value={
                      student.assessments
                        .filter((x) => x.status === "confirmed")
                        .at(-1)?.level || "—"
                    }
                  />
                  <Metric
                    label="Target"
                    value={student.profile.target_level || "—"}
                  />
                  <Metric
                    label="Plan"
                    value={
                      student.plan?.status ||
                      student.pending_plan?.status ||
                      "None"
                    }
                  />
                </div>
                <p>
                  <strong>Goal:</strong> {student.profile.goal_text}
                </p>
                <p>
                  <strong>Latest assessment:</strong>{" "}
                  {student.assessments.at(-1)?.feedback || "No assessment yet."}
                </p>
                <p>
                  <strong>Plan stage:</strong>{" "}
                  {student.plan?.stages[student.plan.stage_index]?.title ||
                    "Awaiting approval"}
                </p>
              </>
            ) : (
              <Empty />
            )}
          </Panel>
          <Panel title="Teacher observation">
            <Textarea
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Write a concise observation"
            />
            <Button
              className="action primary"
              disabled={busy || !note.trim()}
              onClick={() =>
                run(
                  () => api.saveObservation(selected, note),
                  "Observation saved."
                )
              }
            >
              Save observation
            </Button>
          </Panel>
          <Panel title="AI progress support">
            <div className="button-row">
              <Button
                className="action secondary"
                disabled={busy}
                onClick={async () => {
                  const result = await run(() =>
                    api.request("review_progress", {}, selected)
                  )
                  if (result)
                    setRecommendation(String(result.result.recommendation))
                }}
              >
                Review progress <Sparkles size={15} />
              </Button>
              <Button
                className="action secondary"
                disabled={busy}
                onClick={async () => {
                  const result = await run(() =>
                    api.request("recommend_plan", {}, selected)
                  )
                  if (result)
                    setRecommendation(String(result.result.recommendation))
                }}
              >
                Recommend plan
              </Button>
            </div>
            {recommendation && <Status>{recommendation}</Status>}
            <div className="divider" />
            <h3>Directed assessment</h3>
            <label className="field-label">
              Focus
              <Input
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                placeholder="Evidence-to-claim connection"
              />
            </label>
            <Button
              className="action primary"
              disabled={busy || !focus.trim()}
              onClick={() =>
                run(
                  () => api.startAssessment(selected, "directed", focus),
                  "Directed assessment created."
                )
              }
            >
              Request assessment <ArrowRight size={15} />
            </Button>
          </Panel>
        </div>
      </div>
    </Page>
  )
}
export function TeacherLessons() {
  const { lessons, availability, students } = useTeacher()
  const { run, busy } = useApp()
  const [selected, setSelected] = useState(
    lessons.find((x) => x.status === "confirmed")?.id || lessons[0]?.id || ""
  )
  const lesson = lessons.find((x) => x.id === selected)
  const [attendance, setAttendance] = useState("attended")
  const [feedback, setFeedback] = useState("")
  const [slots, setSlots] = useState(availability)
  return (
    <Page
      eyebrow="LESSONS & AVAILABILITY"
      title="Time to teach."
      subtitle="Confirmed lessons and your declared availability share one schedule."
    >
      <div className="board two">
        <Panel title="Lesson schedule">
          {lessons.map((item) => (
            <Row
              key={item.id}
              title={item.title}
              detail={`${fmt(item.starts_at)} · ${displayName(item.student_id, students[item.student_id])}`}
              right={
                <Pill tone={item.status === "completed" ? "good" : "info"}>
                  {item.status}
                </Pill>
              }
              onClick={() => {
                setSelected(item.id)
                setFeedback(item.feedback || "")
              }}
            />
          ))}
        </Panel>
        <div className="stack">
          <Panel title={lesson?.title || "Lesson detail"}>
            {lesson ? (
              <>
                <Pill tone={lesson.status === "completed" ? "good" : "info"}>
                  {lesson.status}
                </Pill>
                <h3>{fmt(lesson.starts_at)}</h3>
                <p>
                  Student:{" "}
                  {displayName(lesson.student_id, students[lesson.student_id])}
                </p>
                <p>Attendance: {lesson.attendance.replace("_", " ")}</p>
                <label className="field-label">
                  Attendance
                  <select
                    value={attendance}
                    onChange={(e) => setAttendance(e.target.value)}
                  >
                    <option value="attended">Attended</option>
                    <option value="absent">Absent</option>
                  </select>
                </label>
                <label className="field-label">
                  Lesson observation
                  <Textarea
                    rows={4}
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    placeholder="Record teaching feedback"
                  />
                </label>
                <Button
                  className="action primary"
                  disabled={busy || !feedback.trim()}
                  onClick={() =>
                    run(
                      () => api.saveLesson(lesson.id, attendance, feedback),
                      "Lesson feedback saved."
                    )
                  }
                >
                  Save lesson record
                </Button>
              </>
            ) : (
              <Empty />
            )}
          </Panel>
          <Panel title="Teaching availability">
            <div className="visual-panel short">
              <AIVisual variant="path" />
            </div>
            {slots.map((slot, i) => (
              <div className="slot-row" key={i}>
                <select
                  aria-label={`Day ${i + 1}`}
                  value={slot.day}
                  onChange={(e) =>
                    setSlots(
                      slots.map((x, n) =>
                        n === i ? { ...x, day: e.target.value } : x
                      )
                    )
                  }
                >
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
                    (d) => (
                      <option key={d}>{d}</option>
                    )
                  )}
                </select>
                <Input
                  type="time"
                  value={slot.start}
                  onChange={(e) =>
                    setSlots(
                      slots.map((x, n) =>
                        n === i ? { ...x, start: e.target.value } : x
                      )
                    )
                  }
                />
                <Input
                  type="time"
                  value={slot.end}
                  onChange={(e) =>
                    setSlots(
                      slots.map((x, n) =>
                        n === i ? { ...x, end: e.target.value } : x
                      )
                    )
                  }
                />
              </div>
            ))}
            <div className="button-row">
              <Button
                className="action secondary"
                onClick={() =>
                  setSlots([
                    ...slots,
                    { day: "Fri", start: "18:00", end: "19:00" },
                  ])
                }
              >
                Add time
              </Button>
              <Button
                className="action primary"
                disabled={busy}
                onClick={() =>
                  run(() => api.saveAvailability(slots), "Availability saved.")
                }
              >
                Save availability
              </Button>
            </div>
          </Panel>
        </div>
      </div>
    </Page>
  )
}
export function TeacherReviews() {
  const { reviews, students } = useTeacher()
  const { run, busy } = useApp()
  const [selected, setSelected] = useState(
    reviews.find((x) => x.status === "pending")?.id || reviews[0]?.id || ""
  )
  const [detail, setDetail] = useState<ReviewDetail | null>(null)
  const [note, setNote] = useState("")
  const [filter, setFilter] = useState("all")
  useEffect(() => {
    if (!selected) return
    api
      .getReview(selected)
      .then(setDetail)
      .catch(() => setDetail(null))
  }, [selected, reviews.length])
  const visible = reviews.filter((x) => filter === "all" || x.kind === filter)
  async function decide(
    action: "approve" | "request_changes" | "confirm_result" | "answer"
  ) {
    const result = await run(
      () => api.decideReview(selected, action, note),
      "Review decision recorded."
    )
    if (result) {
      setNote("")
      setDetail(await api.getReview(selected))
    }
  }
  return (
    <Page
      eyebrow="AI SUPPORT · HUMAN JUDGEMENT"
      title="Human judgement, where it matters."
      subtitle="Approve a plan, confirm an uncertain result, or answer an escalated question."
    >
      <div className="choice-row tabs">
        {["all", "plan", "assessment", "question"].map((item) => (
          <button
            key={item}
            className={`choice ${filter === item ? "active" : ""}`}
            onClick={() => setFilter(item)}
          >
            {item === "all" ? "All decisions" : item}
          </button>
        ))}
      </div>
      <div className="board teacher-grid">
        <Panel title="Review queue">
          {visible.length ? (
            visible.map((review) => (
              <button
                data-testid={`review-${review.id}`}
                className={`select-row ${selected === review.id ? "active" : ""}`}
                key={review.id}
                onClick={() => {
                  setSelected(review.id)
                  setNote("")
                }}
              >
                <strong>
                  {displayName(review.student_id, students[review.student_id])}{" "}
                  · {review.kind}
                </strong>
                <small>{review.trigger}</small>
                <Pill tone={review.status === "pending" ? "warn" : "good"}>
                  {review.status}
                </Pill>
              </button>
            ))
          ) : (
            <Empty>No reviews in this category.</Empty>
          )}
        </Panel>
        <Panel title="Your decision, grounded in evidence">
          {detail ? (
            <>
              <div className="review-summary">
                <strong>
                  {displayName(
                    detail.review.student_id,
                    students[detail.review.student_id]
                  )}{" "}
                  · {detail.review.kind}
                </strong>
                <Pill
                  tone={detail.review.status === "pending" ? "warn" : "good"}
                >
                  {detail.review.status}
                </Pill>
              </div>
              <p>{detail.evidence}</p>
              <ReviewSubject detail={detail} />
              {detail.review.status === "pending" && (
                <>
                  <label className="field-label">
                    Decision note and supporting evidence
                    <Textarea
                      rows={4}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="Record the reason for your decision"
                    />
                  </label>
                  <div className="button-row">
                    <Button
                      className="action primary"
                      disabled={busy || !note.trim()}
                      onClick={() =>
                        decide(
                          detail.review.kind === "plan"
                            ? "approve"
                            : detail.review.kind === "assessment"
                              ? "confirm_result"
                              : "answer"
                        )
                      }
                    >
                      {detail.review.kind === "plan"
                        ? "Approve & activate"
                        : detail.review.kind === "assessment"
                          ? "Confirm result"
                          : "Answer question"}{" "}
                      <ArrowRight size={15} />
                    </Button>
                    <Button
                      className="action secondary"
                      disabled={busy || !note.trim()}
                      onClick={() => decide("request_changes")}
                    >
                      Request changes
                    </Button>
                  </div>
                </>
              )}
            </>
          ) : (
            <Empty>Select a review to see its evidence.</Empty>
          )}
        </Panel>
      </div>
    </Page>
  )
}
export function TeacherPreparation() {
  const { lessons, materials } = useTeacher()
  const { run, busy } = useApp()
  const [selected, setSelected] = useState(
    lessons.find((x) => x.status === "confirmed")?.id || lessons[0]?.id || ""
  )
  const [briefing, setBriefing] = useState("")
  const [title, setTitle] = useState("Evidence linking practice")
  const [materialId, setMaterialId] = useState(materials[0]?.id || "")
  const material = materials.find((x) => x.id === materialId)
  const [content, setContent] = useState(material?.content || "")
  return (
    <Page
      eyebrow="TEACHING PREPARATION"
      title="Be ready before class."
      subtitle="AI drafts briefing and material; you edit and approve what students can see."
    >
      <div className="board two">
        <Panel title="Lesson briefing">
          <label className="field-label">
            Lesson
            <select
              aria-label="Lesson"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              {lessons.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.title}
                </option>
              ))}
            </select>
          </label>
          <div className="visual-panel">
            <AIVisual variant="paper" />
          </div>
          <Button
            className="action primary"
            disabled={busy || !selected}
            onClick={async () => {
              const result = await run(() =>
                api.request(
                  "lesson_briefing",
                  { lesson_id: selected },
                  undefined,
                  selected
                )
              )
              if (result) setBriefing(String(result.result.briefing))
            }}
          >
            Prepare briefing <Sparkles size={15} />
          </Button>
          {briefing && <Status>{briefing}</Status>}
        </Panel>
        <Panel title="Teaching material">
          <label className="field-label">
            Material
            <select
              value={materialId}
              onChange={(e) => {
                setMaterialId(e.target.value)
                setContent(
                  materials.find((item) => item.id === e.target.value)
                    ?.content || ""
                )
              }}
            >
              {materials.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.title} · {x.status}
                </option>
              ))}
            </select>
          </label>
          {material && (
            <>
              <Pill tone={material.status === "approved" ? "good" : "warn"}>
                {material.status}
              </Pill>
              <p>{material.locator}</p>
              <Textarea
                rows={7}
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
              <div className="button-row">
                <Button
                  className="action secondary"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => api.saveMaterial(material.id, content, "draft"),
                      "Draft saved."
                    )
                  }
                >
                  Save draft
                </Button>
                <Button
                  className="action primary"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => api.saveMaterial(material.id, content, "approved"),
                      "Material approved."
                    )
                  }
                >
                  Approve material
                </Button>
              </div>
            </>
          )}
          <div className="divider" />
          <h3>Generate a draft</h3>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Material title"
          />
          <Button
            className="action secondary"
            disabled={busy || !title.trim()}
            onClick={async () => {
              const result = await run(
                () =>
                  api.request(
                    "generate_material",
                    { title, lesson_id: selected },
                    undefined,
                    selected
                  ),
                "Draft material created."
              )
              if (result) {
                const created = result.result.material as Material
                setMaterialId(created.id)
                setContent(created.content)
              }
            }}
          >
            Generate draft <Sparkles size={15} />
          </Button>
        </Panel>
      </div>
    </Page>
  )
}

function ReviewSubject({ detail }: { detail: ReviewDetail }) {
  if (detail.review.kind === "plan") {
    const plan = detail.subject as Plan | null
    return (
      <div className="review-subject">
        {plan ? (
          <>
            <div className="metric-grid in-panel three">
              <Metric label="Version" value={plan.version} />
              <Metric
                label="Weekly time"
                value={`${plan.weekly_hours} hours`}
              />
              <Metric label="Matched teacher" value={plan.teacher.name} />
            </div>
            <p>{plan.reason}</p>
            <div className="review-stages">
              {plan.stages.map((stage, index) => (
                <div key={stage.title}>
                  <strong>
                    {String(index + 1).padStart(2, "0")} · {stage.title}
                  </strong>
                  <small>
                    {stage.milestone} · Weeks {stage.start_week}–
                    {stage.end_week}
                  </small>
                </div>
              ))}
            </div>
          </>
        ) : (
          <Empty />
        )}
      </div>
    )
  }
  if (detail.review.kind === "assessment") {
    const item = detail.subject as Assessment | null
    return (
      <div className="review-subject">
        {item ? (
          <>
            <div className="metric-grid in-panel three">
              <Metric label="Level" value={item.level} />
              <Metric
                label="Confidence"
                value={`${Math.round(item.confidence * 100)}%`}
              />
              <Metric label="Status" value={item.status.replace("_", " ")} />
            </div>
            <p>{item.feedback}</p>
            <Row title="Strengths" detail={item.strengths.join(", ")} />
            <Row title="Areas to review" detail={item.weaknesses.join(", ")} />
          </>
        ) : (
          <Empty />
        )}
      </div>
    )
  }
  const item = detail.subject as Interaction | null
  return (
    <div className="review-subject">
      {item ? (
        <>
          <Row title="Student question" detail={item.question} />
          <Row title="Current answer" detail={item.answer} />
          {detail.draft_answer && (
            <section aria-label="AI draft (not sent)">
              <h3>AI draft (not sent)</h3>
              <Status>{detail.draft_answer}</Status>
              {!!detail.draft_source_refs?.length && (
                <ul>
                  {detail.draft_source_refs.map((source, index) => (
                    <li key={index}>
                      {source.title || source.material_id}
                      {source.locator ? ` · ${source.locator}` : ""}
                    </li>
                  ))}
                </ul>
              )}
              <p>
                Review the draft and write your final answer below. The student
                has not received this draft.
              </p>
            </section>
          )}
          <Row
            title="Confidence"
            detail={`${Math.round(item.confidence * 100)}%`}
          />
        </>
      ) : (
        <Empty />
      )}
    </div>
  )
}
