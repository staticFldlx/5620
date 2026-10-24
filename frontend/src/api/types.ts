export type Role = "Student" | "Teacher" | "Founder"
export type User = { id: string; name: string; email: string; role: Role }
export type Assessment = {
  id: string
  kind: string
  status: string
  created_at: string
  level: string
  confidence: number
  strengths: string[]
  weaknesses: string[]
  goal_gap: string
  feedback: string
  review_note?: string | null
  requested_focus?: string | null
}
export type Stage = {
  target_level?: string
  milestone_status?: string
  title: string
  course_ref: string
  start_week: number
  end_week: number
  topics: string[]
  milestone: string
  status: string
}
export type Plan = {
  progress_message?: string
  id: string
  version: number
  status: string
  stage_index: number
  teacher: { id: string; name: string }
  weekly_hours: number
  stages: Stage[]
  reason: string
  review_id: string
  approved_at: string | null
  revision_request?: {
    reason: string
    submitted_at: string
    can_withdraw: boolean
  } | null
}
export type Profile = {
  goal_text: string
  goal_summary: string
  focus_skills: string[]
  target_level: string
  self_level: string
  weekly_hours: number
  timezone: string
  availability: Availability[]
}
export type Availability = { day: string; start: string; end: string }
export type StudentRecord = {
  name?: string
  profile: Profile
  assessments: Assessment[]
  plan: Plan | null
  pending_plan: Plan | null
  material_records: { material_id: string; completed_at: string }[]
  observation: string
}
export type Lesson = {
  id: string
  student_id: string
  title: string
  starts_at: string
  ends_at: string
  teacher: { id: string; name: string }
  stage_index: number
  status: string
  classroom_url: string | null
  attendance: string
  feedback: string
  material_ids: string[]
}
export type Material = {
  id: string
  title: string
  locator: string
  status: string
  lesson_id: string
  content: string
  source_refs: unknown[]
}
export type Interaction = {
  id: string
  student_id: string
  type: string
  question: string
  answer: string
  feedback: string | null
  status: string
  confidence: number
  source_refs: { material_id: string; title: string; locator: string }[]
  sent_at: string
  escalation: unknown
}
export type Review = {
  id: string
  kind: string
  student_id: string
  subject_id: string
  status: string
  trigger: string
  decision: string | null
}
export type Agent = {
  id: string
  name: string
  status: string
  latest_task: {
    id: string
    status: string
    confidence: number
    output_summary: string
  }
}
export type Log = {
  id: string
  time: string
  agent_id: string
  event: string
  severity: string
  task_status: string
  confidence: number
  escalated: boolean
}
export type Case = {
  available_actions?: string[]
  id: string
  kind: string
  status: string
  subject: string
  trigger: string
  diagnosis: string
  evidence: { ref: string; summary: string }[]
  proposal_id: string | null
  decision: string | null
  verification: string | null
}
export type Proposal = {
  id: string
  type: string
  title: string
  case_id: string | null
  status: string
  evidence: string[]
  before: string
  after: string
  validation: string
  rollback: string
  decision: string | null
  execution: { status: string; verification: string | null }
}
export type Operations = {
  agents: Agent[]
  services: { name: string; status: string; last_backup_at: string | null }[]
  logs: Log[]
  warnings: {
    id: string
    trigger: string
    status: string
    output_summary: string
  }[]
  cases: Case[]
  proposals: Proposal[]
  audit: {
    id: string
    time: string
    actor_role: string
    actor_name: string
    subject_id: string
    action: string
    result: string
  }[]
}
// A plan request paused until the student picks one of the offered lesson times.
// It is answered with the paused request's own type (usually start_assessment).
export type PlanChoice = {
  request_id: string
  request_type: RequestType
  question: string
  message: string
  slots: { id: string; starts_at: string; ends_at: string }[]
}
export type Workspace = {
  assessment_sessions?: AssessmentSession[]
  plan_choice?: PlanChoice | null
  user: User
  students?: Record<string, StudentRecord>
  lessons?: Lesson[]
  materials?: Material[]
  interactions?: Interaction[]
  reviews?: Review[]
  teacher_availability?: Availability[]
  operations?: Operations
}
export type RequestType =
  | "collect_goal"
  | "confirm_goal"
  | "revise_plan"
  | "reschedule"
  | "confirm_slot"
  | "replace_teacher"
  | "explain"
  | "resources"
  | "practice"
  | "practice_answer"
  | "review_progress"
  | "recommend_plan"
  | "lesson_briefing"
  | "generate_material"
  | "start_assessment" // only as a reply to a paused request (PlanChoice)
export type RequestEnvelope = {
  id: string
  type: string
  status: string
  phase: string
  result: Record<string, unknown>
  error?: { code: string; message: string } | null
}

export type AssessmentResponse = {
  number: number
  prompt: string
  answer: string
}
export type AssessmentSession = {
  id: string
  student_id: string
  kind: string
  focus: string
  current_item: string
  current_item_id: string | null
  answered: number
  answered_items: string[]
  responses?: AssessmentResponse[]
  max_items: number
  status: string
  result?: Assessment | null
  follow_up?: RequestEnvelope | null
}
export type ReviewDetail = {
  review: Review
  subject: unknown
  evidence: string
  draft_answer?: string | null
  draft_source_refs?: {
    material_id?: string
    title?: string
    locator?: string
  }[]
}
export type DecisionResult = { follow_up?: RequestEnvelope | null }
