import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const REPOSITORY_ROOT = resolve(WEB_ROOT, "..", "..");
const read = (path: string) => readFileSync(resolve(WEB_ROOT, path), "utf8");

describe("website checklist", () => {
  it("puts the primary action before deferred rankings", () => {
    const home = read("src/pages/HomePage.tsx");
    expect(home.indexOf('className="index-grid"')).toBeGreaterThan(-1);
    expect(home.indexOf('className="index-rankings"')).toBeGreaterThan(-1);
    expect(home.indexOf('className="index-grid"')).toBeLessThan(
      home.indexOf('className="index-rankings"'),
    );
  });

  it("keeps local-business claims out of an online-only application", () => {
    const html = read("index.html");
    for (const unsupported of [
      '"LocalBusiness"',
      '"PostalAddress"',
      '"GeoCoordinates"',
      '"aggregateRating"',
      '"Review"',
    ]) {
      expect(html).not.toContain(unsupported);
    }
  });

  it("retains the completed crawler, privacy, FAQ, and social foundations", () => {
    const robots = read("public/robots.txt");
    const sitemap = read("public/sitemap.xml");
    const faq = read("src/pages/FaqPage.tsx");
    const privacy = read("src/pages/PrivacyPage.tsx");
    const index = read("index.html");
    const vercel = readFileSync(
      resolve(REPOSITORY_ROOT, "vercel.json"),
      "utf8",
    );

    expect(robots).toContain("Sitemap:");
    expect(sitemap).toContain("/results");
    expect(faq.match(/q: "/g)?.length ?? 0).toBeGreaterThanOrEqual(5);
    expect(privacy).toContain("Privacy and data");
    expect(index).toContain("/social-card.png");
    expect(vercel).toContain("X-Robots-Tag");
    expect(vercel).toContain("https://www.googletagmanager.com");
    expect(vercel).toContain("https://www.google-analytics.com");
  });
});
