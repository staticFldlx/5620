import { test } from "node:test"
import assert from "node:assert/strict"
import { requestFeedback } from "../src/api/request-feedback.ts"
const envelope = (status, extra = {}) => ({
  id: "saved-request",
  type: "decision_follow_up",
  phase: status,
  status,
  result: {},
  ...extra,
})
test("HTTP success with failed execution must surface the backend reason", () => {
  assert.match(
    requestFeedback({
      follow_up: envelope("failed", {
        error: { code: "boom", message: "Recovery failed" },
      }),
    }).message,
    /Recovery failed/
  )
})
test("Queued, human approval, escalation and next-item states are not treated alike", () => {
  assert.match(
    requestFeedback({ follow_up: envelope("queued") }).message,
    /still processing/
  )
  assert.equal(
    requestFeedback({ follow_up: envelope("pending_review") }).approvals,
    true
  )
  assert.match(requestFeedback(envelope("escalated")).message, /human review/)
  assert.equal(
    requestFeedback(envelope("awaiting_confirmation", { phase: "next_item" })),
    null
  )
  assert.equal(requestFeedback({ follow_up: envelope("completed") }), null)
  assert.equal(requestFeedback({ review: {} }), null)
})

test("waiting messages do not expose request identifiers or alter the envelope", () => {
  const request = envelope("queued", {
    id: "845a92fa-ff05-5629-9854-d5253f447b7f",
  })
  const original = JSON.stringify(request)
  assert.doesNotMatch(requestFeedback(request).message, /845a92fa/)
  assert.equal(JSON.stringify(request), original)
})
