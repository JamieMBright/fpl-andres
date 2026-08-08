import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * `DESIGN.md` claims a contrast standard and nothing enforced
 * it across the site.
 *
 * What was already there: the home page was scanned in both kits, and three
 * other pages were scanned in whichever kit happened to be active — which is
 * the dark one, because that is the default in `index.html`. So the light kit's
 * palette, defined separately at `:root[data-theme="light"]`, was unscanned on
 * every route but one.
 *
 * The tags are named rather than left to axe's defaults so that the standard
 * being claimed is the standard being checked. `wcag2aa` carries the 4.5:1
 * contrast rule that `DESIGN.md` commits to.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

const ROUTES = [
  { name: "landing", path: "/" },
  { name: "season plan", path: "/plan" },
  { name: "method", path: "/methodology" },
  { name: "player pool", path: "/players" },
  { name: "analysis", path: "/analysis" },
  { name: "calibration", path: "/calibration" },
] as const;

const KITS = [
  { name: "away kit", theme: "dark", clicks: 0 },
  { name: "third kit", theme: "third", clicks: 1 },
  { name: "home kit", theme: "light", clicks: 2 },
] as const;

/** Longest a route is given to stop changing before it is scanned anyway. */
const SETTLE_CEILING_MS = 8_000;

/** How long the DOM must hold still before the page counts as settled. */
const SETTLE_QUIET_MS = 500;

/**
 * Waits for the lazy route chunk and everything it then renders, so axe never
 * scans a Suspense fallback or a half-filled page.
 *
 * Waiting on the heading alone made this suite scan whatever had mounted by
 * then, which on a loaded machine was less than on an idle one. The captaincy
 * grid, the plan's numbered steps and its fixture-difficulty chips all carried
 * real contrast failures that only surfaced in a full parallel run — the check
 * was passing by arriving early, not by the page being sound.
 *
 * `networkidle` was the first attempt and is the wrong instrument: it waits on
 * requests rather than on rendering, and it has no ceiling of its own. This
 * waits for the DOM itself to hold still, and gives up at a stated bound rather
 * than hanging.
 */
async function settle(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.evaluate(
    async ([quietMs, ceilingMs]: [number, number]) => {
      await new Promise<void>((resolve) => {
        let quiet = window.setTimeout(finish, quietMs);
        const observer = new MutationObserver(() => {
          window.clearTimeout(quiet);
          quiet = window.setTimeout(finish, quietMs);
        });
        const ceiling = window.setTimeout(finish, ceilingMs);

        function finish(): void {
          window.clearTimeout(quiet);
          window.clearTimeout(ceiling);
          observer.disconnect();
          resolve();
        }

        observer.observe(document.body, {
          attributes: true,
          childList: true,
          subtree: true,
        });
      });
    },
    [SETTLE_QUIET_MS, SETTLE_CEILING_MS] as [number, number],
  );
}

async function applyKit(
  page: Page,
  clicks: number,
  theme: string,
): Promise<void> {
  for (let index = 0; index < clicks; index += 1) {
    await page.getByRole("button", { name: /kit$/i }).click();
  }
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

test.describe("both kits meet the contrast standard the design claims", () => {
  for (const kit of KITS) {
    for (const route of ROUTES) {
      test(`${route.name} in the ${kit.name}`, async ({ page }) => {
        await page.goto(route.path);
        await settle(page);
        await applyKit(page, kit.clicks, kit.theme);

        const scan = await new AxeBuilder({ page })
          .withTags([...WCAG])
          .analyze();

        expect(scan.violations).toEqual([]);
      });
    }

    test(`a dossier in the ${kit.name}`, async ({ page }) => {
      await page.route("**/api/team/*", async (route) => {
        await route.fulfill({
          body: JSON.stringify({
            status: "unavailable",
            reason: "no_processed_event",
          }),
          contentType: "application/json",
        });
      });
      await page.goto("/plan?team=212279");
      await settle(page);
      await applyKit(page, kit.clicks, kit.theme);

      const scan = await new AxeBuilder({ page }).withTags([...WCAG]).analyze();

      expect(scan.violations).toEqual([]);
    });
  }
});

test.describe("the contrast check is real, not vacuous", () => {
  test("axe reports a colour-contrast violation when one is injected", async ({
    page,
  }) => {
    await page.goto("/");
    await settle(page);

    // A scan that passes proves nothing unless a genuine failure would fail it.
    // Grey on white is roughly 1.6:1, well under the 4.5:1 the standard needs.
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

  test("the two kits genuinely differ, so scanning both is not scanning one twice", async ({
    page,
  }) => {
    await page.goto("/");
    await settle(page);

    const readSurface = () =>
      page.evaluate(() => {
        const styles = getComputedStyle(document.body);
        return `${styles.color}|${styles.backgroundColor}`;
      });

    const dark = await readSurface();
    await applyKit(page, 2, "light");
    const light = await readSurface();

    expect(light).not.toEqual(dark);
  });
});
