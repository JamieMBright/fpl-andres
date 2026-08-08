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

function bootstrapDocument() {
  return {
    events: [{ id: 1, deadline_time: "2026-08-21T17:30:00Z" }],
    element_types: [
      { id: 1, singular_name_short: "GKP" },
      { id: 2, singular_name_short: "DEF" },
      { id: 3, singular_name_short: "MID" },
      { id: 4, singular_name_short: "FWD" },
    ],
    teams: [{ id: 1, code: 1, short_name: "MUN", name: "Man Utd" }],
    elements: [
      {
        id: 1,
        // Bruno Fernandes, whose record is in the published artifact.
        code: 141746,
        web_name: "B.Fernandes",
        element_type: 3,
        team: 1,
        now_cost: 120,
        status: "a",
      },
      {
        id: 2,
        code: 999_999_999,
        web_name: "Debutant",
        element_type: 4,
        team: 1,
        now_cost: 55,
        status: "a",
      },
    ],
  };
}

async function mockManagerHistory(page: Page) {
  await page.route("**/api/fpl/**", async (route) => {
    if (route.request().url().includes("bootstrap-static")) {
      await route.fulfill({
        body: JSON.stringify(bootstrapDocument()),
        contentType: "application/json",
      });
      return;
    }
    // Slash-insensitive: Vercel's catch-all route refuses a trailing slash, so
    // the app asks for `/api/fpl/fixtures` and the proxy restores it upstream.
    if (/\/fixtures\/?($|\?)/.test(route.request().url())) {
      await route.fulfill({
        body: JSON.stringify([{ event: 1, team_h: 1, team_a: 1 }]),
        contentType: "application/json",
      });
      return;
    }
    await route.fulfill({
      body: JSON.stringify({
        past: [
          { season_name: "2024/25", total_points: 2308, rank: 1_410_478 },
          { season_name: "2025/26", total_points: 1858, rank: 6_659_254 },
        ],
      }),
      contentType: "application/json",
    });
  });
}

