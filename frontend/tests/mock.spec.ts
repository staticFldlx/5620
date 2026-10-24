import { test, expect, type Page } from "@playwright/test"
async function login(page: Page, email: string) {
  await page.goto("/p01")
  await page.getByLabel("Email address").fill(email)
  await page.getByLabel("Password", { exact: true }).fill("demo1238")
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
  await expect(page).toHaveURL(/\/[stf]1$/)
}
test("offline demo retains directed assessments and agent controls", async ({
  page,
}) => {
  const errors: string[] = []
  page.on("pageerror", (error) => errors.push(error.message))
  await login(page, "emily.walker@example.com")
  await page.goto("/t2")
  await page.locator(".select-row").filter({ hasText: "Ivy Lin" }).click()
  await page.getByLabel("Focus", { exact: true }).fill("Offline regression")
  await page.getByRole("button", { name: "Request assessment" }).click()
  await expect(page.locator(".toast")).toContainText(
    "Directed assessment created"
  )
  await page.getByRole("button", { name: "Sign out" }).click()
  await login(page, "ivy.lin@example.com")
  await page.goto("/s3")
  await page
    .getByRole("button", {
      name: /Continue teacher-directed assessment.*Offline regression/,
    })
    .click()
  await page
    .getByPlaceholder("Write your answer")
    .fill("A claim needs supporting evidence.")
  await page.getByRole("button", { name: "Submit answer" }).click()
  await expect(page.getByText("Question 2 of 3")).toBeVisible()
  await page.reload()
  await page
    .getByRole("button", {
      name: /Continue teacher-directed assessment.*Offline regression/,
    })
    .click()
  await expect(page.getByText("Question 2 of 3")).toBeVisible()
  await page.getByRole("button", { name: "Sign out" }).click()
  await login(page, "alex.hu@example.com")
  await page
    .getByPlaceholder("Explain why the agent should be paused or resumed")
    .fill("Offline demo check")
  const card = page
    .locator(".agent-card")
    .filter({ has: page.getByText("Teaching Assistant", { exact: true }) })
  await card.getByRole("button", { name: "Pause agent", exact: true }).click()
  await expect(
    card.getByRole("button", { name: "Resume agent", exact: true })
  ).toBeVisible()
  await card.getByRole("button", { name: "Resume agent", exact: true }).click()
  await expect(
    card.getByRole("button", { name: "Pause agent", exact: true })
  ).toBeVisible()
  expect(errors).toEqual([])
})
