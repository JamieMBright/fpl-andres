import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke tests against a real deployment.
 *
 * The ordinary suite drives the Vite dev server, which serves `/api/*` from a
 * plugin that calls the handler libraries directly. Production routes the same
 * paths through Vercel's filesystem router to `api/**` instead. Nothing in the
 * repository exercised that second path, so a routing mistake was invisible to
 * every test and visible to every visitor: `/api/fpl/*` returned 404 in
 * production for days while the suite stayed green.
 *
 * These run against a URL rather than a server this config starts, because the
 * thing under test is the deployment.
 *
 *     FPL_ANDRES_BASE_URL=https://… corepack pnpm test:deployed
 */
const baseURL = process.env.FPL_ANDRES_BASE_URL;

export default defineConfig({
  testDir: "./e2e-deployed",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 1,
  reporter: "list",
  use: {
    ...(baseURL ? { baseURL } : {}),
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "deployed",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
});
