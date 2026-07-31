import { describe, expect, it } from "vitest";

import { clubStrength, rateFixtureRun } from "./fixture-run";

// Permanent FPL club codes. Arsenal are strong, Wolves are not.
const ARSENAL = 3;
const WOLVES = 39;
const PROMOTED = 999_999;

// This season's ids, which have nothing to do with last season's.
const codeByTeamId = new Map([
  [1, ARSENAL],
  [2, WOLVES],
  [3, PROMOTED],
]);

const OURS = 4;
const ourCodes = new Map([...codeByTeamId, [OURS, 14]]);

describe("clubStrength", () => {
  it("finds a club by the code that survives a season change", () => {
    expect(clubStrength(ARSENAL)?.shortName).toBe("ARS");
  });

  it("returns nothing for a club it never measured", () => {
    expect(clubStrength(PROMOTED)).toBeNull();
    expect(clubStrength(undefined)).toBeNull();
  });
});

describe("rateFixtureRun", () => {
  const fixtures = [
    { event: 1, team_h: OURS, team_a: 1 },
    { event: 2, team_h: 2, team_a: OURS },
    { event: 3, team_h: OURS, team_a: 3 },
  ];

  it("rates a defender on what the opponents score", () => {
    const run = rateFixtureRun(ourCodes, fixtures, OURS, "DEF", 2);
    const arsenal = clubStrength(ARSENAL);
    const wolves = clubStrength(WOLVES);

    expect(run.opponents).toEqual(["ARS", "WOL"]);
    expect(run.rating).toBeCloseTo(
      ((arsenal?.attackAway ?? 0) + (wolves?.attackHome ?? 0)) / 2,
      2,
    );
  });

  it("rates a forward on what the opponents concede", () => {
    const run = rateFixtureRun(ourCodes, fixtures, OURS, "FWD", 2);
    const arsenal = clubStrength(ARSENAL);
    const wolves = clubStrength(WOLVES);

    expect(run.rating).toBeCloseTo(
      ((arsenal?.defenceAway ?? 0) + (wolves?.defenceHome ?? 0)) / 2,
      2,
    );
  });

  it("leaves a promoted club unrated rather than calling it average", () => {
    const run = rateFixtureRun(ourCodes, fixtures, OURS, "FWD", 3);

    expect(run.fixtures).toBe(3);
    expect(run.rated).toBe(2);
    expect(run.opponents).toEqual(["ARS", "WOL", ""]);
  });

  it("says nothing at all when no opponent in the run is known", () => {
    const run = rateFixtureRun(
      ourCodes,
      [{ event: 1, team_h: OURS, team_a: 3 }],
      OURS,
      "MID",
      1,
    );

    expect(run.rating).toBeNull();
    expect(run.rated).toBe(0);
  });

  it("counts both halves of a double gameweek", () => {
    const run = rateFixtureRun(
      ourCodes,
      [
        { event: 1, team_h: OURS, team_a: 1 },
        { event: 1, team_h: 2, team_a: OURS },
      ],
      OURS,
      "DEF",
      1,
    );

    expect(run.fixtures).toBe(2);
    expect(run.rated).toBe(2);
  });

  it("counts a blank gameweek as no fixture rather than an easy one", () => {
    const run = rateFixtureRun(
      ourCodes,
      [
        { event: 1, team_h: 1, team_a: 2 },
        { event: 2, team_h: OURS, team_a: 1 },
      ],
      OURS,
      "DEF",
      2,
    );

    expect(run.fixtures).toBe(1);
  });
});
