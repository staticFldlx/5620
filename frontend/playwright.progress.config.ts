import { defineConfig } from "@playwright/test"
import base from "./playwright.config"
export default defineConfig({
  ...base,
  use: { ...base.use, actionTimeout: 15000 },
  testMatch: "progress.spec.ts",
  webServer: (Array.isArray(base.webServer) ? base.webServer : []).map(
    (server, index) =>
      index === 0
        ? { ...server, env: { ...server.env, E2E_PROGRESS_SCENARIOS: "true" } }
        : server
  ),
})
