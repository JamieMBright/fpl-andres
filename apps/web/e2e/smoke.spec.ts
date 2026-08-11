import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

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

  await expect(
    page.getByRole("button", { name: /retry analysis/i }),
  ).toBeVisible();
});

test("the busiest page passes an accessibility scan in both kits", async ({
  page,
}) => {
  await page.goto(`/plan?team=${TEAM_ID}`);
  await settle(page);
  // The steps and their fixture chips carried real contrast failures that only
  // appeared once the page had finished rendering.
  await expect(page.locator('[data-step="04"]')).toBeVisible();

  const scan = async () =>
    (await new AxeBuilder({ page }).withTags([...WCAG]).analyze()).violations;

  expect(await scan()).toEqual([]);

  // The light kit is a separate palette, not a filter over the dark one, and
  // three of the four contrast defects found so far were only in one of them.
  await page.getByRole("button", { name: /kit$/i }).click();
  await page.getByRole("button", { name: /kit$/i }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  expect(await scan()).toEqual([]);
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

  await expect(page.getByRole("status")).toContainText(
    "Saved team data cleared",
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
