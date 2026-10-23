import { defineConfig } from "@playwright/test"
import base from "./playwright.mock.config"
export default defineConfig({
  ...base,
  testMatch: "navigation.spec.ts",
  use: { ...base.use, actionTimeout: 10000 },
})
