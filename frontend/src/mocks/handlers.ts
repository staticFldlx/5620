import { http, HttpResponse } from "msw"
import fixture from "./fixture.json"
import type {
  Assessment,
  Availability,
  Interaction,
  Lesson,
  Material,
  Operations,
  Plan,
  RequestEnvelope,
  RequestType,
  Review,
  StudentRecord,
  User,
  Workspace,
} from "@/api/types"

type Store = {
  users: User[]
  students: Record<string, StudentRecord>
  teacher_availability: Availability[]
  lessons: Lesson[]
  materials: Material[]
  interactions: Interaction[]
  reviews: Review[]
  operations: Operations
  requests: RequestEnvelope[]
  password_hashes: Record<string, string>
  assessment_sessions: {
    id: string
    student_id: string
    kind: string
    focus: string
    answered: number
    answered_items: string[]
    max_items: number
    status: string
    current_item: string
  }[]
}
const initial = fixture as unknown as Omit<
  Store,
  "requests" | "assessment_sessions"
>
const key = "lingopath-mock-v1"
const demoHash =
  "75720c14118af03a7444e67f9bfbb9e7fefd38c5d357483b516cc6a66d8fb71d"
async function hashPassword(value: string) {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value)
  )
  return [...new Uint8Array(bytes)]
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("")
}
function read(): Store {
  try {
    const saved = localStorage.getItem(key)
    if (saved) {
      const data = JSON.parse(saved) as Store
      data.password_hashes ||= Object.fromEntries(
        data.users.slice(0, 3).map((user) => [user.id, demoHash])
      )
      for (const user of data.users) {
        if (
          user.role === "Student" &&
          data.students[user.id] &&
          !data.students[user.id].name
        )
          data.students[user.id].name = user.name
      }
      return data
    }
  } catch {
    /* use fixture */
  }
  return {
    ...structuredClone(initial),
    requests: [],
    password_hashes: Object.fromEntries(
      initial.users.map((user) => [user.id, demoHash])
    ),
    assessment_sessions: [],
  }
}
function save(data: Store) {
  localStorage.setItem(key, JSON.stringify(data))
}
function current(request: Request, data: Store): User | undefined {
  const token = request.headers.get("authorization")?.replace(/^Bearer /, "")
  return data.users.find((user) => user.id === token)
}
function denied() {
  return HttpResponse.json(
    { message: "Sign in with an authorised demo account." },
    { status: 401 }
  )
}
function missing() {
  return HttpResponse.json({ message: "Record not found." }, { status: 404 })
}
function body<T>(request: Request): Promise<T> {
  return request.json() as Promise<T>
}
function respond<T>(value: T) {
  return HttpResponse.json(value as Parameters<typeof HttpResponse.json>[0])
}
function requestResult(
  data: Store,
  type: RequestType,
  input: Record<string, unknown>,
  studentId: string
): RequestEnvelope {
  const id = `RQ-${Date.now().toString(36)}`
  const student = data.students[studentId]
  let result: Record<string, unknown> = {}
  let status = "completed"
  if (type === "collect_goal")
    result = {
      summary: String(input.goal_text || student.profile.goal_text).slice(
        0,
        90
      ),
      focus_skills: input.focus_skills || student.profile.focus_skills,
    }
  if (type === "confirm_goal") {
    student.profile.goal_text = String(
      input.goal_text || student.profile.goal_text
    )
    student.profile.goal_summary = String(
      input.goal_summary || student.profile.goal_summary
    )
    student.profile.focus_skills = Array.isArray(input.focus_skills)
      ? input.focus_skills.map(String)
      : student.profile.focus_skills
    student.profile.weekly_hours = Number(
      input.weekly_hours || student.profile.weekly_hours
    )
    student.profile.self_level = String(
      input.self_level || student.profile.self_level
    )
    student.profile.target_level = String(
      input.target_level || student.profile.target_level
    )
    result = { profile: student.profile }
  }
  if (type === "revise_plan" || type === "replace_teacher") {
    const base = student.plan
    if (base && !student.pending_plan) {
      const reviewId = `RV-${Date.now().toString(36)}`
      const plan: Plan = {
        ...structuredClone(base),
        id: `${base.id}-v${base.version + 1}`,
        version: base.version + 1,
        status: "pending_review",
        reason: String(input.reason || "Revision requested"),
        review_id: reviewId,
        approved_at: null,
      }
      student.pending_plan = plan
      data.reviews.unshift({
        id: reviewId,
        kind: "plan",
        student_id: studentId,
        subject_id: plan.id,
        status: "pending",
        trigger: plan.reason,
        decision: null,
      })
      result = { plan, review_id: reviewId }
      status = "pending_review"
    } else {
      status = "rejected"
      result = {
        message:
          "Wait for the current plan review before requesting another revision.",
      }
    }
  }
  if (type === "reschedule") {
    result = {
      lesson_id: input.lesson_id,
      proposed_slot: input.slot || "Thursday 18:00",
      message: "A proposed time is ready for student confirmation.",
    }
    status = "awaiting_confirmation"
  }
  if (type === "confirm_slot") {
    const matchingProposal = data.requests.some(
      (item) =>
        item.type === "reschedule" &&
        item.status === "awaiting_confirmation" &&
        item.result.proposed_slot === input.slot &&
        item.result.lesson_id === input.lesson_id
    )
    if (!matchingProposal) {
      status = "rejected"
      result = { message: "Propose the specific slot before confirmation." }
    }
    const lesson = data.lessons.find(
      (item) => item.id === input.lesson_id && item.student_id === studentId
    )
    if (matchingProposal && lesson && input.starts_at) {
      lesson.starts_at = String(input.starts_at)
      lesson.ends_at = new Date(
        new Date(lesson.starts_at).getTime() + 3600000
      ).toISOString()
      result = { lesson }
    }
  }
  if (type === "explain" || type === "resources") {
    const question = String(
      input.question || "Find learning resources for my current stage"
    )
    const uncertain = /unpublished|permission|copyright|未经|引用录音/i.test(
      question
    )
    const interaction: Interaction = {
      id,
      student_id: studentId,
      type,
      question,
      answer: uncertain
        ? "The available sources do not establish the permission rules. Your teacher will review this question."
        : type === "resources"
          ? "Start with the approved Academic Argument Guide and Evidence & Commentary. Each resource is linked to your current stage."
          : "Use a short because bridge: state the evidence, explain what it shows, then connect it to your claim.",
      feedback: null,
      status: uncertain ? "escalated" : "completed",
      confidence: uncertain ? 0.41 : 0.89,
      source_refs: uncertain
        ? []
        : data.materials
            .filter((material) => material.status === "approved")
            .slice(0, 2)
            .map((material) => ({
              material_id: material.id,
              title: material.title,
              locator: material.locator,
            })),
      sent_at: new Date().toISOString(),
      escalation: uncertain
        ? { trigger: "Insufficient source evidence", status: "pending" }
        : null,
    }
    data.interactions.push(interaction)
    result = { interaction }
    status = interaction.status
    if (uncertain)
      data.reviews.unshift({
        id: `RV-${id}`,
        kind: "question",
        student_id: studentId,
        subject_id: id,
        status: "pending",
        trigger: "Insufficient source evidence",
        decision: null,
      })
  }
  if (type === "practice")
    result = {
      question:
        "Write one sentence that explains how evidence supports your main claim.",
      source: "Academic Argument Guide",
    }
  if (type === "practice_answer")
    result = {
      feedback:
        String(input.answer || "").trim().length > 30
          ? "Good connection. You explained how the evidence supports the claim."
          : "Add a because bridge and explain what the evidence shows.",
    }
  if (type === "review_progress" || type === "recommend_plan")
    result = {
      recommendation: `Review ${student.profile.goal_summary}, the latest assessment and the current plan before changing the teaching strategy.`,
      evidence: student.assessments.at(-1)?.feedback || "No assessment yet.",
    }
  if (type === "lesson_briefing")
    result = {
      briefing:
        "Focus on evidence-to-claim connections. The latest feedback asks for a clearer explanation of significance.",
      source_refs: data.materials
        .filter((item) => item.status === "approved")
        .map((item) => item.title),
    }
  if (type === "generate_material") {
    const id = `M-${Date.now().toString(36)}`
    const material: Material = {
      id,
      title: String(input.title || "Evidence linking practice"),
      locator: "Teacher draft",
      status: "draft",
      lesson_id: String(input.lesson_id || "L-018"),
      content:
        "Model: The claim is supported by the evidence because the observation explains the underlying reason. Add a source citation before use.",
      source_refs: [],
    }
    data.materials.push(material)
    result = { material }
  }
  const envelope = { id, type, status, phase: status, result }
  data.requests.push(envelope)
  return envelope
}
function draftInitialPlan(data: Store, studentId: string) {
  const student = data.students[studentId]
  if (!student || student.plan || student.pending_plan) return
  const assessment = student.assessments
    .filter((item) => item.status === "confirmed")
    .at(-1)
  if (!assessment) return
  const reviewId = `RV-${Date.now().toString(36)}`
  const stages = [
    [
      "Goal foundations",
      "Read and organise ideas",
      "Identify a clear claim and its evidence.",
    ],
    [
      "Applied writing",
      "Connect evidence and explanation",
      "Explain how evidence supports a claim.",
    ],
    [
      "Critical reading",
      "Compare sources",
      "Compare two arguments with cited evidence.",
    ],
    [
      "Confident communication",
      "Discuss and present",
      "Explain a position and respond to questions.",
    ],
  ]
  const plan: Plan = {
    id: `PL-${Date.now().toString(36)}`,
    version: 1,
    status: "pending_review",
    stage_index: 0,
    teacher: { id: "teacher-emily", name: "Emily Walker" },
    weekly_hours: student.profile.weekly_hours,
    stages: stages.map(([title, topic, milestone], index) => ({
      title,
      course_ref: `CORE-${index + 1}`,
      start_week: index * 3 + 1,
      end_week: index * 3 + 3,
      topics: [topic],
      milestone,
      status: "upcoming",
    })),
    reason: `Initial plan from ${student.profile.goal_summary} and confirmed ${assessment.level} assessment.`,
    review_id: reviewId,
    approved_at: null,
  }
  student.pending_plan = plan
  data.reviews.unshift({
    id: reviewId,
    kind: "plan",
    student_id: studentId,
    subject_id: plan.id,
    status: "pending",
    trigger: "Initial learning plan requires teacher approval.",
    decision: null,
  })
}
const prefix = "/api/v1"
export const handlers = [
  http.post(`${prefix}/auth/login`, async ({ request }) => {
    const { email, password } = await body<{ email: string; password: string }>(
      request
    )
    const data = read()
    const user = data.users.find(
      (item) => item.email.toLowerCase() === email.toLowerCase()
    )
    return user &&
      data.password_hashes[user.id] === (await hashPassword(password))
      ? respond({ session: user.id, user })
      : HttpResponse.json(
          { message: "Invalid demo email or password." },
          { status: 401 }
        )
  }),
  http.post(`${prefix}/auth/register`, async ({ request }) => {
    const { name, email, password } = await body<{
      name: string
      email: string
      password: string
    }>(request)
    const data = read()
    if (!name.trim() || !email.includes("@") || password.length < 8)
      return HttpResponse.json(
        { message: "Enter a name, valid email and at least 8 characters." },
        { status: 400 }
      )
    if (data.users.some((user) => user.email === email))
      return HttpResponse.json(
        { message: "Email already exists." },
        { status: 409 }
      )
    const user: User = {
      id: `student-${Date.now().toString(36)}`,
      name,
      email,
      role: "Student",
    }
    data.users.push(user)
    data.password_hashes[user.id] = await hashPassword(password)
    data.students[user.id] = {
      name,
      profile: {
        goal_text: "",
        goal_summary: "Set your learning goal",
        focus_skills: [],
        target_level: "",
        self_level: "",
        weekly_hours: 3,
        timezone: "Australia/Sydney",
        availability: [],
      },
      assessments: [],
      plan: null,
      pending_plan: null,
      material_records: [],
      observation: "",
    }
    save(data)
    return respond({ session: user.id, user })
  }),
  http.get(`${prefix}/workspace`, ({ request }) => {
    const data = read(),
      user = current(request, data)
    if (!user) return denied()
    const studentId = new URL(request.url).searchParams.get("student_id")
    if (studentId && user.role !== "Teacher") return denied()
    if (studentId && !data.students[studentId]) return missing()
    let workspace: Workspace = { user }
    if (user.role === "Student")
      workspace = {
        user,
        students: { [user.id]: data.students[user.id] },
        lessons: data.lessons.filter((x) => x.student_id === user.id),
        materials: data.materials.filter((x) =>
          data.lessons.some(
            (l) => l.student_id === user.id && l.material_ids.includes(x.id)
          )
        ),
        interactions: data.interactions.filter((x) => x.student_id === user.id),
      }
    if (user.role === "Teacher")
      workspace = {
        user,
        students: studentId
          ? { [studentId]: data.students[studentId] }
          : data.students,
        lessons: data.lessons.filter((x) => x.teacher.id === user.id),
        materials: data.materials,
        reviews: data.reviews,
        teacher_availability: data.teacher_availability,
      }
    if (user.role === "Founder")
      workspace = { user, operations: data.operations }
    return respond(workspace)
  }),
  http.post(`${prefix}/requests`, async ({ request }) => {
    const data = read(),
      user = current(request, data)
    if (!user) return denied()
    const {
      type,
      input = {},
      student_id,
    } = await body<{
      type: RequestType
      input: Record<string, unknown>
      student_id?: string
    }>(request)
    const studentId =
      user.role === "Student" ? user.id : student_id || "student-ivy"
    if (!data.students[studentId]) return missing()
    const result = requestResult(data, type, input, studentId)
    if (result.status === "rejected")
      return HttpResponse.json(
        { message: result.result.message },
        { status: 400 }
      )
    save(data)
    return respond(result)
  }),
  http.get(`${prefix}/requests/:id`, ({ request, params }) => {
    const data = read()
    if (!current(request, data)) return denied()
    return respond(data.requests.find((x) => x.id === params.id) || null)
  }),
  http.post(`${prefix}/assessments`, async ({ request }) => {
    const data = read(),
      user = current(request, data)
    if (!user) return denied()
    const {
      student_id,
      kind,
      focus = "",
    } = await body<{ student_id: string; kind: string; focus?: string }>(
      request
    )
    if (
      !data.students[student_id] ||
      (user.role === "Student" && user.id !== student_id)
    )
      return denied()
    if (!data.students[student_id].profile.goal_text)
      return HttpResponse.json(
        { message: "Confirm a learning goal before assessment." },
        { status: 400 }
      )
    const session = {
      id: `AS-${Date.now().toString(36)}`,
      student_id,
      kind,
      focus,
      answered: 0,
      answered_items: [],
      max_items: 3,
      status: "in_progress",
      current_item: "What is the main claim in this short academic argument?",
    }
    data.assessment_sessions.push(session)
    save(data)
    return respond(session)
  }),
  http.get(`${prefix}/assessments/:id`, ({ request, params }) => {
    const data = read()
    if (!current(request, data)) return denied()
    return respond(
      data.assessment_sessions.find((x) => x.id === params.id) ||
        Object.values(data.students)
          .flatMap((x) => x.assessments)
          .find((x) => x.id === params.id) ||
        null
    )
  }),
  http.post(
    `${prefix}/assessments/:id/answers`,
    async ({ request, params }) => {
      const data = read(),
        user = current(request, data)
      if (!user) return denied()
      const session = data.assessment_sessions.find((x) => x.id === params.id)
      if (!session) return missing()
      const { item_id, answer } = await body<{
        item_id: string
        answer: string
      }>(request)
      session.answered_items ||= []
      if (session.answered_items.includes(item_id)) return respond(session)
      if (!answer.trim())
        return HttpResponse.json(
          { message: "Please enter an answer." },
          { status: 400 }
        )
      session.answered_items.push(item_id)
      session.answered++
      if (session.answered < session.max_items)
        session.current_item = [
          "Explain how one piece of evidence supports that claim.",
          "What would you improve in the argument?",
        ][session.answered - 1]
      else {
        session.status = "pending_review"
        const record: Assessment = {
          id: `A-${Date.now().toString(36)}`,
          kind: session.kind,
          status: "pending_review",
          created_at: new Date().toISOString(),
          level: "B1–B2",
          confidence: 0.62,
          strengths: ["Academic reading"],
          weaknesses: ["Evidence links"],
          goal_gap: "More reliable evidence needed",
          feedback: "Your result is provisional until teacher review.",
          requested_focus: session.focus,
        }
        data.students[session.student_id].assessments.push(record)
        data.reviews.unshift({
          id: `RV-${record.id}`,
          kind: "assessment",
          student_id: session.student_id,
          subject_id: record.id,
          status: "pending",
          trigger: "Low-confidence assessment result",
          decision: null,
        })
      }
      save(data)
      return respond(session)
    }
  ),
  http.get(`${prefix}/reviews/:id`, ({ request, params }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Teacher") return denied()
    const review = data.reviews.find((x) => x.id === params.id)
    if (!review) return missing()
    const student = data.students[review.student_id]
    const subject =
      review.kind === "plan"
        ? student.pending_plan || student.plan
        : review.kind === "assessment"
          ? student.assessments.find((x) => x.id === review.subject_id)
          : data.interactions.find((x) => x.id === review.subject_id)
    return respond({ review, subject, evidence: review.trigger })
  }),
  http.post(`${prefix}/reviews/:id/decision`, async ({ request, params }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Teacher") return denied()
    const review = data.reviews.find((x) => x.id === params.id)
    if (!review) return missing()
    const { action, note } = await body<{ action: string; note: string }>(
      request
    )
    if (!note?.trim())
      return HttpResponse.json(
        { message: "A decision note is required." },
        { status: 400 }
      )
    review.status = "decided"
    review.decision = action
    const student = data.students[review.student_id]
    if (
      review.kind === "plan" &&
      action === "request_changes" &&
      student.pending_plan
    )
      student.pending_plan.status = "changes_requested"
    if (
      review.kind === "plan" &&
      action === "approve" &&
      student.pending_plan
    ) {
      student.pending_plan.status = "active"
      student.pending_plan.approved_at = new Date().toISOString()
      student.plan = student.pending_plan
      student.pending_plan = null
    }
    if (review.kind === "assessment" && action === "request_changes") {
      const assessment = student.assessments.find(
        (x) => x.id === review.subject_id
      )
      if (assessment) assessment.status = "changes_requested"
    }
    if (review.kind === "assessment" && action === "confirm_result") {
      const assessment = student.assessments.find(
        (x) => x.id === review.subject_id
      )
      if (assessment) {
        assessment.status = "confirmed"
        assessment.review_note = note
        draftInitialPlan(data, review.student_id)
      }
    }
    if (review.kind === "question" && action === "answer") {
      const interaction = data.interactions.find(
        (x) => x.id === review.subject_id
      )
      if (interaction) {
        interaction.answer = note
        interaction.status = "completed"
      }
    }
    save(data)
    return respond({ review })
  }),
  http.patch(
    `${prefix}/students/:id/observation`,
    async ({ request, params }) => {
      const data = read(),
        user = current(request, data)
      if (user?.role !== "Teacher") return denied()
      const student = data.students[String(params.id)]
      if (!student) return missing()
      const { note } = await body<{ note: string }>(request)
      student.observation = note
      save(data)
      return respond({
        note,
        updated_at: new Date().toISOString(),
        teacher_id: user.id,
      })
    }
  ),
  http.patch(`${prefix}/teachers/me/availability`, async ({ request }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Teacher") return denied()
    const { availability } = await body<{ availability: Availability[] }>(
      request
    )
    data.teacher_availability = availability
    save(data)
    return respond({ timezone: "Australia/Sydney", availability })
  }),
  http.patch(`${prefix}/lessons/:id`, async ({ request, params }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Teacher") return denied()
    const lesson = data.lessons.find((x) => x.id === params.id)
    if (!lesson) return missing()
    const { attendance, feedback } = await body<{
      attendance: string
      feedback: string
    }>(request)
    lesson.attendance = attendance
    lesson.feedback = feedback
    lesson.status = "completed"
    save(data)
    return respond(lesson)
  }),
  http.get(`${prefix}/materials/:id`, ({ request, params }) => {
    const data = read()
    if (!current(request, data)) return denied()
    return respond(data.materials.find((x) => x.id === params.id) || null)
  }),
  http.patch(`${prefix}/materials/:id`, async ({ request, params }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Teacher") return denied()
    const material = data.materials.find((x) => x.id === params.id)
    if (!material) return missing()
    const { content, status } = await body<{ content: string; status: string }>(
      request
    )
    material.content = content
    material.status = status
    save(data)
    return respond(material)
  }),
  http.get(`${prefix}/cases/:id`, ({ request, params }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Founder") return denied()
    return respond(
      data.operations.cases.find((x) => x.id === params.id) || null
    )
  }),
  http.post(`${prefix}/cases/:id/decision`, async ({ request, params }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Founder") return denied()
    const item = data.operations.cases.find((x) => x.id === params.id)
    if (!item) return missing()
    const { action, note } = await body<{ action: string; note: string }>(
      request
    )
    item.decision = `${action}: ${note}`
    item.status = "decided"
    data.operations.audit.unshift({
      id: `AUD-${Date.now().toString(36)}`,
      time: new Date().toISOString(),
      actor_role: "Founder",
      actor_name: user.name,
      subject_id: item.id,
      action,
      result: note,
    })
    save(data)
    return respond(item)
  }),
  http.post(`${prefix}/agents/:id/decision`, async ({ request, params }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Founder") return denied()
    const { note } = await body<{ note: string }>(request)
    const agent = data.operations.agents.find((x) => x.id === params.id)
    if (!agent) return missing()
    data.operations.audit.unshift({
      id: `AUD-${Date.now().toString(36)}`,
      time: new Date().toISOString(),
      actor_role: "Founder",
      actor_name: user.name,
      subject_id: agent.id,
      action: "request_correction",
      result: note,
    })
    save(data)
    return respond({ agent, status: "requested" })
  }),
  http.get(`${prefix}/proposals/:id`, ({ request, params }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Founder") return denied()
    return respond(
      data.operations.proposals.find((x) => x.id === params.id) || null
    )
  }),
  http.post(`${prefix}/proposals/:id/decision`, async ({ request, params }) => {
    const data = read(),
      user = current(request, data)
    if (user?.role !== "Founder") return denied()
    const item = data.operations.proposals.find((x) => x.id === params.id)
    if (!item) return missing()
    const { action, note } = await body<{ action: string; note: string }>(
      request
    )
    item.status = action === "approve" ? "approved" : "rejected"
    item.decision = `${action}: ${note}`
    data.operations.audit.unshift({
      id: `AUD-${Date.now().toString(36)}`,
      time: new Date().toISOString(),
      actor_role: "Founder",
      actor_name: user.name,
      subject_id: item.id,
      action,
      result: note,
    })
    save(data)
    return respond(item)
  }),
]
