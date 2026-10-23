import { defineConfig } from "@playwright/test"
export default defineConfig({
  testDir: "./tests",
  testMatch: "mock.spec.ts",
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  use: {
    baseURL: "http://127.0.0.1:5275",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5275 --strictPort",
    url: "http://127.0.0.1:5275",
    reuseExistingServer: false,
    env: { VITE_USE_MOCK_API: "true", VITE_API_BASE_URL: "/api/v1" },
  },
})
