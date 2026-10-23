import { test, expect, type Page } from "@playwright/test"
import type { Workspace, AssessmentSession } from "../src/api/types"

async function login(page: Page, email: string) {
  await page.goto("/p01")
  await page.getByLabel("Email address").fill(email)
  await page.getByLabel("Password", { exact: true }).fill("demo1238")
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
  await expect(page).toHaveURL(/\/[stf]1$/)
}
async function workspace(page: Page): Promise<Workspace> {
  return page.evaluate(async () => {
    const response = await fetch("http://127.0.0.1:8101/api/v1/workspace", {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("lingopath-session")}`,
      },
    })
    if (!response.ok) throw new Error(`Workspace failed: ${response.status}`)
    return response.json()
  })
}
async function answerSession(page: Page, answer: string) {
  for (let i = 0; i < 8; i++) {
    const field = page.getByPlaceholder("Write your answer")
    if (!(await field.isVisible())) break
    const text = await page.getByText(/^Question \d+ of/).innerText()
    const next = Number(text.match(/Question (\d+)/)![1]) + 1
    await field.fill(answer)
    await page.getByRole("button", { name: "Submit answer" }).click()
    await expect(
      page.getByText(new RegExp(`^Question ${next} of`)).or(
        page.getByRole("heading", {
          name: /Assessment complete|Assessment submitted/,
        })
      )
    ).toBeVisible()
  }
}

test("teacher-directed assessment survives student refresh and finishes confirmed", async ({
  page,
  browser,
}) => {
  const errors: string[] = []
  page.on("pageerror", (e) => errors.push(e.message))
  await login(page, "emily.walker@example.com")
  await page.goto("/t2")
  await page.locator(".select-row").filter({ hasText: "Ivy Lin" }).click()
  await page
    .getByLabel("Focus", { exact: true })
    .fill("Browser evidence linking")
  await page.getByRole("button", { name: "Request assessment" }).click()
  await expect(page.locator(".toast")).toContainText(
    "Directed assessment created"
  )
  const context = await browser.newContext()
  const student = await context.newPage()
  student.on("pageerror", (e) => errors.push(e.message))
  await login(student, "ivy.lin@example.com")
  await student.goto("/s3")
  await student
    .getByRole("button", {
      name: /Continue teacher-directed assessment.*Browser evidence linking/,
    })
    .click()
  await student
    .getByPlaceholder("Write your answer")
    .fill(Array(16).fill("evidence").join(" "))
  await student.getByRole("button", { name: "Submit answer" }).click()
  await expect(student.getByText(/^Question 2 of/)).toBeVisible()
  await student.reload()
  await student
    .getByRole("button", {
      name: /Continue teacher-directed assessment.*Browser evidence linking/,
    })
    .click()
  await expect(student.getByText(/^Question 2 of/)).toBeVisible()
  await answerSession(student, Array(16).fill("evidence").join(" "))
  await expect(
    student.getByRole("heading", { name: "Assessment complete", exact: true })
  ).toBeVisible()
  await expect(
    student.getByText("Result confirmed", { exact: true })
  ).toBeVisible()
  expect((await workspace(student)).assessment_sessions).toHaveLength(0)
  expect(errors).toEqual([])
  await context.close()
})

test("provisional assessment becomes confirmed after teacher review", async ({
  page,
  browser,
}) => {
  await login(page, "ivy.lin@example.com")
  await page.goto("/s3")
  await page.getByRole("button", { name: "Start assessment" }).click()
  await expect(page.getByPlaceholder("Write your answer")).toBeVisible()
  const sid = (await workspace(page)).assessment_sessions![0].id
  await answerSession(page, "yes")
  await expect(
    page.getByText("Pending teacher review", { exact: true })
  ).toBeVisible()
  const context = await browser.newContext()
  const teacher = await context.newPage()
  await login(teacher, "emily.walker@example.com")
  const session: AssessmentSession = await page.evaluate(
    async (id) =>
      (
        await fetch(`http://127.0.0.1:8101/api/v1/assessments/${id}`, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem("lingopath-session")}`,
          },
        })
      ).json(),
    sid
  )
  const review = (await workspace(teacher)).reviews!.find(
    (r) => r.subject_id === session.result!.id
  )!
  await teacher.goto("/t4")
  await teacher.getByTestId(`review-${review.id}`).click()
  await teacher
    .getByPlaceholder("Record the reason for your decision")
    .fill("Reviewed the assessment evidence and confirmed the level.")
  await teacher.getByRole("button", { name: "Confirm result" }).click()
  await expect
    .poll(
      async () =>
        (await workspace(teacher)).reviews!.find((r) => r.id === review.id)!
          .status
    )
    .toBe("decided")
  await page.getByRole("button", { name: "Refresh result" }).click()
  await expect(
    page.getByText("Result confirmed", { exact: true })
  ).toBeVisible()
  await context.close()
})

