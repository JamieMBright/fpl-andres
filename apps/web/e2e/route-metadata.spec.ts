import { expect, test } from "@playwright/test";

test.describe("each route says what it is", () => {
  test("the landing page names the project", async ({ page }) => {
    await page.goto("/");

    await expect(page).toHaveTitle("FPL Andres");
  });

  test("the method page has its own title", async ({ page }) => {
    await page.goto("/methodology");

    await expect(page).toHaveTitle(/How I work · FPL Andres/);
  });

  test("the player pool has its own title", async ({ page }) => {
    await page.goto("/players");

    await expect(page).toHaveTitle(/The player pool · FPL Andres/);
  });

  test("calibration has its own title", async ({ page }) => {
    await page.goto("/calibration");

    await expect(page).toHaveTitle(/Calibration · FPL Andres/);
  });

  test("a dossier names the team it is for", async ({ page }) => {
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

    await expect(page).toHaveTitle(/Team 212279 · FPL Andres/);
  });

  test("the description changes with the route", async ({ page }) => {
    await page.goto("/methodology");
    // The title settles when the split route has mounted; read the meta after.
    await expect(page).toHaveTitle(/How I work/);
    const method = await page
      .locator('meta[name="description"]')
      .getAttribute("content");

    await page.goto("/calibration");
    await expect(page).toHaveTitle(/Calibration/);
    const calibration = await page
      .locator('meta[name="description"]')
      .getAttribute("content");

    expect(method).not.toBe(calibration);
    expect(calibration).toContain("loses");
  });

  test("robots keeps crawlers off the per-team dossiers", async ({
    request,
  }) => {
    const response = await request.get("/robots.txt");

    expect(response.status()).toBe(200);
    expect(await response.text()).toContain("Disallow: /team/");
  });

  test("a sitemap is served", async ({ request }) => {
    const response = await request.get("/sitemap.xml");

    expect(response.status()).toBe(200);
    expect(await response.text()).toContain("/calibration");
  });
});
