import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import gw1Review from "../src/data/gw1-review.json" with { type: "json" };

/**
 * The whole browser suite, deliberately.
 *
 * What was here before: six spec files, 1,476 lines, 212 runs across two
 * projects, four to six minutes. Most of it re-asserted in a real browser what
 * a component test already proves in milliseconds — every degraded reason,
 * every route's title, every page at every width, every palette on every route.
 * A suite nobody will wait for is a suite that stops being run.
 *
 * What survives is what only a real browser can tell us, and only where a
 * failure would mean the product is broken rather than untidy:
 *
 *   - the app boots and routes at all
 *   - a manager can enter a Team ID and get a plan with recommendations in it
 *   - the API is alive and answers in its own contract
 *   - the busiest page has no accessibility violations
 *   - nothing spills sideways on a phone
 *
 * Everything else is a unit test's job. If a browser journey fails here it is
 * worth stopping for; that is the bar.
 */

const TEAM_ID = "212279";
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

/** Waits for the lazy route chunk and whatever it then renders. */
async function settle(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

async function selectKit(
  page: Page,
  theme: "dark" | "light" | "away",
): Promise<void> {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if ((await page.locator("html").getAttribute("data-theme")) === theme) {
      return;
    }
    await page.getByRole("button", { name: /kit$/i }).click();
  }
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

test("the API is alive and says so in its own contract", async ({
  request,
}) => {
  const response = await request.get("/api/health");

  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({
    status: "ok",
    service: "fpl-andres",
  });
});

test("a manager can enter a Team ID and reach their plan", async ({ page }) => {
  await page.goto("/");
  await settle(page);

  await page.getByLabel("Your FPL team ID").fill(TEAM_ID);
  await page.getByRole("button", { name: /analyse my squad/i }).click();

  await expect(page).toHaveURL(new RegExp(`/plan\\?team=${TEAM_ID}$`));
  await expect(page).toHaveTitle(new RegExp(`Team ${TEAM_ID}`));
  await expect(page.getByText(/lock a fifteen in at step one/i)).toHaveCount(0);
});

test("the plan answers with gameweeks rather than an empty page", async ({
  page,
}) => {
  await page.goto("/plan");
  await settle(page);

  // The product is the numbered steps and the gameweeks inside them. A plan
  // page that renders its heading and nothing else is the failure that matters.
  await expect(page.locator(".plan-step").first()).toBeVisible();
  await expect(page.locator('[data-step="04"]')).toBeVisible();
});

test("the observed GW1 team opens its immutable review", async ({ page }) => {
  await page.route("**/api/team/2822737", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      status: 200,
      body: JSON.stringify({
        status: "ready",
        state: {
          entryId: 2_822_737,
          event: 1,
          bankTenths: 0,
          squadValueTenths: 1_000,
          eventTransfers: 0,
          eventTransferCostPoints: 0,
          totalTransfers: 0,
          activeChip: null,
          picks: gw1Review.picks.map((pick) => ({
            elementId: pick.elementId,
            squadPosition: pick.squadPosition,
            multiplier: pick.multiplier,
            isCaptain: pick.isCaptain,
            isViceCaptain: pick.isViceCaptain,
            identity: {
              webName: pick.identity.name,
              positionCode: pick.identity.position,
              teamShortName: pick.identity.club,
              priceTenths: pick.identity.priceTenths,
              code: pick.identity.code,
            },
          })),
          stateAsOf: "2026-08-21T17:30:00Z",
          dataAvailableAt: "2026-08-26T12:00:00Z",
          evidenceLevel: "observed",
          sourceHashes: [`sha256:${"a".repeat(64)}`],
        },
      }),
    });
  });

  await page.goto("/plan?team=2822737");
  await settle(page);
  await page.locator('[data-step="02"] > summary').click();

  await expect(
    page.getByRole("heading", { name: "Gameweek 1, reviewed" }),
  ).toBeVisible();
  await expect(page.locator(".gw1-review-card")).toHaveCount(15);
  await expect(
    page.getByRole("button", { name: /Raya, captain, 6 actual points/i }),
  ).toBeVisible();
});

test("an unreachable source is reported, never invented", async ({ page }) => {
  await page.route("**/api/team/*", async (route) => {
    await route.fulfill({
      body: JSON.stringify({ status: "degraded", reason: "fpl_unreachable" }),
      contentType: "application/json",
      status: 503,
    });
  });

  await page.goto(`/plan?team=${TEAM_ID}`);
  await settle(page);
  await page
    .locator('[data-step="01"] summary')
    .getByText("Your manager and season")
    .click();

  await expect(
    page.getByRole("button", { name: /retry analysis/i }),
  ).toBeVisible();
});

