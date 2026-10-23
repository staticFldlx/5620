import { test, expect, type Page } from "@playwright/test"
import type { Workspace } from "../src/api/types"

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
async function submitShortAnswers(page: Page) {
  await expect(page.getByPlaceholder("Write your answer")).toBeVisible()
  for (let index = 0; index < 9; index++) {
    const field = page.getByPlaceholder("Write your answer")
    if (!(await field.isVisible())) return
    const question = await page.getByText(/^Question \d+ of/).innerText()
    const next = Number(question.match(/Question (\d+)/)![1]) + 1
    await field.fill("yes")
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
async function completeLesson(teacher: Page, title: string) {
  await teacher.goto("/t3")
  await teacher
    .locator(".list-row.interactive")
    .filter({ hasText: title })
    .click()
  await teacher.getByLabel("Attendance").selectOption("attended")
  await teacher
    .getByPlaceholder("Record teaching feedback")
    .fill("Lesson completed; ready for milestone review.")
  await teacher.getByRole("button", { name: "Save lesson record" }).click()
  await expect(teacher.locator(".toast")).toContainText("Lesson feedback saved")
}
async function correctResult(teacher: Page, student: Page, level: string) {
  const ws = await workspace(student)
  const sid = ws.user.id
  const record = ws.students[sid].assessments.at(-1)!
  const review = (await workspace(teacher)).reviews!.find(
    (r) => r.kind === "assessment" && r.subject_id === record.id
  )!
  await teacher.goto("/t4")
  await teacher.getByTestId(`review-${review.id}`).click()
  await teacher.getByLabel("Confirmed level (CEFR)").selectOption(level)
  await teacher
    .getByPlaceholder("Record the reason for your decision")
    .fill(
      `Observed work supports ${level}; confirmed after reviewing all evidence.`
    )
  await teacher.screenshot({
    path: test.info().outputPath(`teacher-correction-${level}.png`),
    fullPage: true,
  })
  await teacher
    .getByRole("button", { name: "Confirm corrected result" })
    .click()
  await expect
    .poll(
      async () =>
        (await workspace(teacher)).reviews!.find((r) => r.id === review.id)
          ?.status
    )
    .toBe("decided")
}

test("teacher revision creates a pending version and approval activates it", async ({
  page,
  browser,
}) => {
  const errors: string[] = []
  page.on("pageerror", (error) => errors.push(error.message))
  await login(page, "emily.walker@example.com")
  await page.goto("/t2")
  await page
    .locator(".select-row")
    .filter({ hasText: "Revision Learner" })
    .click()
  await page
    .getByLabel("Requested plan changes")
    .fill("Add guided reading practice to strengthen evidence identification.")
  await page.screenshot({
    path: test.info().outputPath("teacher-plan-revision.png"),
    fullPage: true,
  })
  await page.getByRole("button", { name: "Submit plan revision" }).click()
  await expect(
    page.getByText("Version 2 is awaiting review.", { exact: false })
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Submit plan revision" })
  ).toHaveCount(0)
  const ws = await workspace(page)
  const sid = Object.keys(ws.students).find(
    (id) => ws.students[id].name === "Revision Learner"
  )!
  expect(ws.students[sid].plan?.version).toBe(1)
  const pending = ws.students[sid].pending_plan!
  const context = await browser.newContext()
  const student = await context.newPage()
  await login(student, "revision@test.example")
  await student.goto("/s4")
  await expect(
    student.getByText("Awaiting teacher review · Version 2")
  ).toBeVisible()
  await page.goto("/t4")
  await page.getByTestId(`review-${pending.review_id}`).click()
  await page
    .getByPlaceholder("Record the reason for your decision")
    .fill("Reviewed revised curriculum and approved.")
  await page.getByRole("button", { name: "Approve & activate" }).click()
  await expect
    .poll(async () => (await workspace(page)).students[sid].plan?.version)
    .toBe(2)
  await student.reload()
  await expect(
    student.getByRole("heading", { name: /Learning plan · Version 2/i })
  ).toBeVisible()
  expect(errors).toEqual([])
  await context.close()
})

test("automatic milestones, corrected levels, stage advancement and final completion", async ({
  page,
  browser,
}) => {
  const errors: string[] = []
  page.on("pageerror", (error) => errors.push(error.message))
  await login(page, "emily.walker@example.com")
  const context = await browser.newContext()
  const student = await context.newPage()
  student.on("pageerror", (error) => errors.push(error.message))
  await login(student, "progress@test.example")
  for (const number of [1, 2]) {
    await completeLesson(page, `Progress checkpoint lesson ${number}`)
    await expect
      .poll(async () => (await workspace(student)).assessment_sessions?.length)
      .toBe(1)
    await student.goto("/s3")
    await student
      .getByRole("button", { name: /Continue milestone assessment/ })
      .click()
    await submitShortAnswers(student)
    await expect(
      student.getByText("Pending teacher review", { exact: true })
    ).toBeVisible()
    const before = await workspace(student)
    expect(before.students[before.user.id].plan?.stage_index).toBe(number - 1)
    await correctResult(page, student, "B2")
    await expect
      .poll(async () => {
        const ws = await workspace(student)
        return ws.students[ws.user.id].plan?.stages[number - 1].status
      })
      .toBe("completed")
    await student.goto("/s4")
    await expect(
      student.getByText(
        number === 1
          ? /Stage 1 completed; Stage 2 is current/
          : /All plan stages are complete/
      )
    ).toBeVisible()
    const ws = await workspace(student)
    expect(ws.students[ws.user.id].plan?.version).toBe(1)
    expect(ws.students[ws.user.id].pending_plan).toBeNull()
  }
  await expect(
    student.getByText("Your learning plan is complete.", { exact: true })
  ).toBeVisible()
  await expect(
    student.getByRole("button", { name: "Request revision" })
  ).toHaveCount(0)
  await student.goto("/s1")
  await expect(student.getByText("Completed", { exact: true })).toBeVisible()
  await student.goto("/s4")
  await student.screenshot({
    path: test.info().outputPath("completed-plan.png"),
    fullPage: true,
  })
  expect(errors).toEqual([])
  await context.close()
})

test("below-target result keeps the stage and submits one reviewable revision", async ({
  page,
  browser,
}) => {
  await login(page, "emily.walker@example.com")
  // Editing an existing absence must not silently change it to attendance.
  await page.goto("/t3")
  await page
    .locator(".list-row.interactive")
    .filter({ hasText: "Deviation checkpoint lesson 2" })
    .click()
  await page.getByLabel("Attendance").selectOption("absent")
  await page
    .getByPlaceholder("Record teaching feedback")
    .fill("Student absent; arrange follow-up.")
  await page.getByRole("button", { name: "Save lesson record" }).click()
  await expect(page.locator(".toast")).toContainText("Lesson feedback saved")
  await page
    .locator(".list-row.interactive")
    .filter({ hasText: "Deviation checkpoint lesson 1" })
    .click()
  await page
    .locator(".list-row.interactive")
    .filter({ hasText: "Deviation checkpoint lesson 2" })
    .click()
  await expect(page.getByLabel("Attendance")).toHaveValue("absent")
  await completeLesson(page, "Deviation checkpoint lesson 1")
  const context = await browser.newContext()
  const student = await context.newPage()
  await login(student, "deviation@test.example")
  await expect
    .poll(async () => (await workspace(student)).assessment_sessions?.length)
    .toBe(1)
  await student.goto("/s3")
  await student
    .getByRole("button", { name: /Continue milestone assessment/ })
    .click()
  await submitShortAnswers(student)
  await correctResult(page, student, "B1")
  await expect
    .poll(async () => {
      const ws = await workspace(student)
      return ws.students[ws.user.id].pending_plan?.version
    })
    .toBe(2)
  const ws = await workspace(student)
  expect(ws.students[ws.user.id].plan?.version).toBe(1)
  expect(ws.students[ws.user.id].plan?.stage_index).toBe(0)
  await student.goto("/s4")
  await expect(
    student.getByText(/Plan review required: confirmed level B1/)
  ).toBeVisible()
  await expect(
    student.getByText("Awaiting teacher review · Version 2")
  ).toBeVisible()
  await context.close()
})
