import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import vercelConfig from "../../../vercel.json";

const SOURCE_ROOT = join(__dirname);

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)
      ? [path]
      : [];
  });
}

function directive(policy: string, name: string): string[] {
  const found = policy
    .split(";")
    .map((part) => part.trim())
    .find((part) => part === name || part.startsWith(`${name} `));
  return found
    ? found.slice(name.length).trim().split(/\s+/).filter(Boolean)
    : [];
}

function contentSecurityPolicy(): string {
  const globalHeaders = vercelConfig.headers.find(
    ({ source }) => source === "/(.*)",
  );
  const value = globalHeaders?.headers.find(
    ({ key }) => key === "Content-Security-Policy",
  )?.value;
  if (!value) throw new Error("no Content-Security-Policy in vercel.json");
  return value;
}

describe("Vercel deployment policy", () => {
  it("restricts executable content while allowing the configured font hosts", () => {
    const policy = contentSecurityPolicy();

    expect(policy).toContain("default-src 'self'");
    expect(policy).toContain("script-src 'self'");
    expect(policy).toContain("style-src 'self' https://fonts.googleapis.com");
    expect(policy).toContain("font-src https://fonts.gstatic.com");
    expect(policy).toContain("connect-src 'self'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("base-uri 'none'");
    expect(policy).toContain("frame-ancestors 'none'");
  });

  /**
   * The dev server does not apply `vercel.json` headers, so a host missing from
   * the policy looks perfectly fine locally and blocks in production only. That
   * is how the API routes went down for six days. Read the hosts out of the
   * source instead of trusting anyone to remember.
   */
  it("permits every external host the source loads images from", () => {
    const allowed = directive(contentSecurityPolicy(), "img-src");

    const hosts = new Set<string>();
    for (const file of sourceFiles(SOURCE_ROOT)) {
      const contents = readFileSync(file, "utf8");
      // File-level: does this module both name an external origin and deal in
      // image files? Deliberately broad. A false positive costs one line in the
      // policy; a false negative is a production-only outage.
      if (!/\.(png|jpe?g|gif|webp|avif)\b/i.test(contents)) continue;
      for (const [, origin] of contents.matchAll(
        /["'`](https:\/\/[a-z0-9.-]+)[/"'`]/gi,
      )) {
        if (origin) hosts.add(origin);
      }
    }

    expect(
      hosts.size,
      "no external image hosts found — has the scan broken?",
    ).toBeGreaterThan(0);

    for (const host of hosts) {
      expect(
        allowed,
        `${host} is used for images in source but is absent from img-src`,
      ).toContain(host);
    }
  });
});