async function fulfillReady(page: Page) {
  await mockManagerHistory(page);
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
    await page.goto("/plan?team=212279");
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
    await page.goto("/plan?team=111111");
    await expect(
      page.getByRole("heading", { name: "Every gameweek to the end." }),
    ).toBeVisible();
    await page.getByText("Observed snapshot ready").waitFor();

    // Switching team must remount the snapshot, not repaint the previous one.
    await page.goto("/plan?team=222222");
    await expect(
      page.getByRole("heading", { name: "Every gameweek to the end." }),
    ).toBeVisible();
    await expect(page.getByLabel("Your Team ID")).toHaveValue("222222");
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

  test("prices the 2026/27 pool against last season and admits the gaps", async ({
    page,
  }) => {
    await fulfillReady(page);
    await page.goto("/");

    await page.getByRole("link", { name: "Players" }).click();
    await expect(page).toHaveURL(/\/players$/);

    const rows = page.getByRole("table", {
      name: /2026\/27 players against last season/,
    });
    await expect(rows).toBeVisible();
    // This season's price, last season's record, and the ratio of the two.
    await expect(rows.getByRole("row", { name: /B\.Fernandes/ })).toContainText(
      "£12.0m",
    );
    await expect(rows.getByRole("row", { name: /B\.Fernandes/ })).toContainText(
      "5.05",
    );
    // A player with no Premier League record is listed, and left blank.
    await expect(rows.getByRole("row", { name: /Debutant/ })).toContainText(
      "—",
    );
    await expect(page.getByText(/1 in the game with no record/)).toBeVisible();
  });

  test("opens one player in full and says where his points come from", async ({
    page,
  }) => {
    await fulfillReady(page);
    await page.goto("/players");

    await page
      .getByRole("button", { name: "B.Fernandes", exact: true })
      .click();

    const card = page.getByRole("dialog");
    await expect(card).toBeVisible();
    await expect(card).toContainText("Where the points come from");
    await expect(card).toContainText("Goals and assists");
    // The published routes add back up to the figure in the table.
    await expect(card).toContainText("Points per match");
    await expect(card).toContainText("Suspension derate");

    await card.getByRole("button", { name: "Close" }).click();
    await expect(card).toBeHidden();
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
        heading: /^Team Not Available$/,
      },
      {
        payload: {
          status: "unavailable",
          reason: "no_processed_event" as const,
        },
        heading: /season hasn.t started/,
      },
      {
        payload: {
          status: "unavailable",
          reason: "picks_unavailable" as const,
          event: 12,
        },
        heading: /^Gameweek Picks Not Available$/,
      },
    ];

    for (const variant of variants) {
      await page.route("**/api/team/*", async (route) => {
        await route.fulfill({
          body: JSON.stringify(variant.payload),
          contentType: "application/json",
        });
      });
      await page.goto("/plan?team=212279");
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

    await page.goto("/plan?team=212279");
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

  test("kit toggle names the kit in use and repaints both themes", async ({
    page,
  }) => {
    await page.goto("/");

    const toggle = page.getByRole("button", { name: /kit$/i });
    const shell = page.locator(".app-shell");

    // The label names the kit the button switches *to*, which is what a kit
    // button does. The away kit is the default, so it offers the third.
    await expect(toggle).toHaveText("Third kit");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    const awayKit = await shell.evaluate(
      (node) => getComputedStyle(node).backgroundImage,
    );

    await toggle.click();

    await expect(toggle).toHaveText("Home kit");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "third");
    const thirdKit = await shell.evaluate(
      (node) => getComputedStyle(node).backgroundImage,
    );

    await toggle.click();

    await expect(toggle).toHaveText("Away kit");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    const homeKit = await shell.evaluate(
      (node) => getComputedStyle(node).backgroundImage,
    );

    // Every kit must actually paint stripes, and they must differ.
    expect(awayKit).toContain("repeating-linear-gradient");
    expect(thirdKit).toContain("repeating-linear-gradient");
    expect(homeKit).toContain("repeating-linear-gradient");
    expect(homeKit).not.toEqual(awayKit);
    expect(thirdKit).not.toEqual(awayKit);
  });

  test("the chosen kit survives a reload", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /kit$/i }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "third");

    await page.reload();

    await expect(page.locator("html")).toHaveAttribute("data-theme", "third");
  });

  test("home kit passes automated axe scans", async ({ page }) => {
    await page.goto("/");
    const toggle = page.getByRole("button", { name: /kit$/i });
    await toggle.click();
    await toggle.click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    const scan = await new AxeBuilder({ page }).analyze();
    expect(scan.violations).toEqual([]);
  });

  test("the calibration page reports results it lost as well as won", async ({
    page,
  }) => {
    await page.goto("/calibration");

    await expect(
      page.getByRole("heading", { name: "Can I rank players?" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Does following me actually help?" }),
    ).toBeVisible();

    await expect(
      page.getByRole("heading", { name: "Who would I have captained?" }),
    ).toBeVisible();

    // The verdicts are derived from the artifact, so the page states whichever
    // way the measurement fell rather than a sentence somebody typed once.
    await expect(
      page.getByText(/last-five average in (all )?\d+( of \d+)? seasons/),
    ).toBeVisible();

    // The rank comparison is a chart now, not a table: the question is always
    // whether a lead holds across seasons, which is a shape.
    await expect(
      page.getByRole("img", { name: "Rank correlation, season by season" }),
    ).toBeVisible();
    await expect(
      page.getByRole("table", { name: "Mini-league outcomes by season" }),
    ).toBeVisible();
  });

  test("calibration passes automated axe scans", async ({ page }) => {
    await page.goto("/calibration");
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
    await page.goto("/plan?team=212279");
    await page
      .getByRole("heading", { name: "FPL Cannot Be Reached" })
      .waitFor();

    const scan = await new AxeBuilder({ page }).analyze();
    expect(scan.violations).toEqual([]);
  });
});
