import { describe, expect, it } from "vitest";

import { chipAdoption, SECOND_HALF_START } from "./fpl500-chip-adoption";

describe("chip adoption", () => {
  it("accumulates a chip's share across the gameweeks captured so far", () => {
    const [wildcard] = chipAdoption({
      events: [1, 2, 3],
      samples: {
        "01": { attempted: 100, aggregate: { chips: { wildcard: 5 } } },
        "02": { attempted: 100, aggregate: { chips: { wildcard: 3 } } },
        "03": { attempted: 100, aggregate: { chips: {} } },
      },
    }).filter((series) => series.chip === "wildcard");

    expect(wildcard?.points).toEqual([
      { event: 1, share: 0.05 },
      { event: 2, share: 0.08 },
      { event: 3, share: 0.08 },
    ]);
  });

  it("resets every chip's count at the second-half boundary", () => {
    const [wildcard] = chipAdoption({
      events: [19, SECOND_HALF_START, SECOND_HALF_START + 1],
      samples: {
        "19": { attempted: 100, aggregate: { chips: { wildcard: 40 } } },
        "20": { attempted: 100, aggregate: { chips: { wildcard: 10 } } },
        "21": { attempted: 100, aggregate: { chips: { wildcard: 5 } } },
      },
    }).filter((series) => series.chip === "wildcard");

    expect(wildcard?.points).toEqual([
      { event: 19, share: 0.4 },
      { event: 20, share: 0.1 },
      { event: 21, share: 0.15 },
    ]);
  });

  it("returns every chip even where a gameweek recorded none of it", () => {
    const series = chipAdoption({
      events: [1],
      samples: { "01": { attempted: 10, aggregate: { chips: {} } } },
    });

    expect(series.map((entry) => entry.chip).sort()).toEqual([
      "3xc",
      "bboost",
      "freehit",
      "wildcard",
    ]);
    expect(series.every((entry) => entry.points[0]?.share === 0)).toBe(true);
  });

  it("reports zero rather than a guess for a gameweek with no sample", () => {
    const [wildcard] = chipAdoption({
      events: [1, 2],
      samples: {
        "01": { attempted: 10, aggregate: { chips: { wildcard: 1 } } },
      },
    }).filter((series) => series.chip === "wildcard");

    expect(wildcard?.points).toEqual([
      { event: 1, share: 0.1 },
      { event: 2, share: 0 },
    ]);
  });
});
