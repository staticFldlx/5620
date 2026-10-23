import { defineConfig } from "@playwright/test"
import base from "./playwright.config"
export default defineConfig({
  ...base,
  testMatch: "assessment-history.spec.ts",
})
