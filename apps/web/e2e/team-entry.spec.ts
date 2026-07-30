import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const sourceHashes = [
  `sha256:${"a".repeat(64)}`,
  `sha256:${"b".repeat(64)}`,
  `sha256:${"c".repeat(64)}`,
];

function publicTeamState(entryId = 212279) {
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

async function mockTeamResponse(page: Page, body: unknown, status = 200) {
  await page.route("**/api/team/*", async (route) => {
    await route.fulfill({
      body: JSON.stringify(body),
      contentType: "application/json",
      status,
    });
  });
}

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
}

test("opens a verified public team dossier from the working first screen", async ({
  page,
}) => {
  await mockTeamResponse(page, {
    status: "ready",
    state: publicTeamState(123456),
  });
  await page.goto("/");

  const homeHeading = page.getByRole("heading", {
    name: "Let me look at your squad.",
  });
  await expect(homeHeading).toBeVisible();
  await expect(homeHeading).not.toBeFocused();
  await page.getByLabel("Your FPL team ID").fill("123456");
  await page.getByRole("button", { name: "Analyse my squad" }).click();

  await expect(page).toHaveURL(/\/team\/123456$/);
  await expect(
    page.getByRole("heading", { name: "Analysis for team 123456" }),
  ).toBeFocused();
  await expect(page.getByText("Observed snapshot ready")).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Last-deadline squad" }),
  ).toBeVisible();
  await expect(page.getByText("£100.4m")).toBeVisible();
});

test("supports keyboard bypass and disclosure controls", async ({ page }) => {
  await mockTeamResponse(page, {
    status: "ready",
    state: publicTeamState(),
  });
  await page.goto("/team/212279");
  await page.getByText("Observed snapshot ready").waitFor();

  const skipLink = page.getByRole("link", { name: "Skip to content" });
  await expect(skipLink).toHaveCSS("clip-path", "inset(50%)");
  await page.keyboard.press("Home");
  await page.keyboard.press("Tab");
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toHaveCSS("clip-path", "none");
  await skipLink.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();

  const sourceSummary = page.locator(".source-trail summary");
  await sourceSummary.focus();
  await page.keyboard.press("Space");
  await expect(page.locator(".source-trail")).toHaveAttribute("open", "");
  await page.keyboard.press("Space");
  await expect(page.locator(".source-trail")).not.toHaveAttribute("open", "");
});

test("passes automated accessibility scans on entry and dossier", async ({
  page,
}) => {
  await mockTeamResponse(page, {
    status: "ready",
    state: publicTeamState(),
  });
  await page.goto("/");

  const entryScan = await new AxeBuilder({ page }).analyze();
  expect(entryScan.violations).toEqual([]);

  await page.getByLabel("Your FPL team ID").fill("212279");
  await page.getByRole("button", { name: "Analyse my squad" }).click();
  await page.getByText("Observed snapshot ready").waitFor();
  await page.getByText("Correct Current State").click();

  const dossierScan = await new AxeBuilder({ page }).analyze();
  expect(dossierScan.violations).toEqual([]);
});

test("keeps verified cached state visible when refresh is degraded", async ({
  page,
}, testInfo) => {
  await page.addInitScript((state) => {
    localStorage.setItem(
      `fpl-andres:public-team-state:v1:${state.entryId}`,
      JSON.stringify(state),
    );
  }, publicTeamState());
  await mockTeamResponse(
    page,
    { status: "degraded", reason: "fpl_unreachable" },
    503,
  );

  await page.goto("/team/212279");

  await expect(
    page.getByText("Showing a stale verified snapshot"),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Last-deadline squad" }),
  ).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("stale.png"),
  });
});

test("renders an honest unavailable state without a squad", async ({
  page,
}, testInfo) => {
  await mockTeamResponse(page, {
    status: "unavailable",
    reason: "picks_unavailable",
    event: 9,
  });

  await page.goto("/team/212279");

  await expect(
    page.getByRole("heading", { name: "Gameweek Picks Not Available" }),
  ).toBeVisible();
  await expect(page.getByText(/Gameweek 9/)).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Last-deadline squad" }),
  ).toHaveCount(0);
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("unavailable.png"),
  });
});

