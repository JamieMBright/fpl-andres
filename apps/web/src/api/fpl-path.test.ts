import { describe, expect, it } from "vitest";

import {
  FplPathError,
  normalizeVercelProxyUrl,
  resolveFplUpstreamUrl,
} from "../../../../api/_lib/fpl-path";

describe("FPL proxy path grammar", () => {
  it.each([
    [
      "/api/fpl/bootstrap-static/",
      "https://fantasy.premierleague.com/api/bootstrap-static/",
    ],
    [
      "/api/fpl/fixtures/?event=38",
      "https://fantasy.premierleague.com/api/fixtures/?event=38",
    ],
    [
      "/api/fpl/entry/123/history/",
      "https://fantasy.premierleague.com/api/entry/123/history/",
    ],
    [
      "/api/fpl/entry/123/event/5/picks/",
      "https://fantasy.premierleague.com/api/entry/123/event/5/picks/",
    ],
    [
      "/api/fpl/leagues-classic/314/standings/?phase=2&page_standings=3",
      "https://fantasy.premierleague.com/api/leagues-classic/314/standings/?page_standings=3&phase=2",
    ],
  ])("maps %s to the fixed upstream host", (requestUrl, expected) => {
    expect(resolveFplUpstreamUrl(requestUrl).href).toBe(expected);
  });

  it.each([
    [
      "/api/fpl/bootstrap-static/?path=bootstrap-static",
      "/api/fpl/bootstrap-static/",
    ],
    ["/api/fpl/fixtures/?event=5&path=fixtures", "/api/fpl/fixtures/?event=5"],
    [
      "/api/fpl/entry/123/history/?...path=entry%2F123%2Fhistory",
      "/api/fpl/entry/123/history/",
    ],
  ])(
    "removes Vercel catch-all route metadata from %s",
    (requestUrl, expected) => {
      expect(normalizeVercelProxyUrl(requestUrl)).toBe(expected);
    },
  );

  it.each([
    "/api/fpl/foo/",
    "/api/fpl/../secret",
    "/api/fpl/%2e%2e/secret",
    "/api/fpl/https://example.com/",
    "/api/fpl/entry/abc/",
    "/api/fpl/entry/0/",
    "/api/fpl/entry/1/event/39/picks/",
    "/api/fpl/element-summary/2001/",
    "/api/fpl/fixtures/?event=0",
    "/api/fpl/fixtures/?event=1&host=example.com",
    "/api/fpl/bootstrap-static/?event=1",
  ])("rejects unsupported or unsafe URL %s", (requestUrl) => {
    expect(() => resolveFplUpstreamUrl(requestUrl)).toThrow(FplPathError);
  });
});
