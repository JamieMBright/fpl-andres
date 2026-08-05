import { describe, expect, it } from "vitest";

import {
  describeFreshness,
  freshnessOf,
  LastGood,
  leastFresh,
  LIVE,
} from "./freshness";

describe("freshness", () => {
  it("reads a live response as live", () => {
    expect(freshnessOf(Response.json({})).stale).toBe(false);
  });

  it("reads the staleness the proxy declared", () => {
    const capturedAt = new Date("2026-08-05T06:00:00Z");
    const response = Response.json(
      {},
      {
        headers: {
          "X-FPL-Stale": "1",
          "X-FPL-Stale-Age": "300",
          "X-FPL-Captured-At": capturedAt.toISOString(),
        },
      },
    );

    const freshness = freshnessOf(response);

    expect(freshness.stale).toBe(true);
    expect(freshness.ageSeconds).toBe(300);
    expect(freshness.capturedAt).toBe(capturedAt.getTime());
  });

  it("falls back to the age when the capture time is unreadable", () => {
    const now = 1_000_000;
    const freshness = freshnessOf(
      Response.json(
        {},
        {
          headers: {
            "X-FPL-Stale": "1",
            "X-FPL-Stale-Age": "60",
            "X-FPL-Captured-At": "not a date",
          },
        },
      ),
      now,
    );

    expect(freshness.capturedAt).toBe(now - 60_000);
  });

  it("reports a view as no fresher than its oldest part", () => {
    const older = { capturedAt: 100, stale: true, ageSeconds: 900 };
    const newer = { capturedAt: 500, stale: true, ageSeconds: 500 };

    expect(leastFresh([LIVE, newer, older])).toEqual(older);
    expect(leastFresh([LIVE, LIVE])).toEqual(LIVE);
  });

  it("says nothing about a live view and names the age of a stale one", () => {
    expect(describeFreshness(LIVE)).toBe("");
    expect(
      describeFreshness({ capturedAt: 0, stale: true, ageSeconds: 600 }),
    ).toContain("10 minutes ago");
    expect(
      describeFreshness({ capturedAt: 0, stale: true, ageSeconds: 7_200 }),
    ).toContain("2 hours ago");
    expect(
      describeFreshness({ capturedAt: 0, stale: true, ageSeconds: null }),
    ).toContain("not the current one");
  });

  it("returns a remembered value marked stale, and nothing when it was forgotten", () => {
    const held = new LastGood<string>();
    expect(held.recall()).toBeNull();

    held.remember("pool", Date.now() - 120_000);
    const recalled = held.recall();
    expect(recalled?.value).toBe("pool");
    expect(recalled?.freshness.stale).toBe(true);
    expect(recalled?.freshness.ageSeconds).toBeGreaterThanOrEqual(119);

    held.forget();
    expect(held.recall()).toBeNull();
  });
});
