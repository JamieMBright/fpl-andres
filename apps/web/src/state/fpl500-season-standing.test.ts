import { describe, expect, it } from "vitest";

import { sortedStanding } from "./fpl500-season-standing";

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