test("recovers from an invalid response without losing focus", async ({
  page,
}, testInfo) => {
  let allowReady = false;
  let requestCount = 0;
  await page.route("**/api/team/*", async (route) => {
    requestCount += 1;
    await route.fulfill(
      allowReady
        ? {
            body: JSON.stringify({
              status: "ready",
              state: publicTeamState(),
            }),
            contentType: "application/json",
          }
        : { body: "not-json", contentType: "application/json" },
    );
  });
  await page.goto("/team/212279");

  await expect(
    page.getByRole("heading", {
      name: "Analysis Response Failed Validation",
    }),
  ).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("error.png"),
  });
  const requestsBeforeRetry = requestCount;
  allowReady = true;
  await page.getByRole("button", { name: "Retry analysis" }).click();

  await expect(
    page.getByRole("region", { name: "Analysis result" }),
  ).toBeFocused();
  await expect(page.getByText("Observed snapshot ready")).toBeVisible();
  expect(requestCount).toBeGreaterThan(requestsBeforeRetry);
});

test("keeps the dossier inside a 360 pixel mobile viewport", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await mockTeamResponse(page, {
    status: "ready",
    state: publicTeamState(),
  });
  await page.goto("/");
  await expectNoPageOverflow(page);
  await expect(
    page.getByRole("heading", {
      name: "Let me look at your squad.",
    }),
  ).toBeVisible();
  await page.getByLabel("Your FPL team ID").fill("212279");
  await page.getByRole("button", { name: "Analyse my squad" }).click();
  await page.getByText("Observed snapshot ready").waitFor();

  await expectNoPageOverflow(page);
  await expect(page.getByRole("link", { name: "Method" })).toBeVisible();
  await expect(page.getByText("£100.4m")).toBeVisible();
  await page.getByText("Correct Current State").click();
  await expect(page.getByLabel("Current bank (£m)")).toBeVisible();
  await expectNoPageOverflow(page);
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("ready-mobile-360.png"),
  });
});

test("reflows at a 200 percent desktop zoom equivalent", async ({ page }) => {
  await page.setViewportSize({ width: 720, height: 450 });
  await mockTeamResponse(page, {
    status: "ready",
    state: publicTeamState(4_294_967_295),
  });
  await page.goto("/team/4294967295");
  await page.getByText("Observed snapshot ready").waitFor();

  await expectNoPageOverflow(page);
  await expect(
    page.getByRole("heading", { name: "Analysis for team 4294967295" }),
  ).toBeVisible();
  await expect(page.getByText("£100.4m")).toBeVisible();
});

test("disables loading and disclosure animation for reduced motion", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/team/*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({
      body: JSON.stringify({ status: "ready", state: publicTeamState() }),
      contentType: "application/json",
    });
  });
  await page.goto("/team/212279");

  const loadingMark = page.locator(".loading-mark");
  await expect(loadingMark).toBeVisible();
  await expect(loadingMark).toHaveCSS("animation-name", "none");
  await page.getByText("Observed snapshot ready").waitFor();
  await expect(page.locator(".disclosure-mark").first()).toHaveCSS(
    "transition-duration",
    "0s",
  );
});

test("keeps evidence and focus controls visible in forced colors", async ({
  page,
}) => {
  await page.emulateMedia({ forcedColors: "active" });
  await mockTeamResponse(page, {
    status: "ready",
    state: publicTeamState(),
  });
  await page.goto("/team/212279");
  await page.getByText("Observed snapshot ready").waitFor();

  await expect(page.locator(".brand-mark")).toBeVisible();
  await expect(page.getByText("Observed", { exact: true })).toBeVisible();
  const correctionSummary = page.locator(".correction-panel > summary");
  await correctionSummary.focus();
  await expect(correctionSummary).toBeFocused();
});