test.describe.serial("plan palette accessibility", () => {
  for (const theme of ["dark", "light", "away"] as const) {
    test(`the busiest page passes an accessibility scan in the ${theme} kit`, async ({
      page,
    }) => {
      await page.goto(`/plan?team=${TEAM_ID}`);
      await settle(page);
      // The steps and their fixture chips carried real contrast failures that
      // only appeared once the page had finished rendering.
      await expect(page.locator('[data-step="04"]')).toBeVisible();
      await page.locator('[data-step="01"] > summary').click();
      // Wait for step 01 content to render. Pre-season: squad builder is shown.
      // In-season: the snapshot dossier is shown instead. Either satisfies.
      await expect(
        page.locator(
          '[data-step="01"] .squad-builder, [data-step="01"] .dossier',
        ),
      ).toBeVisible();
      await selectKit(page, theme);

      const scan = await new AxeBuilder({ page }).withTags([...WCAG]).analyze();
      expect(scan.violations).toEqual([]);
    });
  }
});

test("the accessibility scan is not vacuous", async ({ page }) => {
  await page.goto("/");
  await settle(page);

  // A scan that passes proves nothing unless a real failure would fail it.
  // Grey on white is about 1.6:1, well under the 4.5:1 the standard needs.
  await page.evaluate(() => {
    const probe = document.createElement("p");
    probe.textContent = "deliberately unreadable probe text";
    probe.setAttribute(
      "style",
      "color:#a9a9a9;background:#ffffff;font-size:12px;padding:8px",
    );
    document.body.append(probe);
  });

  const scan = await new AxeBuilder({ page })
    .withTags([...WCAG])
    .options({ runOnly: { type: "rule", values: ["color-contrast"] } })
    .analyze();

  expect(scan.violations.map((violation) => violation.id)).toContain(
    "color-contrast",
  );
});

test("privacy controls clear team data without clearing the kit", async ({
  page,
}) => {
  await page.goto("/privacy");
  await settle(page);
  await page.evaluate(() => {
    localStorage.setItem("fpl-andres:last-team", "212279");
    localStorage.setItem("fpl-andres:theme", "light");
  });

  await page.getByRole("button", { name: "Clear Saved Team Data" }).click();
  await expect(
    page.getByRole("alertdialog", { name: "Clear Saved Team Data?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear Team Data Now" }).click();

  await expect(page.getByText(/Saved team data cleared/)).toHaveAttribute(
    "role",
    "status",
  );
  expect(
    await page.evaluate(() => ({
      team: localStorage.getItem("fpl-andres:last-team"),
      theme: localStorage.getItem("fpl-andres:theme"),
    })),
  ).toEqual({ team: null, theme: "light" });

  const scan = await new AxeBuilder({ page }).withTags([...WCAG]).analyze();
  expect(scan.violations).toEqual([]);
});

test("the trust routes pass accessibility in all kits", async ({ page }) => {
  const scan = async () =>
    (await new AxeBuilder({ page }).withTags([...WCAG]).analyze()).violations;

  for (const path of [
    "/results",
    "/markets",
    "/fpl500",
    "/privacy",
    "/thanks?from=contact",
  ]) {
    await page.goto(path);
    await settle(page);
    for (const theme of ["dark", "light", "away"] as const) {
      await selectKit(page, theme);
      expect(await scan(), `${path} in the ${theme} kit`).toEqual([]);
    }
  }
});

test("the phone action reaches and focuses the Team ID field", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto("/results");
  await settle(page);

  const scan = await new AxeBuilder({ page }).withTags([...WCAG]).analyze();
  expect(scan.violations).toEqual([]);

  await page.getByRole("link", { name: "Analyse my squad" }).click();

  await expect(page).toHaveURL(/\/#team-id$/);
  await expect(page.getByLabel("Your FPL team ID")).toBeFocused();
  await expect(
    page.getByRole("link", { name: "Analyse my squad" }),
  ).toHaveCount(0);
});

test("all primary destinations stay visible on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto("/");
  await settle(page);

  const links = page
    .getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link");
  await expect(links).toHaveCount(10);

  const layout = await links.evaluateAll((destinations) => ({
    visible: destinations.every(
      (destination) => destination.getClientRects().length > 0,
    ),
    rows: new Set(
      destinations.map((destination) =>
        Math.round(destination.getBoundingClientRect().top),
      ),
    ).size,
  }));
  expect(layout.visible).toBe(true);
  expect(layout.rows).toBeLessThanOrEqual(3);
});

