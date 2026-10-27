import { test, expect } from "@playwright/test"

test("homepage cycles every six seconds without playback controls and opens real auth routes", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "no-preference" })
  await page.clock.install()
  await page.goto("/")
  await expect(page.locator(".landing")).toHaveAttribute("data-scene", "book")
  await page.clock.fastForward(6500)
  await expect(page.locator(".landing")).toHaveAttribute("data-scene", "plan")
  await expect(page.locator(".landing-motion")).toHaveCount(0)
  await expect(page.locator(".landing-bottom")).toHaveCount(0)
  await page.clock.fastForward(6500)
  await expect(page.locator(".landing")).toHaveAttribute(
    "data-scene",
    "conversation"
  )
  await page.getByRole("link", { name: "Get started" }).click()
  await expect(page).toHaveURL(/\/p01$/)
  await expect(page.getByLabel("Email address")).toBeVisible()
  await page.getByRole("link", { name: "Create a student account" }).click()
  await expect(page).toHaveURL(/\/p02$/)
  await expect(page.getByLabel("Full name")).toBeVisible()
})

test("reduced motion keeps the homepage still", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await page.goto("/")
  await expect(page.locator(".landing-motion")).toHaveCount(0)
  await expect(page.locator(".landing")).toHaveAttribute("data-scene", "book")
})

for (const width of [320, 390, 1024]) {
  test(`public pages fit at ${width}px and use English`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    for (const path of ["/", "/p01", "/p02", "/workspaces"]) {
      await page.goto(path)
      const size = await page.locator("body").evaluate((el) => ({
        width: el.clientWidth,
        scroll: el.scrollWidth,
        text: el.innerText,
      }))
      expect(size.scroll).toBeLessThanOrEqual(size.width)
      expect(size.text).not.toMatch(/[\u4e00-\u9fff]/)
    }
  })
}

test("student overview expands existing lesson content and learning stages", async ({
  page,
}) => {
  await page.goto("/p01")
  await page.getByLabel("Email address").fill("ivy.lin@example.com")
  await page.getByLabel("Password", { exact: true }).fill("demo1238")
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
  await expect(page).toHaveURL(/\/s1$/)
  await page.getByRole("button", { name: "Expand lesson actions" }).click()
  await expect(
    page.getByRole("region", { name: "Lesson quick actions" })
  ).toBeVisible()
  await page.getByRole("button", { name: "Materials", exact: true }).click()
  await expect(page.locator("#overview-lesson-actions")).toContainText(
    "Approved materials"
  )
  await page.getByRole("button", { name: /Academic Argument Guide/ }).click()
  await expect(page.locator("#overview-lesson-actions")).toContainText(
    "A claim tells the reader"
  )
  const stage = page
    .locator(".path-stage")
    .filter({ hasText: "Academic foundations" })
  await stage.locator("summary").click()
  await expect(stage.locator(".path-stage-detail")).toBeVisible()
  await page.getByRole("link", { name: "Change time", exact: true }).click()
  await expect(page).toHaveURL(/\/s5$/)
  await expect(
    page.getByRole("heading", { name: "Change this time" })
  ).toBeVisible()
})
