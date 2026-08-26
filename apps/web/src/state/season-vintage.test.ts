import { describe, expect, it } from "vitest";

import { readSeasonVintage } from "./season-vintage";

function events(finished: number, total = 38) {
  return Array.from({ length: total }, (_, index) => ({
    id: index + 1,
    finished: index < finished,
    deadline_time: `2026-08-${String(21 + index).padStart(2, "0")}T17:30:00Z`,
  }));
}

describe("readSeasonVintage", () => {
  it("reads a full pre-season pool as last season's record", () => {
    const vintage = readSeasonVintage(events(0), 3420);

    expect(vintage.state).toBe("previous_season");
    expect(vintage.season).toBe("2025-26");
    expect(vintage.completedGameweeks).toBe(0);
  });

  it("switches to the live season once a gameweek has finished", () => {
    const vintage = readSeasonVintage(events(1), 90);

    expect(vintage.state).toBe("live_season");
    expect(vintage.season).toBe("2026-27");
    expect(vintage.completedGameweeks).toBe(1);
  });

  /*
   * The window this exists for. FPL wipes the season totals at the rollover but
   * marks no event finished until the first gameweek is scored, so for a few
   * days every column reads zero. Plotting that draws 500 players on the origin
   * and calls it analysis.
   */
  it("refuses the gap between the totals being wiped and the first result", () => {
    const vintage = readSeasonVintage(events(0), 0);

    expect(vintage.state).toBe("unavailable");
  });

  it("refuses a pool too thin to be a completed season", () => {
    expect(readSeasonVintage(events(0), 200).state).toBe("unavailable");
  });

  it("derives the season label from the first deadline, not the clock", () => {
    const summer = events(0).map((event) => ({
      ...event,
      deadline_time: "2031-08-15T17:30:00Z",
    }));

    expect(readSeasonVintage(summer, 3000).season).toBe("2030-31");
  });

  it("has no vintage at all when the event list is empty", () => {
    expect(readSeasonVintage([], 3420).state).toBe("unavailable");
  });
});

describe("minimum minutes default", () => {
  it("asks for 450 minutes of a completed season", () => {
    expect(readSeasonVintage(events(0), 3420).defaultMinimumMinutes).toBe(450);
  });

  /*
   * One full match minus stoppage each gameweek: this keeps the floor near
   * regular starters early on, while still staying below the hard maximum.
   */
  it("scales the threshold down early in a live season", () => {
    expect(readSeasonVintage(events(2), 180).defaultMinimumMinutes).toBe(160);
    expect(readSeasonVintage(events(10), 900).defaultMinimumMinutes).toBe(800);
  });
});
