import { expect, test, type Page } from "@playwright/test";

/**
 * The browser journeys covered the happy paths of two flows
 * plus a handful of failure reasons chosen ad hoc. This walks the whole state
 * space the contract defines, so a reason that stops rendering is a failing
 * test rather than a blank panel nobody notices.
 *
 * Three distinct classes are exercised, because they arrive by different routes
 * and the UI treats them differently:
 *
 *   unavailable  the request succeeded and there is genuinely nothing to show
 *   degraded     the request succeeded and FPL could not answer it
 *   stale        a refresh failed after a snapshot had already been shown, so
 *                the last verified state stays on screen with a warning
 *
 * The last one is the interesting case: it can only be reached by serving a
 * ready response and then failing the next one, which is why no earlier test
 * covered more than one of its five reasons.
 */

const sourceHashes = [
  `sha256:${"a".repeat(64)}`,
  `sha256:${"b".repeat(64)}`,
  `sha256:${"c".repeat(64)}`,
];

function readyState(entryId = 212279) {
  return {
    entryId,
    event: 5,
    bankTenths: 17,
    squadValueTenths: 1004,
    eventTransfers: 1,
    eventTransferCostPoints: 0,
    totalTransfers: 4,
    activeChip: null,
    picks: Array.from({ length: 15 }, (_, index) => ({
      elementId: 101 + index,
      squadPosition: index + 1,
      multiplier: index === 0 ? 2 : index < 11 ? 1 : 0,
      isCaptain: index === 0,
      isViceCaptain: index === 1,
    })),
    stateAsOf: "2026-07-20T10:30:00Z",
    dataAvailableAt: "2026-07-20T12:30:00Z",
    evidenceLevel: "observed",
    sourceHashes,
  };
}

async function stubHistory(page: Page) {
  await page.route("**/api/fpl/**", async (route) => {
    await route.fulfill({
      body: JSON.stringify({
        past: [{ season_name: "2024/25", total_points: 2308, rank: 1_410_478 }],
      }),
      contentType: "application/json",
    });
  });
}

test.describe("every unavailable reason explains itself", () => {
  const cases = [
    {
      reason: "entry_unavailable",
      body: { status: "unavailable", reason: "entry_unavailable" },
    },
    {
      reason: "no_processed_event",
      body: { status: "unavailable", reason: "no_processed_event" },
    },
    {
      reason: "picks_unavailable",
      body: { status: "unavailable", reason: "picks_unavailable", event: 5 },
    },
  ] as const;

  for (const scenario of cases) {
    test(scenario.reason, async ({ page }) => {
      await stubHistory(page);
      await page.route("**/api/team/*", async (route) => {
        await route.fulfill({
          body: JSON.stringify(scenario.body),
          contentType: "application/json",
        });
      });
      await page.goto("/plan?team=212279");

      const main = page.getByRole("main");
      await expect(main).toContainText(/./);
      // No squad may be drawn when there is no verified state to draw it from.
      await expect(
        page.getByRole("list", { name: "Substitutes in order" }),
      ).toHaveCount(0);
      await expect(page.getByText("Observed snapshot ready")).toHaveCount(0);
    });
  }
});

test.describe("every degraded reason offers a retry and fabricates nothing", () => {
  const reasons = [
    "fpl_unreachable",
    "fpl_source_failed",
    "source_contract_failed",
  ] as const;

  for (const reason of reasons) {
    test(reason, async ({ page }) => {
      await stubHistory(page);
      await page.route("**/api/team/*", async (route) => {
        await route.fulfill({
          body: JSON.stringify({ status: "degraded", reason }),
          contentType: "application/json",
        });
      });
      await page.goto("/plan?team=212279");

      await expect(
        page.getByRole("button", { name: "Retry analysis" }),
      ).toBeVisible();
      await expect(
        page.getByRole("list", { name: "Substitutes in order" }),
      ).toHaveCount(0);
      await expect(page.getByText("£100.4m")).toHaveCount(0);
    });
  }
});