test("private AI draft is shown to its reviewer and teacher text preserves newlines", async ({
  page,
  browser,
}) => {
  await login(page, "ivy.lin@example.com")
  await page.goto("/s6")
  const question =
    "Can I quote an unpublished interview without permission? Browser review."
  await page
    .getByPlaceholder("Can you explain this in another way?")
    .fill(question)
  await page.getByRole("button", { name: "Send", exact: true }).click()
  await expect
    .poll(async () =>
      (await workspace(page)).interactions?.some((i) => i.question === question)
    )
    .toBe(true)
  const interaction = (await workspace(page)).interactions!.find(
    (i) => i.question === question
  )!
  expect(interaction.answer).not.toContain("available sources do not establish")
  const context = await browser.newContext()
  const teacher = await context.newPage()
  await login(teacher, "emily.walker@example.com")
  const review = (await workspace(teacher)).reviews!.find(
    (r) => r.subject_id === interaction.id
  )!
  await teacher.goto("/t4")
  await teacher.getByTestId(`review-${review.id}`).click()
  await expect(
    teacher.getByRole("heading", { name: "AI draft (not sent)" })
  ).toBeVisible()
  await expect(
    teacher.getByRole("region", { name: "AI draft (not sent)" })
  ).toContainText("available sources do not establish")
  await teacher.goto("/t3")
  await expect(
    teacher.getByText("Student: Ivy Lin", { exact: true })
  ).toBeVisible()
  await teacher.goto("/t2")
  await teacher.locator(".select-row").filter({ hasText: "Ivy Lin" }).click()
  await teacher
    .getByRole("button", { name: "Review progress", exact: true })
    .click()
  const status = teacher.locator(".inline-status")
  await expect(status).toBeVisible()
  await expect(status).toHaveCSS("white-space", "pre-line")
  expect(await status.textContent()).toContain("\n")
  await context.close()
})

test("Founder pauses/resumes agents and confidence chart labels remain short", async ({
  page,
}) => {
  await login(page, "alex.hu@example.com")
  await page
    .getByPlaceholder("Explain why the agent should be paused or resumed")
    .fill("Regression check")
  const card = page
    .locator(".agent-card")
    .filter({ has: page.getByText("Teaching Assistant", { exact: true }) })
  await card.getByRole("button", { name: "Pause", exact: true }).click()
  await expect(
    card.getByRole("button", { name: "Resume", exact: true })
  ).toBeVisible()
  await card.getByRole("button", { name: "Resume", exact: true }).click()
  await expect(
    card.getByRole("button", { name: "Pause", exact: true })
  ).toBeVisible()
  for (const label of await page
    .locator(".confidence-bars span")
    .allTextContents())
    expect(label.length).toBeLessThanOrEqual(8)
})

