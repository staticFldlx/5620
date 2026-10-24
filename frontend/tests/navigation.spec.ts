import { test, expect, type Page } from "@playwright/test"

async function login(page: Page, email = "ivy.lin@example.com") {
  await page.goto("/p01")
  await page.getByLabel("Email address").fill(email)
  await page.getByLabel("Password", { exact: true }).fill("demo1238")
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
  await expect(page).toHaveURL(/\/[stf]1$/)
  await page.evaluate(() => document.fonts.ready)
}

test("desktop precision workspace keeps navigation and sign out accessible", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await login(page)
  await expect(page.locator("aside.sidebar")).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Open navigation menu" })
  ).toHaveCount(0)
  await expect(
    page.getByRole("navigation", { name: "Student workspace" })
  ).toBeVisible()
  const sidebar = await page.locator("aside.sidebar").boundingBox()
  const header = await page.locator(".topbar").boundingBox()
  expect(sidebar!.width).toBe(190)
  expect(header!.x).toBe(190)
  await expect(page.getByRole("button", { name: "Sign out" })).toBeInViewport()
})

for (const width of [320, 390, 660, 760]) {
  test(`mobile menu at ${width}px supports navigation and dismissal`, async ({
    page,
  }) => {
    const errors: string[] = []
    page.on("pageerror", (error) => errors.push(error.message))
    await page.setViewportSize({ width, height: 740 })
    await login(page)
    const trigger = page.getByRole("button", { name: "Open navigation menu" })
    const dialog = page.getByRole("dialog", { name: "Navigation menu" })
    await expect(page.getByRole("navigation")).toHaveCount(0)
    await trigger.click()
    await expect(dialog).toBeVisible()
    const links = dialog.getByRole("navigation").getByRole("link")
    await expect(links).toHaveCount(7)
    const bounds = await links.evaluateAll((nodes) =>
      nodes.map((node) => ({
        y: node.getBoundingClientRect().y,
        font: parseFloat(getComputedStyle(node).fontSize),
      }))
    )
    expect(
      bounds.every((b, i) => b.font >= 16 && (!i || b.y > bounds[i - 1].y))
    ).toBe(true)
    const box = await dialog.boundingBox()
    expect(box!.x).toBe(0)
    expect(box!.width).toBeLessThan(width)
    await expect(
      dialog.getByRole("button", { name: "Sign out" })
    ).toBeInViewport()
    await page.screenshot({
      path: test.info().outputPath(`mobile-${width}.png`),
    })
    await page.keyboard.press("Tab")
    expect(
      await dialog.evaluate((node) => node.contains(document.activeElement))
    ).toBe(true)
    await page.keyboard.press("Escape")
    await expect(dialog).toHaveCount(0)
    await expect(trigger).toBeFocused()
    await trigger.click()
    await expect(dialog).toBeVisible()
    await page
      .locator(".mobile-menu-overlay")
      .click({ position: { x: width - 25, y: 350 } })
    await expect(dialog).toHaveCount(0)
    await trigger.click()
    await dialog.getByRole("button", { name: "Close navigation menu" }).click()
    await expect(dialog).toHaveCount(0)
    await trigger.click()
    await dialog
      .getByRole("link", { name: "Learning goal", exact: true })
      .click()
    await expect(page).toHaveURL(/\/s2$/)
    await expect(dialog).toHaveCount(0)
    const header = await page.locator(".topbar").boundingBox()
    expect(header!.x + header!.width).toBeLessThanOrEqual(width)
    expect(errors).toEqual([])
  })
}

test("short mobile viewport keeps sign out accessible and releases drawer on resize", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 420 })
  await login(page)
  const trigger = page.getByRole("button", { name: "Open navigation menu" })
  await trigger.click()
  await expect(page.getByRole("button", { name: "Sign out" })).toBeInViewport()
  await page.getByRole("link", { name: "Learning record", exact: true }).click()
  await expect(page).toHaveURL(/\/s8$/)
  await trigger.click()
  await page.setViewportSize({ width: 1440, height: 900 })
  await expect(page.getByRole("dialog")).toHaveCount(0)
  await expect(trigger).toHaveCount(0)
  await expect(page.locator("aside.sidebar")).toBeVisible()
  await expect(page.locator("body")).not.toHaveAttribute("data-scroll-locked")
  await page.setViewportSize({ width: 390, height: 740 })
  await expect(page.getByRole("dialog")).toHaveCount(0)
  await trigger.click()
  await page.getByRole("button", { name: "Sign out" }).click()
  await expect(page).toHaveURL(/\/p01$/)
})

for (const [email, label, path] of [
  ["emily.walker@example.com", "Teaching preparation", "/t5"],
  ["alex.hu@example.com", "Approvals & audit", "/f4"],
]) {
  test(`${email} uses the same mobile drawer with role-specific links`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 740 })
    await login(page, email)
    await page.getByRole("button", { name: "Open navigation menu" }).click()
    await page
      .getByRole("dialog")
      .getByRole("link", { name: label, exact: true })
      .click()
    await expect(page).toHaveURL(new RegExp(path + "$"))
    await expect(page.getByRole("dialog")).toHaveCount(0)
  })
}
