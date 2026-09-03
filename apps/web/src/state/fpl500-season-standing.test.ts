import { describe, expect, it } from "vitest";

import { sortedStanding, standingHistogram } from "./fpl500-season-standing";

describe("sorted standing", () => {
  it("sorts by total points, highest first", () => {
    const rows = [
      { overallRank: 500, totalPoints: 100 },
      { overallRank: 200, totalPoints: 300 },
      { overallRank: 900, totalPoints: 50 },
    ];

    expect(
      sortedStanding(rows, "points").map((row) => row.totalPoints),
    ).toEqual([300, 100, 50]);
  });

  it("sorts by overall rank, lowest (best) first", () => {
    const rows = [
      { overallRank: 500, totalPoints: 100 },
      { overallRank: 200, totalPoints: 300 },
      { overallRank: 900, totalPoints: 50 },
    ];

    expect(sortedStanding(rows, "rank").map((row) => row.overallRank)).toEqual([
      200, 500, 900,
    ]);
  });

  it("sorts a missing rank to the back rather than the front", () => {
    const rows = [
      { overallRank: null, totalPoints: 400 },
      { overallRank: 100, totalPoints: 50 },
    ];

    expect(sortedStanding(rows, "rank").map((row) => row.overallRank)).toEqual([
      100,
      null,
    ]);
  });
});

describe("standingHistogram", () => {
  it("groups points into fixed-width bins and preserves every manager", () => {
    const bins = standingHistogram(
      [
        { overallRank: 500, totalPoints: 100 },
        { overallRank: 200, totalPoints: 104 },
        { overallRank: 900, totalPoints: 105 },
        { overallRank: null, totalPoints: 111 },
      ],
      "points",
      5,
    );

    expect(bins.map((bin) => [bin.start, bin.end, bin.count])).toEqual([
      [100, 104, 2],
      [105, 109, 1],
      [110, 114, 1],
    ]);
    expect(bins.reduce((total, bin) => total + bin.count, 0)).toBe(4);
  });

  it("omits missing ranks rather than putting them in a fabricated zero bin", () => {
    const bins = standingHistogram(
      [
        { overallRank: null, totalPoints: 400 },
        { overallRank: 101, totalPoints: 50 },
        { overallRank: 199, totalPoints: 60 },
      ],
      "rank",
      100,
    );

    expect(bins).toEqual([{ start: 100, end: 199, count: 2 }]);
  });
});