test("Founder polls follow-up failure, links pending approval, and sends widen_match", async ({
  page,
}) => {
  await login(page, "alex.hu@example.com")
  const business = (await workspace(page)).operations!.cases.find(
    (c) => c.kind === "business"
  )!
  await page.route(`**/api/v1/cases/${business.id}`, (route) =>
    route.fulfill({
      json: {
        ...business,
        available_actions: ["widen_match"],
        status: "pending",
      },
    })
  )
  let action = ""
  let polls = 0
  await page.route(`**/api/v1/cases/${business.id}/decision`, (route) => {
    action = route.request().postDataJSON().action
    return route.fulfill({
      json: {
        ...business,
        follow_up: {
          id: "test-follow-up",
          type: "decision_follow_up",
          status: "queued",
          phase: "queued",
          result: {},
        },
      },
    })
  })
  await page.route("**/api/v1/requests/test-follow-up", (route) => {
    polls++
    return route.fulfill({
      json: {
        id: "test-follow-up",
        type: "decision_follow_up",
        status: polls === 1 ? "running" : "failed",
        phase: "execution",
        result: {},
        error: {
          code: "booking_failed",
          message: "No conflict-free lesson slots remain.",
        },
      },
    })
  })
  await page.goto("/f2")
  await page
    .getByPlaceholder("Record the reason and next action")
    .fill("Allow a broader subject match.")
  await page.getByRole("button", { name: "Widen teacher match" }).click()
  await expect(page.locator(".toast")).toContainText(
    "No conflict-free lesson slots remain."
  )
  expect(action).toBe("widen_match")
  expect(polls).toBe(2)
  await page.route("**/api/v1/agents/technical/decision", (route) =>
    route.fulfill({
      json: {
        follow_up: {
          id: "approval-test",
          type: "agent_correction",
          status: "pending_review",
          phase: "review",
          result: {},
        },
      },
    })
  )
  await page.goto("/f3")
  await page
    .getByPlaceholder("Explain the correction needed")
    .fill("Review the proposed correction.")
  await page
    .getByRole("button", { name: "Request correction", exact: true })
    .click()
  await expect(page.locator(".toast")).toContainText(
    "Waiting for human approval"
  )
  await page.getByRole("link", { name: "Review approvals →" }).click()
  await expect(page).toHaveURL("/f4")
})

test("saved goal keeps a visible placement entry after refresh and tracks assessment progress", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1366, height: 630 })
  await page.goto("/p02")
  await page.getByLabel("Full name").fill("Goal Flow Learner")
  await page
    .getByLabel("Email address")
    .fill(`goal-flow-${Date.now()}@example.com`)
  await page.getByLabel("Password", { exact: true }).fill("demo1238")
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click()
  await expect(page).toHaveURL("/s1")
  await expect(
    page.getByRole("link", { name: "Set learning goal", exact: true })
  ).toBeVisible()
  await page.goto("/s2")
  await page
    .getByPlaceholder("Describe your goal and needs")
    .fill(
      "I am preparing for a Master's degree in Philosophy. I need academic reading and writing. I can attend Tuesday and Thursday 18:00-20:00 Sydney time."
    )
  await page.getByRole("button", { name: "Reading", exact: true }).click()
  await page.getByRole("button", { name: "Writing", exact: true }).click()
  await page.getByLabel("Current level (self-assessed)").selectOption("B1")
  await page.getByLabel("Hours per week").fill("6")
  await page.getByRole("button", { name: "Organise my goal" }).click()
  await expect(page.getByRole("button", { name: "Confirm goal" })).toBeEnabled()
  await page.getByRole("button", { name: "Confirm goal" }).click()
  const saved = page.getByRole("region", {
    name: "Next step for your saved profile",
  })
  await expect(
    saved.getByRole("link", { name: "Start placement assessment" })
  ).toBeVisible()
  await page.reload()
  await expect(
    saved.getByRole("link", { name: "Start placement assessment" })
  ).toBeVisible()
  await expect(page.getByLabel("Hours per week")).toHaveValue("6")
  await page.goto("/s1")
  const next = page.getByRole("region", { name: "Your next step", exact: true })
  await expect(
    next.getByRole("link", { name: "Start placement assessment" })
  ).toBeInViewport({ ratio: 1 })
  await expect(page.getByText("Not assessed", { exact: true })).toBeVisible()
  await expect(
    page.getByText("Self-assessed: B1. Awaiting confirmed assessment.")
  ).toBeVisible()
  await expect(page.getByText("6 hours", { exact: true })).toBeVisible()
  await expect(page.getByText("Stage 0 of 0")).toHaveCount(0)
  await expect(page.getByText("0 hours", { exact: true })).toHaveCount(0)
  await expect(
    page.getByRole("link", { name: "Set learning goal", exact: true })
  ).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath("goal-next-step.png") })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth
    )
  ).toBe(true)
  await page.setViewportSize({ width: 1366, height: 630 })
  await next.getByRole("link", { name: "Start placement assessment" }).click()
  await page.getByRole("button", { name: "Start assessment" }).click()
  await expect(page.getByPlaceholder("Write your answer")).toBeVisible()
  await page.goto("/s1")
  await expect(
    next.getByRole("link", { name: "Continue assessment" })
  ).toBeVisible()
  await next.getByRole("link", { name: "Continue assessment" }).click()
  await page
    .getByRole("button", { name: /Continue initial assessment/ })
    .click()
  await expect(page.getByPlaceholder("Write your answer")).toBeVisible()
  await answerSession(page, "I don't know")
  await expect(
    page.getByText("Pending teacher review", { exact: true })
  ).toBeVisible()
  await page.goto("/s1")
  await expect(
    next.getByRole("link", { name: "View assessment status" })
  ).toBeVisible()
  await expect(page.getByText("Pending review", { exact: true })).toBeVisible()
  await expect(
    page.getByRole("link", { name: "Start placement assessment", exact: true })
  ).toHaveCount(0)
})

