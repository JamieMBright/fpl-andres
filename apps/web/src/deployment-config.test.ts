import { describe, expect, it } from "vitest";

import vercelConfig from "../../../vercel.json";

describe("Vercel deployment policy", () => {
  it("restricts executable content while allowing the configured font hosts", () => {
    const globalHeaders = vercelConfig.headers.find(
      ({ source }) => source === "/(.*)",
    );
    const contentSecurityPolicy = globalHeaders?.headers.find(
      ({ key }) => key === "Content-Security-Policy",
    )?.value;

    expect(contentSecurityPolicy).toContain("default-src 'self'");
    expect(contentSecurityPolicy).toContain("script-src 'self'");
    expect(contentSecurityPolicy).toContain(
      "style-src 'self' https://fonts.googleapis.com",
    );
    expect(contentSecurityPolicy).toContain(
      "font-src https://fonts.gstatic.com",
    );
    expect(contentSecurityPolicy).toContain("connect-src 'self'");
    expect(contentSecurityPolicy).toContain("object-src 'none'");
    expect(contentSecurityPolicy).toContain("base-uri 'none'");
    expect(contentSecurityPolicy).toContain("frame-ancestors 'none'");
  });
});
