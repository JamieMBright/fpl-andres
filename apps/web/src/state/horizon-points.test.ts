import { describe, expect, it } from "vitest";

import {
  DEFAULT_HORIZON,
  HORIZONS,
  horizonPoints,
  horizonPointsByCode,
  horizonsAvailable,
} from "./horizon-points";
import { SEASON_EVENTS, SEASON_PLAYERS } from "./season-solver";

/**
 * A transfer is made for the run a player is about to have, not for Saturday.
 * These pin the two properties that make the number worth sorting on: it is a
 * plain sum of the horizon, and it refuses rather than shortening near the end.
 */

const SOMEBODY = SEASON_PLAYERS[0]?.code ?? 0;

describe("horizonPoints", () => {
  it("adds up more gameweeks as the horizon lengthens", () => {
    const one = horizonPoints(SOMEBODY, 1);
    const nine = horizonPoints(SOMEBODY, 9);

    expect(one).not.toBeNull();
    expect(nine).not.toBeNull();
    expect(nine!).toBeGreaterThanOrEqual(one!);
  });

  it("is the sum of the weeks it covers, not a discounted one", () => {
    // Three separate one-week reads from the same start have to add to the
    // three-week figure, or the number is a weighting rather than a total.
    const start = SEASON_EVENTS[0]!;
    const weekly = SEASON_EVENTS.slice(0, 3).map(
      (event) => horizonPoints(SOMEBODY, 1, event) ?? 0,
    );
    const three = horizonPoints(SOMEBODY, 3, start);

    expect(three).toBeCloseTo(
      weekly.reduce((total, value) => total + value, 0),
      6,
    );
  });

  it("refuses a horizon that runs off the end of the season", () => {
    const last = SEASON_EVENTS.at(-1);
    expect(last).toBeDefined();

    // One gameweek left, so anything longer would total fewer weeks than
    // everyone else's and sort him last for a reason that is not about him.
    expect(horizonPoints(SOMEBODY, 1, last)).not.toBeNull();
    expect(horizonPoints(SOMEBODY, 3, last)).toBeNull();
  });

  it("has nothing to say about a player it has no record for", () => {
    expect(horizonPoints(-1, 5)).toBeNull();
  });

  it("refuses a gameweek that is not in the season", () => {
    expect(horizonPoints(SOMEBODY, 5, 999)).toBeNull();
  });
});

describe("horizonPointsByCode", () => {
  it("agrees with the single-player read", () => {
    const all = horizonPointsByCode(DEFAULT_HORIZON);

    expect(all.get(SOMEBODY)).toBeCloseTo(
      horizonPoints(SOMEBODY, DEFAULT_HORIZON) ?? 0,
      6,
    );
  });

  it("covers every player the season knows", () => {
    expect(horizonPointsByCode(1).size).toBe(SEASON_PLAYERS.length);
  });

  it("gives nothing at all rather than a short season", () => {
    expect(horizonPointsByCode(9, SEASON_EVENTS.at(-1)).size).toBe(0);
  });
});

describe("horizonsAvailable", () => {
  it("offers only the horizons the calendar can still fill", () => {
    expect(horizonsAvailable()).toEqual([...HORIZONS]);
    expect(horizonsAvailable(SEASON_EVENTS.at(-1))).toEqual([1]);
  });
});