test("pending and active plans do not send students back to placement", async ({
  page,
}) => {
  await login(page, "sophia.chen@example.com")
  const next = page.getByRole("region", { name: "Your next step", exact: true })
  await expect(next).toContainText("Your plan is awaiting teacher approval")
  await expect(
    next.getByRole("link", { name: "View learning plan" })
  ).toBeVisible()
  await expect(
    page.getByRole("link", { name: "Start placement assessment", exact: true })
  ).toHaveCount(0)
  await login(page, "ivy.lin@example.com")
  await expect(next).toHaveCount(0)
  await expect(
    page.getByText("Your learning path", { exact: true })
  ).toBeVisible()
  await expect(page.locator(".stage-track .filled").first()).toBeVisible()
  await expect(
    page.getByRole("link", { name: "View lesson", exact: true })
  ).toBeVisible()
})

test("older corrected plans do not block revisions but newer pending plans do", async ({
  page,
}) => {
  await login(page, "ivy.lin@example.com")
  const data = await workspace(page)
  const record = data.students![data.user.id]
  const originalDraft = record.pending_plan!
  record.plan = { ...record.plan!, version: 2 }
  record.pending_plan = {
    ...originalDraft,
    version: 1,
    status: "changes_requested",
  }
  await page.route("**/api/v1/workspace", (route) =>
    route.fulfill({ json: data })
  )
  await page.goto("/s1")
  await expect(
    page.getByText(/Plan version 1 is with your teacher/)
  ).toHaveCount(0)
  await page.goto("/s4")
  await expect(
    page.getByRole("heading", {
      name: "Learning plan · Version 2",
      exact: true,
    })
  ).toBeVisible()
  await expect(
    page.getByText("Your approved plan is active.", { exact: true })
  ).toBeVisible()
  await expect(
    page.getByText("Version 1 is pending teacher review.", { exact: true })
  ).toHaveCount(0)
  const reason = page.getByPlaceholder("What changed, and why?")
  const submit = page.getByRole("button", {
    name: "Request revision",
    exact: true,
  })
  await expect(submit).toBeDisabled()
  await reason.fill(
    "I want more reading practice within my current weekly hours."
  )
  await expect(submit).toBeEnabled()
  // A genuinely newer draft must still stop duplicate revision submissions.
  record.pending_plan = {
    ...originalDraft,
    version: 3,
    status: "pending_review",
  }
  await page.reload()
  await reason.fill("Another change")
  await expect(
    page.getByText("Version 3 is pending teacher review.", { exact: true })
  ).toBeVisible()
  await expect(
    page.getByText(
      /Version 3 must be reviewed before you request another revision/
    )
  ).toBeVisible()
  await expect(submit).toBeDisabled()
})