test("top picks wrap once without shrinking their players", async ({
  page,
}) => {
  await page.goto("/");
  await settle(page);

  const measure = async (width: number) => {
    await page.setViewportSize({ width, height: 900 });
    return page.locator(".top-pick-grid").evaluate((grid) => {
      const cards = [...grid.querySelectorAll<HTMLElement>(".top-pick-column")];
      const firstTop = Math.round(cards[0]?.getBoundingClientRect().top ?? 0);
      const rows = new Set(
        cards.map((card) => Math.round(card.getBoundingClientRect().top)),
      );
      const frame = cards[0]?.querySelector<HTMLElement>(".top-pick-frame");
      const image = frame?.querySelector<HTMLElement>("img, svg");
      const winner = cards[0]?.querySelector<HTMLElement>(
        ".top-pick-name button",
      );
      const names = [
        ...grid.querySelectorAll<HTMLElement>(
          ".top-pick-name button, .top-pick-runner-name",
        ),
      ];
      const tokens = [
        ...grid.querySelectorAll<HTMLElement>(
          ".top-pick-points b, .top-pick-points span, " +
            ".top-pick-runner-points b, .top-pick-runner-points span",
        ),
      ];
      const frameBox = frame?.getBoundingClientRect();
      const imageBox = image?.getBoundingClientRect();

      return {
        columns: cards.filter(
          (card) => Math.round(card.getBoundingClientRect().top) === firstTop,
        ).length,
        rows: rows.size,
        avatar: [frameBox?.width ?? 0, frameBox?.height ?? 0],
        image: [imageBox?.width ?? 0, imageBox?.height ?? 0],
        winnerFont: winner
          ? Number.parseFloat(getComputedStyle(winner).fontSize)
          : 0,
        wrappedNames: names.filter(
          (name) => name.scrollHeight > name.clientHeight + 1,
        ).length,
        splitTokens: tokens.filter(
          (token) => getComputedStyle(token).whiteSpace !== "nowrap",
        ).length,
        overflow:
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      };
    });
  };

  const wide = await measure(1000);
  expect(wide).toMatchObject({ columns: 4, rows: 1 });

  const wrapped = await measure(999);
  expect(wrapped).toMatchObject({ columns: 2, rows: 2 });

  const phone = await measure(360);
  expect(phone).toMatchObject({
    columns: 2,
    rows: 2,
    avatar: [88, 112],
    image: [88, 112],
    winnerFont: 18,
    wrappedNames: 0,
    splitTokens: 0,
    overflow: 0,
  });

  await page.locator(".top-pick-points").first().click();
  await expect(page.locator(".top-pick-panel")).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(0);
});

test("a phone gets a readable, tappable page that does not spill", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto(`/plan?team=${TEAM_ID}`);
  await settle(page);

  const measured = await page.evaluate(() => {
    const root = document.documentElement;
    const heading = document.querySelector("h1");
    // WCAG 2.5.8 exempts targets that are inline in a sentence. A skip link is
    // clipped to a pixel until it is focused, at which point it is full size,
    // so measuring it at rest measures the wrong thing.
    const inProse = (element: Element) =>
      element.parentElement?.closest("p, li") !== null;
    const targets = [
      ...document.querySelectorAll<HTMLElement>(
        "button, a[href], input, select, summary",
      ),
    ].filter(
      (element) =>
        element.getClientRects().length > 0 &&
        !element.closest(".visually-hidden, .skip-link") &&
        !inProse(element),
    );
    const smallest = targets
      .map((element) => {
        const box = element.getBoundingClientRect();
        return {
          size: Math.min(box.width, box.height),
          what: `${element.tagName}.${element.className}`,
        };
      })
      .sort((a, b) => a.size - b.size)[0];
    return {
      // Scrollable regions opt in with their own container; the page must not.
      overflow: root.scrollWidth - root.clientWidth,
      headingPx: heading
        ? Number.parseFloat(getComputedStyle(heading).fontSize)
        : 0,
      smallestTarget: smallest?.size ?? 999,
      smallestWhat: smallest?.what ?? "none",
    };
  });

  expect(measured.overflow).toBeLessThanOrEqual(0);
  expect(measured.headingPx).toBeGreaterThanOrEqual(20);
  expect(
    measured.smallestTarget,
    `smallest tap target is ${measured.smallestWhat}`,
  ).toBeGreaterThanOrEqual(24);
});

test("a mobile gesture over a player row scrolls the plan, not an inner list", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await page.route("**/api/team/*", async (route) => {
    await route.fulfill({
      body: JSON.stringify({
        status: "unavailable",
        reason: "no_processed_event",
      }),
      contentType: "application/json",
      status: 200,
    });
  });
  await page.goto(`/plan?team=${TEAM_ID}`);
  await settle(page);
  await page.locator('[data-step="01"] > summary').click();

  const market = page.getByRole("region", {
    name: "Scrollable player market",
  });
  const row = market.locator(".squad-market-list > li").first();
  await expect(row).toBeVisible();
  await row.scrollIntoViewIfNeeded();
  expect(
    await market.evaluate((element) => getComputedStyle(element).overflowY),
  ).toBe("visible");

  const rowBox = await row.boundingBox();
  if (!rowBox) throw new Error("player row has no box");
  await page.mouse.move(
    rowBox.x + rowBox.width / 2,
    rowBox.y + rowBox.height / 2,
  );
  const pageBefore = await page.evaluate(() => window.scrollY);
  await page.mouse.wheel(0, 600);

  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(pageBefore);
  expect(await market.evaluate((element) => element.scrollTop)).toBe(0);

  const wheelIntoView = async (selector: string) => {
    const target = page.locator(selector);
    const top = await target.evaluate(
      (element) => element.getBoundingClientRect().top,
    );
    await page.mouse.wheel(0, Math.max(1, top - 100));
    await expect(target).toBeInViewport();
  };

  await wheelIntoView(".squad-builder .squad-pitch");
  await wheelIntoView(".declared-squad-actions");
  await expect(
    page.getByRole("button", { name: /Lock this in for gameweek \d+/ }),
  ).toBeInViewport();
  await wheelIntoView('[data-step="02"]');
});
