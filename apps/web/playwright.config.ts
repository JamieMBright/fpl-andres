import { defineConfig, devices } from "@playwright/test";

const PREVIEW = process.env.FPL_ANDRES_TEST_PREVIEW === "1";
const PORT = PREVIEW ? 4174 : 4173;

/**
 * A smoke suite, not a second test pyramid.
 *
 * This used to run 212 journeys across two browser projects for four to six
 * minutes, most of them re-proving in a real browser what a component test
 * already proves in milliseconds. `e2e/smoke.spec.ts` now holds the handful
 * that only a browser can answer, and one project runs them: a second engine
 * doubled the bill and never once caught something the first missed.
 *
 * `retries: 2` stays. These drive a real browser against a real dev server,
 * and a cold first paint on a loaded runner is an environmental failure rather
 * than a defect. The JSON reporter still records every attempt, so a run that
 * "passed" can be inspected for tests that needed a second go.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 2,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI
    ? [
        ["github"],
        ["json", { outputFile: "playwright-report/results.json" }],
        ["list"],
      ]
    : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: PREVIEW
      ? `corepack pnpm exec vite preview --host 127.0.0.1 --port ${PORT}`
      : `corepack pnpm dev --host 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
});
