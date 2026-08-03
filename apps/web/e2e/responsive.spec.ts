import { expect, test, type Page } from "@playwright/test";

/**
 * Audit item #131 said the layout "relies entirely on fluid clamp() scaling".
 * It does not: `styles.css` carries breakpoints at 480px, 640px and 860px.
 *
 * What was missing is a test that any of it works. These check the three widths
 * the item named, plus the two either side of the 640px breakpoint, for the
 * failure that actually reaches users: horizontal overflow, which turns a page
 * into something that scrolls sideways and clips its own content.
 */

const WIDTHS = [
  { name: "small phone", width: 360, height: 740 },
  { name: "below the 640 breakpoint", width: 600, height: 800 },
  { name: "above the 640 breakpoint", width: 680, height: 800 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 900 },
] as const;

const ROUTES = [
  "/",
  "/plan",
  "/methodology",
  "/players",
  "/calibration",
] as const;

async function settle(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth - root.clientWidth;
  });
}

test.describe("layout survives every width", () => {
  for (const viewport of WIDTHS) {
    for (const route of ROUTES) {
      test(`${route} at ${viewport.width}px (${viewport.name})`, async ({
        page,
      }) => {
        await page.setViewportSize({
          width: viewport.width,
          height: viewport.height,
        });
        await page.goto(route);
        await settle(page);

        // A page that scrolls sideways has clipped something. Scrollable
        // tables are exempt by construction: they overflow inside their own
        // wrapper, not the document.
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
      });
    }
  }
});

test.describe("the breakpoints actually do something", () => {
  test("a grid layout reflows to one column on a narrow screen", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await settle(page);

    // Whichever multi-column grids the home page renders, at least one must
    // collapse. A breakpoint that changes nothing is a breakpoint that is not
    // doing the job the stylesheet claims for it.
    const columnsAt = async () =>
      page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("main *")]
          .map((node) => getComputedStyle(node).gridTemplateColumns)
          .filter((value) => value !== "none" && value.split(" ").length > 1),
      );

    const wide = await columnsAt();
    await page.setViewportSize({ width: 360, height: 740 });
    const narrow = await columnsAt();

    expect(wide.length).toBeGreaterThan(0);
    expect(narrow).not.toEqual(wide);
  });

  test("the primary heading stays readable at the smallest width", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto("/");
    await settle(page);

    const size = await page
      .getByRole("heading", { level: 1 })
      .evaluate((node) => Number.parseFloat(getComputedStyle(node).fontSize));

    // clamp() scaling with no floor is how a heading ends up at 11px on a
    // small phone.
    expect(size).toBeGreaterThanOrEqual(20);
  });

  test("no paragraph is squeezed into a ribbon on a wide screen", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await settle(page);

    // An element added as an extra child of a fixed-column grid wraps into the
    // first column, which is often the narrow one. The page still passes an
    // overflow check — nothing is clipped — while a paragraph renders as a
    // vertical ribbon beside an empty half-screen. That is how `.entry-aside`
    // shipped at ~120px wide.
    const ribbons = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>("main p")]
        .filter((node) => (node.textContent ?? "").trim().length > 100)
        .map((node) => ({
          width: Math.round(node.getBoundingClientRect().width),
          text: (node.textContent ?? "").trim().slice(0, 60),
        }))
        .filter((entry) => entry.width > 0 && entry.width < 240),
    );

    expect(
      ribbons,
      "long prose in a column too narrow to read at 1440px",
    ).toEqual([]);
  });

  test("tap targets on the home screen are large enough to hit", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto("/");
    await settle(page);

    const button = page.getByRole("button", { name: "Analyse my squad" });
    const box = await button.boundingBox();

    // 24px is the WCAG 2.2 AA minimum; 44 is the comfortable target.
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(24);
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(24);
  });
});
