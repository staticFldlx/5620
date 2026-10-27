import { test } from "node:test"
import assert from "node:assert/strict"
import { displayText } from "../src/lib/display-text.ts"

const id = "845a92fa-ff05-5629-9854-d5253f447b7f"
test("structured diagnosis preserves uncertainty, risk, recommendation and confidence", () => {
  const diagnosis = {
    probable_cause: "The cause is not confirmed.",
    explanation: "Recovery failed after 1 retry.",
    confidence: 0.68,
    risk_level: "critical",
    recommended_action: "request_founder_review",
  }
  const original = JSON.stringify(diagnosis)
  assert.equal(
    displayText(original),
    "Possible cause: The cause is not confirmed.\nExplanation: Recovery failed after 1 retry.\nConfidence: 68%\nRisk level: critical\nRecommended action: Request Founder review"
  )
  assert.equal(JSON.stringify(diagnosis), original)
})
test("legacy Python evidence keeps numbers, false values, null and quoted prose", () => {
  assert.equal(
    displayText(
      String.raw`{'tasks': 5, 'failure_rate': 0.4, 'verified': False, 'note': 'Teacher\'s note: True is text', 'result': None}`
    ),
    "Agent tasks: 5\nTask failure rate: 40%\nVerified: No\nNote: Teacher's note: True is text\nResult: Not provided"
  )
  assert.equal(
    displayText(
      `{'metrics': {'avg_duration_ms': 1500}, 'agents': ['teaching_support', 'planning']}`
    ),
    "Metrics: Average task duration (milliseconds): 1500\nAgents: 1. Teaching Assistant\n2. Course Consultant"
  )
})
test("record references show a known title while retaining original identifiers in data", () => {
  const refs = [{ id, label: "Teaching Assistant recovery" }]
  assert.equal(
    displayText(`Related incident: ${id}`, refs),
    "Related incident: Teaching Assistant recovery"
  )
  assert.equal(displayText(id), "Related record")
  assert.equal(refs[0].id, id)
})
test("configuration labels and recovery failures remain accurate", () => {
  assert.equal(
    displayText("Update teaching_support: timeout_seconds"),
    "Update Teaching Assistant: Response timeout (seconds)"
  )
  assert.equal(
    displayText("Update planning: timeout_seconds"),
    "Update Course Consultant: Response timeout (seconds)"
  )
  assert.equal(
    displayText("assessment: high_failure_rate"),
    "Assessment Agent: High task failure rate"
  )
  assert.equal(displayText("recovery_failed"), "Recovery failed")
})
test("ordinary prose, course codes, levels, links and numeric values are preserved", () => {
  const prose =
    "B2 · CAT-01 · 6 hours · 26 Oct. See https://example.com/learning_plan or first_name@example.com."
  assert.equal(displayText(prose), prose)
  assert.equal(
    displayText("Timeout is 0 seconds; approval is still required."),
    "Timeout is 0 seconds; approval is still required."
  )
})
test("invalid structured data is reported without evaluating it", () => {
  const output = displayText("{'value': globalThis.shouldNeverRun = true}")
  assert.match(output, /could not be displayed/)
  assert.equal(globalThis.shouldNeverRun, undefined)
})
