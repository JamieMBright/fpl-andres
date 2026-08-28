import { describe, expect, it } from "vitest";

import { SEASON_EVENTS } from "./season-solver";
import { rebuildSquad, rebuildUplift } from "./squad-rebuild";

/**
 * The chip pass rebuilds a fifteen for every gameweek in the season, on the
 * main thread, after a solve the reader has already waited for. A ratio rather
 * than a duration: parallel workers make wall-clock assertions flaky, and what
 * matters is that thirty-eight rebuilds are not thirty-eight times one.
 */

describe("rebuild cost", () => {
  it("prices a whole season's four Wildcard horizons with linear scaling", () => {
    const budget = 1000;
    const squad = rebuildSquad(0, budget)?.squad ?? [];
    const horizons = [3, 5, 7, 9] as const;

    const one = performance.now();
    for (const horizon of horizons) {
      rebuildUplift(SEASON_EVENTS[0] as number, squad, budget, horizon);
    }
    const single = performance.now() - one;

    const many = performance.now();
    for (const event of SEASON_EVENTS) {
      for (const horizon of horizons) {
        rebuildUplift(event, squad, budget, horizon);
      }
    }
    const season = performance.now() - many;

    // The assertion is that adding gameweeks scales linearly. Absolute time is
    // reported by Vitest but never asserted under a contended worker pool.
    expect(season / Math.max(single, 0.01)).toBeLessThan(
      SEASON_EVENTS.length * 3,
    );
  });
});
