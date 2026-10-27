import axios from "axios"
import type {
  AssessmentSession,
  DecisionResult,
  ReviewDetail,
  Availability,
  Case,
  Lesson,
  Material,
  Proposal,
  RequestEnvelope,
  RequestType,
  User,
  Workspace,
} from "./types"

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 180000, // Inline pipelines can include several model calls; worker responses are polled below.
})
http.interceptors.request.use((config) => {
  const session = localStorage.getItem("lingopath-session")
  if (session) config.headers.Authorization = `Bearer ${session}`
  return config
})
export const sessionStore = {
  get: () => localStorage.getItem("lingopath-session"),
  set: (session: string) => localStorage.setItem("lingopath-session", session),
  clear: () => localStorage.removeItem("lingopath-session"),
}

const getRequest = async (id: string) =>
  (await http.get<RequestEnvelope>(`/requests/${id}`, { timeout: 30000 })).data
async function settle(
  value: RequestEnvelope,
  fail = true
): Promise<RequestEnvelope> {
  const deadline = Date.now() + 180000
  while (["queued", "running"].includes(value.status)) {
    if (Date.now() >= deadline) {
      if (!fail) return value
      throw new Error(
        "Your request is still processing. Refresh before submitting again."
      )
    }
    await new Promise((resolve) => setTimeout(resolve, 750))
    value = await getRequest(value.id)
  }
  if (fail && value.status === "failed")
    throw new Error(value.error?.message || "The request failed.")
  return value
}
async function assessment(
  value: AssessmentSession | RequestEnvelope
): Promise<AssessmentSession> {
  if (!("type" in value)) {
    if (
      value.follow_up &&
      ["queued", "running"].includes(value.follow_up.status)
    )
      return assessment(value.follow_up)
    return value
  }
  const envelope = await settle(value, false)
  if (["queued", "running"].includes(envelope.status))
    throw new Error(
      "Your assessment is still processing. Resume it from your assessment list shortly."
    )
  if (typeof envelope.result.session_id !== "string")
    throw new Error(
      envelope.error?.message || "The assessment has not been created."
    )
  const session = (
    await http.get<AssessmentSession>(
      `/assessments/${envelope.result.session_id}`
    )
  ).data
  return { ...session, follow_up: envelope }
}
async function decision<T extends DecisionResult>(value: T): Promise<T> {
  if (value.follow_up) value.follow_up = await settle(value.follow_up, false)
  return value
}

export const api = {
  login: async (email: string, password: string) =>
    (
      await http.post<{ session: string; user: User }>("/auth/login", {
        email,
        password,
      })
    ).data,
  register: async (name: string, email: string, password: string) =>
    (
      await http.post<{ session: string; user: User }>("/auth/register", {
        name,
        email,
        password,
      })
    ).data,
  workspace: async (studentId?: string) =>
    (
      await http.get<Workspace>("/workspace", {
        params: studentId ? { student_id: studentId } : undefined,
      })
    ).data,
  request: async (
    type: RequestType,
    input: Record<string, unknown> = {},
    studentId?: string,
    contextId?: string
  ) =>
    settle(
      (
        await http.post<RequestEnvelope>("/requests", {
          type,
          input,
          student_id: studentId,
          context_id: contextId,
        })
      ).data
    ),
  getRequest,
  startAssessment: async (
    studentId: string,
    kind: "initial" | "milestone" | "directed",
    focus?: string
  ) =>
    assessment(
      (
        await http.post<AssessmentSession | RequestEnvelope>("/assessments", {
          student_id: studentId,
          kind,
          focus,
        })
      ).data
    ),
  getAssessment: async (id: string) =>
    assessment((await http.get<AssessmentSession>(`/assessments/${id}`)).data),
  answerAssessment: async (id: string, itemId: string, answer: string) =>
    assessment(
      (
        await http.post<AssessmentSession | RequestEnvelope>(
          `/assessments/${id}/answers`,
          { item_id: itemId, answer }
        )
      ).data
    ),
  withdrawPlanRevision: async (id: string) =>
    (await http.post<{ withdrawn: boolean }>(`/plans/${id}/withdraw`)).data,
  getReview: async (id: string) =>
    (await http.get<ReviewDetail>(`/reviews/${id}`)).data,
  decideReview: async (
    id: string,
    action: "approve" | "request_changes" | "confirm_result" | "answer",
    note: string,
    correctedLevel?: string
  ) =>
    decision(
      (
        await http.post<DecisionResult>(`/reviews/${id}/decision`, {
          action,
          note,
          ...(action === "confirm_result" && correctedLevel
            ? { corrected_level: correctedLevel }
            : {}),
        })
      ).data
    ),
  saveObservation: async (studentId: string, note: string) =>
    (await http.patch(`/students/${studentId}/observation`, { note })).data,
  saveAvailability: async (availability: Availability[]) =>
    (
      await http.patch("/teachers/me/availability", {
        timezone: "Australia/Sydney",
        availability,
      })
    ).data,
  saveLesson: async (id: string, attendance: string, feedback: string) =>
    (await http.patch<Lesson>(`/lessons/${id}`, { attendance, feedback })).data,
  getMaterial: async (id: string) =>
    (await http.get<Material>(`/materials/${id}`)).data,
  saveMaterial: async (id: string, content: string, status: string) =>
    (await http.patch<Material>(`/materials/${id}`, { content, status })).data,
  getCase: async (id: string) => (await http.get<Case>(`/cases/${id}`)).data,
  decideCase: async (id: string, action: string, note: string) =>
    decision(
      (
        await http.post<Case & DecisionResult>(`/cases/${id}/decision`, {
          action,
          note,
        })
      ).data
    ),
  decideAgent: async (
    id: string,
    action: "pause" | "resume" | "request_correction",
    note: string
  ) =>
    decision(
      (
        await http.post<DecisionResult>(`/agents/${id}/decision`, {
          action,
          note,
        })
      ).data
    ),
  getProposal: async (id: string) =>
    (await http.get<Proposal>(`/proposals/${id}`)).data,
  decideProposal: async (
    id: string,
    action: "approve" | "reject",
    note: string
  ) =>
    decision(
      (
        await http.post<Proposal & DecisionResult>(
          `/proposals/${id}/decision`,
          { action, note }
        )
      ).data
    ),
}
