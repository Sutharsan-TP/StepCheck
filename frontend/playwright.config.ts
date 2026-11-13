import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run the real backend with the deterministic offline AI stub
// (STEPCHECK_STUB_AI=true), so no API key or network access is needed.
// Override with E2E_BACKEND_PORT / E2E_FRONTEND_PORT if these are taken.
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8765);
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3100);
const backendDir = resolve(__dirname, "../backend");
const python = [join(backendDir, ".venv/Scripts/python.exe"), join(backendDir, ".venv/bin/python")].find(existsSync) ?? "python";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e/.artifacts/results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  // Generous: `next dev` compiles pages on first visit and the machine may be busy.
  timeout: 120_000,
  expect: { timeout: 45_000 },
  globalSetup: "./e2e/global-setup.ts",
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: backendDir,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        STEPCHECK_STUB_AI: "true",
        CORS_ORIGINS: `http://127.0.0.1:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}`,
        OPENROUTER_API_KEY: "",
      },
    },
    {
      command: `npx next dev --port ${FRONTEND_PORT} --hostname 127.0.0.1`,
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { NEXT_PUBLIC_API_URL: `http://127.0.0.1:${BACKEND_PORT}` },
    },
  ],
});
