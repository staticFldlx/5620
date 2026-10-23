import { test, expect, type Page } from "@playwright/test"
import type { AssessmentSession, Workspace } from "../src/api/types"

async function login(page: Page, email: string) {
  await page.goto("/p01")
  await page.getByLabel("Email address").fill(email)
  await page.getByLabel("Password", { exact: true }).fill("demo1238")
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
  await expect(page).toHaveURL(/\/[stf]1$/)
}
async function get<T>(page: Page, path: string): Promise<T> {
  return page.evaluate(async (path) => {
    const response = await fetch(`http://127.0.0.1:8101/api/v1${path}`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("lingopath-session")}`,
      },
    })
    if (!response.ok) throw new Error(`Read failed: ${response.status}`)
    return response.json()
  }, path)
}

test("student and teacher can revisit identical saved questions and answers, including after review", async ({
  page,
  browser,
}) => {
  const errors: string[] = []
  page.on("pageerror", (error) => errors.push(error.message))
  await login(page, "ivy.lin@example.com")
  await page.goto("/s3")
  await page.getByRole("button", { name: "Start assessment" }).click()
  await expect(page.getByPlaceholder("Write your answer")).toBeVisible()
  const workspace = await get<Workspace>(page, "/workspace")
  const sid = workspace.assessment_sessions![0].id
  const answer = "yes\n"
  const saved: { prompt: string; answer: string }[] = []
  for (let i = 0; i < 8; i++) {
    const session = await get<AssessmentSession>(page, `/assessments/${sid}`)
    if (session.status !== "in_progress") break
    await expect(
      page.getByRole("heading", { name: session.current_item, exact: true })
    ).toBeVisible()
    saved.push({ prompt: session.current_item, answer })
    await page.getByPlaceholder("Write your answer").fill(answer)
    await page.getByRole("button", { name: "Submit answer" }).click()
    await expect(
      page
        .getByText(new RegExp(`^Question ${session.answered + 2} of`))
        .or(
          page.getByRole("heading", {
            name: /Assessment complete|Assessment submitted/,
          })
        )
    ).toBeVisible()
  }
  const completed = await get<AssessmentSession>(page, `/assessments/${sid}`)
  expect(completed.responses).toEqual(
    saved.map((item, index) => ({ number: index + 1, ...item }))
  )
  expect(completed.result?.status).toBe("pending_review")
  await page.reload()
  const card = page
    .locator(".record-card")
    .filter({ has: page.locator(".assessment-answers") })
    .last()
  // A failed read offers retry without changing the saved assessment.
  let failOnce = true
  await page.route(
    `**/api/v1/assessments/${completed.result!.id}`,
    async (route) => {
      if (failOnce) {
        failOnce = false
        await route.fulfill({
          status: 503,
          json: { message: "Temporary failure" },
        })
      } else await route.continue()
    }
  )
  await card
    .getByRole("button", { name: "View questions & answers", exact: true })
    .click()
  await expect(card.getByRole("alert")).toContainText("Could not load")
  await card.getByRole("button", { name: "Retry", exact: true }).click()
  const evidence = page.getByRole("region", {
    name: "Assessment questions and answers",
  })
  await expect(evidence.locator("article")).toHaveCount(saved.length)
  for (const [i, item] of saved.entries()) {
    await expect(evidence.locator("article").nth(i)).toContainText(item.prompt)
    await expect(evidence.locator("article").nth(i)).toContainText(item.answer)
  }
  await expect(evidence.locator("em")).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await evidence.scrollIntoViewIfNeeded()
  await page.screenshot({
    path: test.info().outputPath("student-answer-history.png"),
  })

  const context = await browser.newContext()
  const teacher = await context.newPage()
  teacher.on("pageerror", (error) => errors.push(error.message))
  await login(teacher, "emily.walker@example.com")
  const teacherWorkspace = await get<Workspace>(teacher, "/workspace")
  const review = teacherWorkspace.reviews!.find(
    (item) => item.subject_id === completed.result!.id
  )!
  await teacher.goto("/t4")
  await teacher.getByTestId(`review-${review.id}`).click()
  await teacher
    .getByRole("button", { name: "View questions & answers", exact: true })
    .click()
  const teacherEvidence = teacher.getByRole("region", {
    name: "Assessment questions and answers",
  })
  await expect(teacherEvidence.locator("article")).toHaveCount(saved.length)
  await expect(teacherEvidence.locator("article").first()).toContainText(
    saved[0].prompt
  )
  await expect(teacherEvidence.locator("article").first()).toContainText(answer)
  await teacher
    .getByPlaceholder("Record the reason for your decision")
    .fill("Checked the original questions and submitted answers.")
  await teacher
    .getByRole("button", { name: "Confirm result", exact: true })
    .click()
  await expect(teacher.getByTestId(`review-${review.id}`)).toContainText(
    "decided"
  )
  await expect(teacherEvidence.locator("article")).toHaveCount(saved.length)
  await teacher.goto("/t2")
  await teacher.locator(".select-row").filter({ hasText: "Ivy Lin" }).click()
  await teacher
    .getByRole("button", { name: "View questions & answers", exact: true })
    .last()
    .click()
  await expect(teacherEvidence.locator("article")).toHaveCount(saved.length)
  await teacher.reload()
  await teacher
    .getByRole("button", { name: "View questions & answers", exact: true })
    .last()
    .click()
  await expect(teacherEvidence.locator("article").first()).toContainText(answer)
  await teacher.locator(".select-row").filter({ hasText: "Sophia" }).click()
  await expect(teacherEvidence).toHaveCount(0)
  expect(errors).toEqual([])
  await context.close()
})

test("old evaluations without saved question details show an honest empty state", async ({
  page,
}) => {
  await login(page, "ivy.lin@example.com")
  await page.goto("/s3")
  await page.route("**/api/v1/assessments/*", async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    await route.fulfill({ response, json: { ...data, responses: [] } })
  })
  await page
    .getByRole("button", { name: "View questions & answers", exact: true })
    .first()
    .click()
  await expect(
    page.getByRole("region", { name: "Assessment questions and answers" })
  ).toContainText("No saved question-and-answer details")
})
