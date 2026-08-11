import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const REPOSITORY_ROOT = resolve(WEB_ROOT, "..", "..");
const html = readFileSync(resolve(WEB_ROOT, "index.html"), "utf8");
const sitemap = readFileSync(
  resolve(WEB_ROOT, "public", "sitemap.xml"),
  "utf8",
);
const security = readFileSync(
  resolve(WEB_ROOT, "public", ".well-known", "security.txt"),
  "utf8",
);
const vercel = JSON.parse(
  readFileSync(resolve(REPOSITORY_ROOT, "vercel.json"), "utf8"),
) as {
  headers?: {
    source: string;
    headers: { key: string; value: string }[];
  }[];
};

const SITE_URL = "https://fpl-andres.vercel.app";
const PUBLIC_PATHS = [
  "/",
  "/plan",
  "/players",
  "/analysis",
  "/methodology",
  "/calibration",
  "/fpl500",
  "/faq",
  "/privacy",
] as const;

function attribute(tag: string, name: string): string | null {
  const match = new RegExp(`${name}="([^"]+)"`).exec(tag);
  return match?.[1] ?? null;
}

function metaContent(attributeName: string, attributeValue: string): string {
  const tags = html.match(/<meta\b[^>]*>/g) ?? [];
  const tag = tags.find(
    (candidate) => attribute(candidate, attributeName) === attributeValue,
  );
  expect(
    tag,
    `missing meta ${attributeName}="${attributeValue}"`,
  ).toBeDefined();
  return attribute(tag ?? "", "content") ?? "";
}

describe("share and canonical metadata", () => {
  it("publishes a canonical URL and a complete social card", () => {
    expect(html).not.toContain('<link rel="canonical"');
    expect(html).toContain(`<meta property="og:url" content="${SITE_URL}/" />`);
    expect(html).toContain(
      '<meta property="og:site_name" content="FPL Andres" />',
    );
    expect(html).toContain('<meta property="og:locale" content="en_GB" />');
    expect(metaContent("property", "og:image")).toBe(
      `${SITE_URL}/social-card.png`,
    );
    expect(metaContent("name", "twitter:image")).toBe(
      `${SITE_URL}/social-card.png`,
    );
    const image = readFileSync(resolve(WEB_ROOT, "public", "social-card.png"));
    expect(image.readUInt32BE(16)).toBe(1200);
    expect(image.readUInt32BE(20)).toBe(630);
    expect(image.byteLength).toBeLessThanOrEqual(300 * 1024);
  });
});

describe("sitemap", () => {
  it("uses the sitemap protocol namespace and lists each public route once", () => {
    expect(sitemap).toContain(
      'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
    );
    expect(sitemap).not.toContain("<changefreq>");
    expect(sitemap).not.toContain("<priority>");

    const locations = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
      (match) => new URL(match[1] as string),
    );
    expect(locations.map((location) => location.pathname)).toEqual(
      PUBLIC_PATHS,
    );
    expect(new Set(locations.map((location) => location.href)).size).toBe(
      locations.length,
    );
  });
});

describe("non-public routes", () => {
  it.each(["/team/(.*)", "/kits", "/kits/(.*)"])(
    "serves an X-Robots-Tag for %s",
    (source) => {
      const rule = vercel.headers?.find((entry) => entry.source === source);
      const robots = rule?.headers.find(
        (header) => header.key.toLowerCase() === "x-robots-tag",
      );
      expect(robots?.value).toBe("noindex, nofollow");
    },
  );
});

describe("security contact", () => {
  it("publishes a canonical, expiring private reporting route", () => {
    expect(security).toContain(
      "Contact: https://github.com/JamieMBright/fpl-andres/security/advisories/new",
    );
    expect(security).toContain(
      "Canonical: https://fpl-andres.vercel.app/.well-known/security.txt",
    );
    expect(security).toMatch(/Expires: 2027-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z/);
    expect(security).toContain("Preferred-Languages: en");
  });
});
