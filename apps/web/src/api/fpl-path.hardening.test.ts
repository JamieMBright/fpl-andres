import { describe, expect, it } from "vitest";

import {
  FplPathError,
  resolveFplUpstreamUrl,
} from "../../../../api/_lib/fpl-path";

/**
 * The proxy is unauthenticated and reachable by anyone. Its only defence is
 * that the URL it fetches is one of a handful it was built to fetch.
 *
 * Audit item #74 asked for the path to be normalised before pattern matching,
 * on the grounds that a percent-encoded or dot-segment variant could clear the
 * allow-list in one form and be fetched in another. The variants below were all
 * already refused. What was missing was a guarantee rather than an enumeration,
 * so `resolveFplUpstreamUrl` now compares the resolved URL against the only
 * string that could have been approved and refuses any difference.
 */

const ORIGIN = "https://fantasy.premierleague.com/api/";

describe("resolveFplUpstreamUrl", () => {
  it.each([
    ["/api/fpl/bootstrap-static/", `${ORIGIN}bootstrap-static/`],
    ["/api/fpl/fixtures/", `${ORIGIN}fixtures/`],
    ["/api/fpl/fixtures/?event=7", `${ORIGIN}fixtures/?event=7`],
    ["/api/fpl/entry/12345/", `${ORIGIN}entry/12345/`],
    ["/api/fpl/entry/12345/history/", `${ORIGIN}entry/12345/history/`],
    [
      "/api/fpl/entry/12345/event/7/picks/",
      `${ORIGIN}entry/12345/event/7/picks/`,
    ],
    ["/api/fpl/element-summary/427/", `${ORIGIN}element-summary/427/`],
    [
      "/api/fpl/leagues-classic/314/standings/?page_standings=2",
      `${ORIGIN}leagues-classic/314/standings/?page_standings=2`,
    ],
  ])("resolves %s", (request, expected) => {
    expect(resolveFplUpstreamUrl(request).href).toBe(expected);
  });

  it("drops Vercel's own routing parameters without changing the endpoint", () => {
    expect(resolveFplUpstreamUrl("/api/fpl/fixtures/?event=7").href).toBe(
      `${ORIGIN}fixtures/?event=7`,
    );
  });
});

describe("path traversal and encoding variants", () => {
  // Each entry is a way of writing something other than an allowlisted
  // endpoint, or of writing an allowlisted one in a form that resolves
  // elsewhere. None may produce a URL.
  it.each([
    ["parent segment", "/api/fpl/../admin/"],
    ["parent segment inside", "/api/fpl/entry/../../admin/"],
    ["encoded dot", "/api/fpl/%2e%2e/admin/"],
    ["encoded dot uppercase", "/api/fpl/%2E%2E/admin/"],
    ["encoded slash", "/api/fpl/entry%2f1%2f"],
    ["backslash", "/api/fpl/entry\\1\\"],
    ["encoded backslash", "/api/fpl/entry%5c1%5c"],
    ["double slash", "/api/fpl//entry/1/"],
    ["empty segment inside", "/api/fpl/entry//1/"],
    ["single dot segment", "/api/fpl/entry/./1/"],
    ["double encoded dot", "/api/fpl/%252e%252e/admin/"],
    ["encoded endpoint letter", "/api/fpl/%65ntry/1/"],
    ["scheme relative", "/api/fpl//evil.example.com/"],
    ["absolute upstream", "/api/fpl/https://evil.example.com/"],
    ["userinfo", "/api/fpl/entry@evil.example.com/"],
    ["fragment", "/api/fpl/bootstrap-static/#@evil.example.com"],
    ["outside the proxy prefix", "/api/team/1"],
    ["prefix only", "/api/fpl/"],
    ["unlisted endpoint", "/api/fpl/me/"],
    ["trailing slash missing", "/api/fpl/bootstrap-static"],
    ["semicolon parameter", "/api/fpl/entry/1;evil/"],
    ["newline", "/api/fpl/entry/1/\nHost: evil"],
    ["whitespace", "/api/fpl/entry/ 1/"],
  ])("refuses %s", (_label, request) => {
    expect(() => resolveFplUpstreamUrl(request)).toThrow(FplPathError);
  });

  it("never produces a URL outside the FPL API origin", () => {
    const attempts = [
      "/api/fpl/bootstrap-static/",
      "/api/fpl/entry/1/",
      "/api/fpl/fixtures/?event=1",
      "/api/fpl/element-summary/1/",
      "/api/fpl/leagues-classic/1/standings/",
    ];
    for (const attempt of attempts) {
      const resolved = resolveFplUpstreamUrl(attempt);
      expect(resolved.origin).toBe("https://fantasy.premierleague.com");
      expect(resolved.pathname.startsWith("/api/")).toBe(true);
      expect(resolved.username).toBe("");
      expect(resolved.password).toBe("");
      expect(resolved.hash).toBe("");
    }
  });
});

describe("identifier bounds", () => {
  it("refuses a leading zero, which is a second spelling of the same id", () => {
    expect(() => resolveFplUpstreamUrl("/api/fpl/entry/0123/")).toThrow(
      FplPathError,
    );
  });

  it("refuses entry zero", () => {
    expect(() => resolveFplUpstreamUrl("/api/fpl/entry/0/")).toThrow(
      FplPathError,
    );
  });

  it("holds the event ceiling at the length of a season", () => {
    expect(
      resolveFplUpstreamUrl("/api/fpl/entry/1/event/38/picks/").href,
    ).toContain("event/38");
    expect(() =>
      resolveFplUpstreamUrl("/api/fpl/entry/1/event/39/picks/"),
    ).toThrow(FplPathError);
  });

  it("refuses an entry id beyond the unsigned 32-bit range", () => {
    expect(() => resolveFplUpstreamUrl("/api/fpl/entry/4294967296/")).toThrow(
      /outside the supported range/,
    );
  });
});

describe("query parameters", () => {
  it("refuses any parameter on an endpoint that takes none", () => {
    expect(() =>
      resolveFplUpstreamUrl("/api/fpl/bootstrap-static/?event=1"),
    ).toThrow(/does not accept query parameters/);
  });

  it("refuses an unlisted parameter", () => {
    expect(() => resolveFplUpstreamUrl("/api/fpl/fixtures/?future=1")).toThrow(
      /'future' is not allowed/,
    );
  });

  it("refuses a repeated parameter, which upstream may resolve either way", () => {
    expect(() =>
      resolveFplUpstreamUrl("/api/fpl/fixtures/?event=1&event=2"),
    ).toThrow(/must appear once/);
  });

  it("canonicalises parameter order so the CDN key does not depend on typing", () => {
    const one = resolveFplUpstreamUrl(
      "/api/fpl/leagues-classic/314/standings/?phase=1&page_standings=2",
    );
    const other = resolveFplUpstreamUrl(
      "/api/fpl/leagues-classic/314/standings/?page_standings=2&phase=1",
    );
    expect(one.href).toBe(other.href);
    expect(one.search).toBe("?page_standings=2&phase=1");
  });

  it("refuses a non-integer parameter value", () => {
    expect(() => resolveFplUpstreamUrl("/api/fpl/fixtures/?event=all")).toThrow(
      FplPathError,
    );
  });

  it("refuses a parameter value outside its range", () => {
    expect(() => resolveFplUpstreamUrl("/api/fpl/fixtures/?event=39")).toThrow(
      /outside the supported range/,
    );
  });
});
