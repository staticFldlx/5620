import { defineConfig } from "@playwright/test"
const python =
  process.platform === "win32"
    ? "../backend/.venv/Scripts/python.exe"
    : "../backend/.venv/bin/python"
export default defineConfig({
  testDir: "./tests",
  testMatch: "regressions.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 90000,
  expect: { timeout: 15000 },
  use: {
    baseURL: "http://127.0.0.1:5274",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `${python} tests/backend_server.py`,
      url: "http://127.0.0.1:8101/api/v1/docs",
      timeout: 60000,
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 10000 },
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5274 --strictPort",
      url: "http://127.0.0.1:5274",
      reuseExistingServer: false,
      env: {
        VITE_USE_MOCK_API: "false",
        VITE_API_BASE_URL: "http://127.0.0.1:8101/api/v1",
      },
    },
  ],
})
