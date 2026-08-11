import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * Does the deployment actually serve what the dev server pretends it does?
 *
 * Every one of these failed silently in production while the ordinary suite
 * passed, because the dev server answers `/api/*` from a Vite plugin that
 * imports the handler libraries directly and never goes near Vercel's
 * filesystem router. A function that is not routed is a 404 nobody sees until
 * somebody opens the page.
 *
 * Skipped unless `FPL_ANDRES_BASE_URL` names a deployment, so a developer
 * without one is not blocked and CI can opt in.
 */

const deployed = Boolean(process.env.FPL_ANDRES_BASE_URL);

test.skip(
  !deployed,
  "set FPL_ANDRES_BASE_URL to the deployment you want smoke tested",
);

const config = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../vercel.json", import.meta.url)),
    "utf-8",
  ),
) as { functions?: Record<string, unknown> };

test("the health endpoint answers", async ({ request }) => {
  const response = await request.get("/api/health");

  expect(response.status()).toBe(200);
  // Status alone is not enough: a single-page rewrite that swallowed `/api`
  // would answer 200 with the app's own HTML and look healthy.
  expect(response.headers()["content-type"]).toContain("application/json");
});

test("the player list is proxied rather than 404d", async ({ request }) => {
  // The exact call the analysis page makes on first paint.
  const response = await request.get("/api/fpl/bootstrap-static/");

  expect(
    response.status(),
    "a 404 here means the function is not routed, not that FPL is down",
  ).toBe(200);
  const payload = (await response.json()) as { elements?: unknown[] };
  expect(Array.isArray(payload.elements)).toBe(true);
  expect(payload.elements?.length ?? 0).toBeGreaterThan(100);
});

test("the fixture list is proxied", async ({ request }) => {
  const response = await request.get("/api/fpl/fixtures/");

  expect(response.status()).toBe(200);
  expect(Array.isArray(await response.json())).toBe(true);
});

test("a team route resolves to a handler", async ({ request }) => {
  const response = await request.get("/api/team/1");

  // What it says about that team is not the point; 404 would mean the
  // `[id]` function was never deployed.
  expect(response.status(), "404 means the function is not routed").not.toBe(
    404,
  );
  expect(response.headers()["content-type"]).toContain("application/json");
});

test("every function named in vercel.json is reachable", async ({
  request,
}) => {
  // A budget entry for a path nobody can reach is a function that was renamed
  // or never deployed, which is exactly how the last outage happened.
  const probes: Record<string, string> = {
    "api/health.ts": "/api/health",
    "api/fpl/*.ts": "/api/fpl/bootstrap-static/",
    "api/team/*.ts": "/api/team/1",
    "api/analysis-request.ts": "/api/analysis-request",
  };
  const declared = Object.keys(config.functions ?? {});
  expect(
    declared.filter((key) => !(key in probes)),
    "a function was added to vercel.json without a probe in this test",
  ).toEqual([]);

  for (const key of declared) {
    const path = probes[key];
    if (path === undefined) continue;
    const response = await request.fetch(path, { method: "GET" });
    expect(response.status(), `${key} is not routed at ${path}`).not.toBe(404);
    // HTML here means the request fell through to the single-page rewrite,
    // which is what an unrouted function looks like from the outside.
    expect(
      response.headers()["content-type"] ?? "",
      `${key} answered with the app shell rather than a function`,
    ).not.toContain("text/html");
  }
});

test("the analysis page plots rather than reporting a failure", async ({
  page,
}) => {
  await page.goto("/analysis");

  await expect(page.locator(".analysis-failure")).toHaveCount(0);
  await expect(page.locator(".scatter-controls").first()).toBeVisible({
    timeout: 30_000,
  });
});

test("the season plan renders its first gameweek", async ({ page }) => {
  await page.goto("/plan");

  await expect(page.locator(".plan-card").first()).toBeVisible({
    timeout: 30_000,
  });
});

test("crawler files publish the canonical routes", async ({ request }) => {
  const robots = await request.get("/robots.txt");
  expect(robots.status()).toBe(200);
  expect(await robots.text()).toContain(
    "Sitemap: https://fpl-andres.vercel.app/sitemap.xml",
  );

  const sitemap = await request.get("/sitemap.xml");
  expect(sitemap.status()).toBe(200);
  const xml = await sitemap.text();
  expect(xml).toContain("http://www.sitemaps.org/schemas/sitemap/0.9");
  expect(xml).toContain("https://fpl-andres.vercel.app/privacy");
  expect(xml).not.toContain("/team/");
  expect(xml).not.toContain("/kits");
});

test("private and QA routes are excluded before JavaScript runs", async ({
  request,
}) => {
  for (const path of ["/team/212279", "/kits", "/kits/"]) {
    const response = await request.get(path);
    expect(response.status()).toBe(200);
    expect(response.headers()["x-robots-tag"]).toBe("noindex, nofollow");
  }
});

test("the standard security contact is deployed", async ({ request }) => {
  const response = await request.get("/.well-known/security.txt");
  expect(response.status()).toBe(200);
  expect(await response.text()).toContain(
    "Contact: https://github.com/JamieMBright/fpl-andres/security/advisories/new",
  );
});
