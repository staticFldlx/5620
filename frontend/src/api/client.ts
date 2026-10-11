import axios from "axios"
import type {
  Availability,
  Case,
  Lesson,
  Material,
  Proposal,
  RequestEnvelope,
  RequestType,
  Review,
  User,
  Workspace,
} from "./types"

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 10000,
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
    (
      await http.post<RequestEnvelope>("/requests", {
        type,
        input,
        student_id: studentId,
        context_id: contextId,
      })
    ).data,
  getRequest: async (id: string) =>
    (await http.get<RequestEnvelope>(`/requests/${id}`)).data,
  startAssessment: async (
    studentId: string,
    kind: "initial" | "milestone" | "directed",
    focus?: string
  ) =>
    (
      await http.post<{
        id: string
        current_item: string
        answered: number
        max_items: number
        status: string
      }>("/assessments", { student_id: studentId, kind, focus })
    ).data,
  getAssessment: async (id: string) =>
    (await http.get(`/assessments/${id}`)).data,
  answerAssessment: async (id: string, itemId: string, answer: string) =>
    (
      await http.post<{
        status: string
        current_item?: string
        result?: unknown
      }>(`/assessments/${id}/answers`, { item_id: itemId, answer })
    ).data,
  getReview: async (id: string) =>
    (
      await http.get<{ review: Review; subject: unknown; evidence: string }>(
        `/reviews/${id}`
      )
    ).data,
  decideReview: async (
    id: string,
    action: "approve" | "request_changes" | "confirm_result" | "answer",
    note: string
  ) => (await http.post(`/reviews/${id}/decision`, { action, note })).data,
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
    (await http.post(`/cases/${id}/decision`, { action, note })).data,
  decideAgent: async (id: string, action: "request_correction", note: string) =>
    (await http.post(`/agents/${id}/decision`, { action, note })).data,
  getProposal: async (id: string) =>
    (await http.get<Proposal>(`/proposals/${id}`)).data,
  decideProposal: async (
    id: string,
    action: "approve" | "reject",
    note: string
  ) => (await http.post(`/proposals/${id}/decision`, { action, note })).data,
}
