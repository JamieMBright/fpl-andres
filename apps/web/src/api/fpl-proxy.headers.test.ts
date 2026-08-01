import { describe, expect, it, vi } from "vitest";

import { createFplProxyResponse } from "../../../../api/_lib/fpl-proxy";

/**
 * Audit items #75 and #76, both of which the code already satisfied.
 *
 * #75 asked for the upstream `content-type` to be checked before the body is
 * parsed. It was, but with a substring search, so the check now compares the
 * media type. #76 asked for entry-specific responses to be marked private. They
 * already were, by falling through an allow-list of two public shapes.
 *
 * Neither was a bug. Both were untested, which is how a claim like this becomes
 * plausible in the first place, and how the property would be lost in a later
 * edit without anything noticing.
 */

function upstream(body: string, contentType: string | null): typeof fetch {
  const headers = new Headers();
  if (contentType !== null) headers.set("Content-Type", contentType);
  return vi
    .fn<typeof fetch>()
    .mockResolvedValue(new Response(body, { status: 200, headers }));
}

describe("upstream content type", () => {
  it.each([
    ["application/json", true],
    ["application/json; charset=utf-8", true],
    ["APPLICATION/JSON", true],
    ["  application/json  ", true],
    ["application/vnd.fpl+json", true],
  ])("accepts %s", async (contentType, _accepted) => {
    const response = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      upstream('{"ok":true}', contentType),
    );
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
  });

  it.each([
    ["a missing header", null],
    ["an empty header", ""],
    ["an HTML error page", "text/html; charset=utf-8"],
    ["plain text", "text/plain"],
    ["an octet stream", "application/octet-stream"],
    // The substring check this replaced would have accepted the next two.
    ["JSON named in a parameter", "text/html; charset=application/json"],
    ["JSON as a prefix of another type", "application/jsonp"],
  ])("refuses %s as an unexpected format", async (_label, contentType) => {
    const fetchUpstream = upstream(
      "<html>Attention Required</html>",
      contentType,
    );
    const response = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      fetchUpstream,
    );

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toMatchObject({
      reason: "unexpected_format",
    });
  });

  it("never lets the upstream body reach the caller when the type is wrong", async () => {
    // A WAF interstitial is HTML, and an HTML page served to a JSON client is
    // how a challenge page ends up parsed as a squad.
    const response = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      upstream("<html>blocked by upstream</html>", "text/html"),
    );
    const text = await response.text();
    expect(text).not.toContain("blocked by upstream");
  });
});

describe("cache policy", () => {
  it.each([
    ["/api/fpl/bootstrap-static/", "public, s-maxage=60"],
    ["/api/fpl/fixtures/", "public, s-maxage=60"],
    ["/api/fpl/element-summary/427/", "public, s-maxage=300"],
  ])(
    "marks %s public because every caller gets the same bytes",
    async (path, prefix) => {
      const response = await createFplProxyResponse(
        path,
        "GET",
        upstream("{}", "application/json"),
      );
      expect(response.headers.get("Cache-Control")).toContain(prefix);
    },
  );

  it.each([
    "/api/fpl/entry/12345/",
    "/api/fpl/entry/12345/history/",
    "/api/fpl/entry/12345/event/7/picks/",
    "/api/fpl/leagues-classic/314/standings/",
  ])("marks %s private, so a shared CDN never holds it", async (path) => {
    const response = await createFplProxyResponse(
      path,
      "GET",
      upstream("{}", "application/json"),
    );
    const policy = response.headers.get("Cache-Control");
    expect(policy).toBe("private, no-store");
    expect(policy).not.toContain("public");
    expect(policy).not.toContain("s-maxage");
  });

  it("never caches an error, whatever the path", async () => {
    const response = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      upstream("nope", "text/html"),
    );
    expect(response.headers.get("Cache-Control")).toBe("no-store");
  });

  it("keeps a new allowlisted endpoint private until it is named public", async () => {
    // The default is the safe one on purpose: adding a path to fpl-path.ts
    // makes it uncacheable, not public. This asserts the direction of the
    // fallthrough rather than any one path.
    const response = await createFplProxyResponse(
      "/api/fpl/entry/1/",
      "GET",
      upstream("{}", "application/json"),
    );
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  });
});
