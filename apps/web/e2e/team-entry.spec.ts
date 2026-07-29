import { expect, test } from "@playwright/test";

test("opens a public team analysis from the working first screen", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "What should your next FPL move be?" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "What should your next FPL move be?" }),
  ).not.toBeFocused();
  await page.getByLabel("FPL team ID").fill("123456");
  await page.getByRole("button", { name: "Analyse team" }).click();

  await expect(page).toHaveURL(/\/team\/123456$/);
  await expect(
    page.getByRole("heading", { name: "Analysis for team 123456" }),
  ).toBeFocused();
});

test("keeps the working surface inside the mobile viewport", async ({
  page,
}) => {
  await page.goto("/");

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  await expect(page.getByLabel("FPL team ID")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Analyse team" }),
  ).toBeVisible();
});