test("student can revise again after teacher corrects and approves a plan", async ({
  page,
}) => {
  await login(page, "emily.walker@example.com")
  const teacherData = await workspace(page)
  const studentId = Object.keys(teacherData.students!).find(
    (id) => teacherData.students![id].name === "Sophia Chen"
  )!
  expect(studentId).toBeTruthy()
  async function selectPendingPlanReview() {
    const data = await workspace(page)
    const pending = data.students![studentId].pending_plan!
    const review = data.reviews!.find(
      (item) => item.subject_id === pending.id && item.status === "pending"
    )!
    expect(review).toBeTruthy()
    await page.goto("/t4")
    await page.getByTestId(`review-${review.id}`).click()
    await expect(
      page.getByText("Sophia Chen · plan", { exact: true }).last()
    ).toBeVisible()
  }
  await selectPendingPlanReview()
  await page
    .getByPlaceholder("Record the reason for your decision")
    .fill("Add clearer writing examples within the current weekly budget.")
  await page
    .getByRole("button", { name: "Request changes", exact: true })
    .click()
  await expect
    .poll(
      async () =>
        (await workspace(page)).students![studentId].pending_plan?.version
    )
    .toBe(2)
  await selectPendingPlanReview()
  await page
    .getByPlaceholder("Record the reason for your decision")
    .fill("The corrected plan is approved.")
  await page
    .getByRole("button", { name: "Approve & activate", exact: true })
    .click()
  await expect
    .poll(
      async () => (await workspace(page)).students![studentId].plan?.version
    )
    .toBe(2)
  expect((await workspace(page)).students![studentId].pending_plan).toBeNull()

  await login(page, "sophia.chen@example.com")
  await page.goto("/s4")
  await expect(
    page.getByRole("heading", {
      name: "Learning plan · Version 2",
      exact: true,
    })
  ).toBeVisible()
  await page
    .getByPlaceholder("What changed, and why?")
    .fill("Add more reading practice within my current weekly hours.")
  await page
    .getByRole("button", { name: "Request revision", exact: true })
    .click()
  await expect
    .poll(
      async () =>
        (await workspace(page)).students![studentId].pending_plan?.version
    )
    .toBe(3)
  await expect(
    page.getByText("Version 3 is pending teacher review.", { exact: true })
  ).toBeVisible()
  expect((await workspace(page)).students![studentId].plan?.version).toBe(2)
  await page
    .getByPlaceholder("What changed, and why?")
    .fill("Duplicate request")
  await expect(
    page.getByRole("button", { name: "Request revision", exact: true })
  ).toBeDisabled()

  await login(page, "emily.walker@example.com")
  await selectPendingPlanReview()
  await page
    .getByPlaceholder("Record the reason for your decision")
    .fill("Approve the requested reading revision.")
  await page
    .getByRole("button", { name: "Approve & activate", exact: true })
    .click()
  await expect
    .poll(
      async () => (await workspace(page)).students![studentId].plan?.version
    )
    .toBe(3)
  await login(page, "sophia.chen@example.com")
  await page.goto("/s4")
  await expect(
    page.getByRole("heading", {
      name: "Learning plan · Version 3",
      exact: true,
    })
  ).toBeVisible()
  await expect(
    page.getByText("Your approved plan is active.", { exact: true })
  ).toBeVisible()
  expect((await workspace(page)).students![studentId].pending_plan).toBeNull()
  await page
    .getByPlaceholder("What changed, and why?")
    .fill("Another change when needed")
  await expect(
    page.getByRole("button", { name: "Request revision", exact: true })
  ).toBeEnabled()
})
