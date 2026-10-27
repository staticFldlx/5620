import type { RequestEnvelope } from "./types"
export function requestFeedback(
  value: unknown
): { message: string; approvals?: boolean } | null {
  if (!value || typeof value !== "object") return null
  const envelope =
    "follow_up" in value
      ? value.follow_up
      : "phase" in value && "result" in value
        ? value
        : null
  if (!envelope || typeof envelope !== "object" || !("status" in envelope))
    return null
  const request = envelope as RequestEnvelope
  if (request.status === "failed")
    return {
      message: `Follow-up failed: ${request.error?.message || "The request could not be completed."}`,
    }
  if (["queued", "running"].includes(request.status))
    return {
      message:
        "Your request is still processing. Refresh its status before retrying.",
    }
  if (request.status === "pending_review")
    return {
      message: "Saved. Waiting for human approval before execution.",
      approvals: true,
    }
  if (request.status === "escalated")
    return { message: "Sent for human review. Further action is pending." }
  if (
    request.status === "awaiting_confirmation" &&
    request.phase !== "next_item"
  )
    return { message: "Waiting for your response or confirmation." }
  return null
}
