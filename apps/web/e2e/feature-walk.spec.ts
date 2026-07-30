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
    evidenceLevel: "observed" as const,
    sourceHashes,
  };
}

async function fulfillReady(page: Page) {
  await page.route("**/api/team/*", async (route) => {
    const entryId = Number(route.request().url().split("/").pop());
    await route.fulfill({
      body: JSON.stringify({
        status: "ready",
        state: publicTeamState(Number.isFinite(entryId) ? entryId : 212279),
      }),
      contentType: "application/json",
    });
  });
}

test.describe("feature walk", () => {
  test("saves, persists and confirms removal of manager corrections", async ({
    page,
  }) => {
    await fulfillReady(page);
    await page.goto("/team/212279");
    await page.getByText("Observed snapshot ready").waitFor();

    await page.getByText("Correct Current State").click();
    const bank = page.getByLabel("Current bank (£m)");
    await bank.fill("1.7");
    await page.getByRole("button", { name: "Save corrections" }).click();

    await expect(
      page.getByRole("status", { name: "Manager correction status" }),
    ).toContainText("Manager corrections saved");

    await page.reload();
    await page.getByText("Observed snapshot ready").waitFor();
    await page.getByText("Correct Current State").click();
    await expect(page.getByLabel("Current bank (£m)")).toHaveValue("1.7");

    await page
      .getByRole("button", { name: "Remove saved corrections" })
      .click();
    const dialog = page.getByRole("alertdialog", {
      name: "Remove saved corrections?",
    });
    await expect(dialog).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(
      page.getByRole("button", { name: "Remove saved corrections" }),
    ).toBeFocused();

    await page
      .getByRole("button", { name: "Remove saved corrections" })
      .click();
    await page.getByRole("button", { name: "Remove corrections now" }).click();
    await expect(
      page.getByRole("status", { name: "Manager correction status" }),
    ).toContainText("Manager corrections removed");
  });

  test("does not leak a prior team's snapshot when navigating between team routes", async ({
    page,
  }) => {
    await fulfillReady(page);
    await page.goto("/team/111111");
    await expect(
      page.getByRole("heading", { name: "Analysis for team 111111" }),
    ).toBeVisible();
    await page.getByText("Observed snapshot ready").waitFor();

    await page.getByRole("link", { name: "Analyse another team" }).click();
    await page.getByLabel("FPL team ID").fill("222222");
    await page.getByRole("button", { name: "Analyse team" }).click();

    await expect(
      page.getByRole("heading", { name: "Analysis for team 222222" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Analysis for team 111111" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "Analysis for team 222222" }),
    ).toHaveAttribute("translate", "no");
  });

  test("navigates the methodology and calibration routes and returns focus to headings", async ({
    page,
  }) => {
    await fulfillReady(page);
    await page.goto("/");

    await page.getByRole("link", { name: "Method" }).click();
    await expect(page).toHaveURL(/\/methodology$/);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeFocused();

    await page.getByRole("link", { name: "Calibration" }).click();
    await expect(page).toHaveURL(/\/calibration$/);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeFocused();
  });

  test("renders every unavailable envelope variant with a distinct heading", async ({
    page,
  }) => {
    const variants = [
      {
        payload: {
          status: "unavailable",
          reason: "entry_unavailable" as const,
        },
        heading: "Team Not Available",
      },
      {
        payload: {
          status: "unavailable",
          reason: "no_processed_event" as const,
        },
        heading: "No processed gameweek yet",
      },
      {
        payload: {
          status: "unavailable",
          reason: "picks_unavailable" as const,
          event: 12,
        },
        heading: "Gameweek Picks Not Available",
      },
    ];

    for (const variant of variants) {
      await page.route("**/api/team/*", async (route) => {
        await route.fulfill({
          body: JSON.stringify(variant.payload),
          contentType: "application/json",
        });
      });
      await page.goto("/team/212279");
      await expect(
        page.getByRole("heading", { name: variant.heading }),
      ).toBeVisible();
      await expect(
        page.getByRole("table", { name: "Last-deadline squad" }),
      ).toHaveCount(0);
      await page.unroute("**/api/team/*");
    }
  });

  test("degraded fpl_source_failed shows retry without offering fabricated data", async ({
    page,
  }) => {
    await page.route("**/api/team/*", async (route) => {
      await route.fulfill({
        body: JSON.stringify({
          status: "degraded",
          reason: "fpl_source_failed",
        }),
        contentType: "application/json",
        status: 503,
      });
    });

    await page.goto("/team/212279");
    await expect(
      page.getByRole("heading", { name: "FPL Source Request Failed" }),
    ).toBeVisible();
    await expect(
      page.getByRole("table", { name: "Last-deadline squad" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Retry analysis" }),
    ).toBeVisible();
  });

  test("home page passes automated axe scans", async ({ page }) => {
    await page.goto("/");
    const scan = await new AxeBuilder({ page }).analyze();
    expect(scan.violations).toEqual([]);
  });

  test("degraded state passes automated axe scans", async ({ page }) => {
    await page.route("**/api/team/*", async (route) => {
      await route.fulfill({
        body: JSON.stringify({
          status: "degraded",
          reason: "fpl_unreachable",
        }),
        contentType: "application/json",
        status: 503,
      });
    });
    await page.goto("/team/212279");
    await page
      .getByRole("heading", { name: "FPL Cannot Be Reached" })
      .waitFor();

    const scan = await new AxeBuilder({ page }).analyze();
    expect(scan.violations).toEqual([]);
  });
});
