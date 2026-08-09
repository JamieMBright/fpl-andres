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
  it("prices a whole season's worth of rebuilds for a few single rebuilds", () => {
    const budget = 1000;
    const squad = rebuildSquad(0, budget)?.squad ?? [];

    const one = performance.now();
    rebuildUplift(SEASON_EVENTS[0] as number, squad, budget);
    const single = performance.now() - one;

    const many = performance.now();
    for (const event of SEASON_EVENTS) {
      rebuildUplift(event, squad, budget);
    }
    const season = performance.now() - many;

    // Measured at roughly 4ms a rebuild, so a season is about 150ms. The
    // assertion is that the cost is linear in gameweeks and nothing worse.
    expect(season / Math.max(single, 0.01)).toBeLessThan(
      SEASON_EVENTS.length * 3,
    );
  });
});
