import { defineConfig, devices } from "@playwright/test";

/**
 * `retries: 2` was already here, which meant a test that
 * failed once and passed on the second attempt was reported as a pass and the
 * flake left no trace. A journey can be flaky for months that way.
 *
 * The retry count stays at two, deliberately: these journeys drive a real
 * browser against a real dev server, and a cold first paint on a loaded runner
 * is a genuine environmental failure rather than a defect. Zero retries would
 * make CI a coin flip; more than two would hide a test that fails half the
 * time.
 *
 * What changes is that a flake is now recorded. The JSON reporter writes every
 * attempt to `playwright-report/results.json`, which CI uploads, so a run that
 * "passed" can still be inspected for tests that needed a second go.
 *
 * The policy: a test that appears in the flaky list twice in a fortnight is a
 * broken test, not an unlucky one. Fix it or delete it -- a journey nobody
 * trusts is worse than no journey, because it trains people to re-run CI
 * without reading the failure.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI
    ? [
        ["github"],
        ["json", { outputFile: "playwright-report/results.json" }],
        // Prints a "flaky" section that the github reporter folds away.
        ["list"],
      ]
    : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "corepack pnpm dev --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: "desktop-chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 7"] },
    },
  ],
});