test.describe("a failed refresh keeps the last verified snapshot and says so", () => {
  const cases = [
    {
      name: "fpl_unreachable",
      respond: async (route: Parameters<Parameters<Page["route"]>[1]>[0]) =>
        route.fulfill({
          body: JSON.stringify({
            status: "degraded",
            reason: "fpl_unreachable",
          }),
          contentType: "application/json",
        }),
    },
    {
      name: "fpl_source_failed",
      respond: async (route: Parameters<Parameters<Page["route"]>[1]>[0]) =>
        route.fulfill({
          body: JSON.stringify({
            status: "degraded",
            reason: "fpl_source_failed",
          }),
          contentType: "application/json",
        }),
    },
    {
      name: "source_contract_failed",
      respond: async (route: Parameters<Parameters<Page["route"]>[1]>[0]) =>
        route.fulfill({
          body: JSON.stringify({
            status: "degraded",
            reason: "source_contract_failed",
          }),
          contentType: "application/json",
        }),
    },
    {
      name: "network_error",
      respond: async (route: Parameters<Parameters<Page["route"]>[1]>[0]) =>
        route.abort("connectionrefused"),
    },
    {
      name: "invalid_response",
      respond: async (route: Parameters<Parameters<Page["route"]>[1]>[0]) =>
        route.fulfill({
          body: JSON.stringify({
            status: "ready",
            state: { entryId: "not a number" },
          }),
          contentType: "application/json",
        }),
    },
  ];

  for (const scenario of cases) {
    test(scenario.name, async ({ page }) => {
      await stubHistory(page);

      // The refresh is automatic on mount, and the snapshot it falls back to
      // lives in localStorage. So the stale state is only reachable across two
      // visits: one that proves and caches a snapshot, one whose refresh fails.
      let failing = false;
      await page.route("**/api/team/*", async (route) => {
        if (failing) {
          await scenario.respond(route);
          return;
        }
        await route.fulfill({
          body: JSON.stringify({ status: "ready", state: readyState() }),
          contentType: "application/json",
        });
      });

      await page.goto("/plan?team=212279");
      await expect(page.getByText("Observed snapshot ready")).toBeVisible();

      failing = true;
      await page.reload();

      await expect(
        page.getByText("Showing a stale verified snapshot"),
      ).toBeVisible();
      // The point of the stale state: the squad it already proved stays visible.
      await expect(
        page.getByRole("list", { name: "Substitutes in order" }),
      ).toBeVisible();
      await expect(page.getByText("£100.4m")).toBeVisible();
    });
  }
});

test.describe("transport failures never reach the user as a blank page", () => {
  const failures = [
    {
      name: "a 500 from the proxy",
      respond: async (route: Parameters<Parameters<Page["route"]>[1]>[0]) =>
        route.fulfill({
          status: 500,
          body: "upstream exploded",
          contentType: "text/plain",
        }),
    },
    {
      name: "a body that is not JSON",
      respond: async (route: Parameters<Parameters<Page["route"]>[1]>[0]) =>
        route.fulfill({
          status: 200,
          body: "<html>gateway</html>",
          contentType: "text/html",
        }),
    },
    {
      name: "JSON that does not match the contract",
      respond: async (route: Parameters<Parameters<Page["route"]>[1]>[0]) =>
        route.fulfill({
          status: 200,
          body: JSON.stringify({ status: "surprise" }),
          contentType: "application/json",
        }),
    },
    {
      name: "a refused connection",
      respond: async (route: Parameters<Parameters<Page["route"]>[1]>[0]) =>
        route.abort("connectionrefused"),
    },
  ];

  for (const failure of failures) {
    test(failure.name, async ({ page }) => {
      await stubHistory(page);
      await page.route("**/api/team/*", failure.respond);
      await page.goto("/plan?team=212279");

      // Something must be said, a heading must survive, and no squad invented.
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.getByRole("main")).toContainText(/./);
      await expect(
        page.getByRole("list", { name: "Substitutes in order" }),
      ).toHaveCount(0);
    });
  }
});

test("an upstream failure never leaks its internals to the page", async ({
  page,
}) => {
  await stubHistory(page);
  await page.route("**/api/team/*", async (route) => {
    await route.fulfill({
      status: 500,
      body: JSON.stringify({
        error: "connect ECONNREFUSED 10.0.0.7:5432",
        stack: "/var/task/api/team/[id].js:41",
      }),
      contentType: "application/json",
    });
  });
  await page.goto("/plan?team=212279");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  const body = (await page.textContent("body")) ?? "";
  for (const secret of ["ECONNREFUSED", "10.0.0.7", "/var/task", "5432"]) {
    expect(body).not.toContain(secret);
  }
});
