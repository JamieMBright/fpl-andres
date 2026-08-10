import { describe, expect, it } from "vitest";

import {
  POSTURE_HEADINGS,
  chipNote,
  postureFor,
  postureVerdict,
} from "./league-tactics";
import type { LeagueExposure, Standing } from "./mini-league";

/**
 * Ownership is a risk setting, not a return setting: a player is worth his
 * projection whether or not your rivals own him, and what their owning him
 * changes is the spread of where you finish. So position in the league is what
 * decides whether to match the field or leave it.
 */

function standing(place: number, size: number): Standing {
  return {
    place,
    size,
    pointsBehindLeader: (place - 1) * 10,
    pointsAheadOfNext: place < size ? 10 : null,
  };
}

function captained(share: number): LeagueExposure {
  return {
    elementId: 1,
    ownedShare: share,
    captainedShare: share,
    effective: share * 2,
    mine: false,
  };
}

describe("which way to lean", () => {
  it("tells a leader to narrow the spread", () => {
    expect(postureFor(standing(1, 12))).toBe("cover");
  });

  it("tells the last man to widen it", () => {
    expect(postureFor(standing(12, 12))).toBe("differ");
  });

  it("tells the middle to do neither", () => {
    expect(postureFor(standing(6, 12))).toBe("level");
  });

  it("has no view on a league of one", () => {
    expect(postureFor(standing(1, 1))).toBe("level");
  });

  it("has no view on somebody it could not place", () => {
    expect(postureFor(null)).toBe("level");
  });

  it("scales with the size of the league rather than the place", () => {
    // The same place means opposite things in different-sized leagues: fourth
    // of twenty is near the top, fourth of five is next to last. Both are kept
    // clear of the one-third boundary, where floating point puts an exact
    // third on the conservative side.
    expect(postureFor(standing(4, 20))).toBe("cover");
    expect(postureFor(standing(4, 5))).toBe("differ");
  });
});

describe("what it says about it", () => {
  it("names the place and the gap it is arguing from", () => {
    const said = postureVerdict("differ", standing(9, 12));

    expect(said).toContain("9th of 12");
    expect(said).toContain("80 points off the top");
  });

  it("tells somebody behind that copying keeps the gap", () => {
    expect(postureVerdict("differ", standing(9, 12))).toContain(
      "keeps the gap",
    );
  });

  it("tells a leader that owning what they own protects it", () => {
    expect(postureVerdict("cover", standing(1, 12))).toContain(
      "their good weeks",
    );
  });

  it("says so plainly when the reader is not in the squads it read", () => {
    expect(postureVerdict("level", null)).toContain("not in the squads");
  });

  it("gives every posture a heading of its own", () => {
    expect(new Set(Object.values(POSTURE_HEADINGS)).size).toBe(3);
  });

  it("gets the ordinal right on the awkward numbers", () => {
    expect(postureVerdict("level", standing(11, 20))).toContain("11th");
    expect(postureVerdict("level", standing(2, 20))).toContain("2nd");
    expect(postureVerdict("level", standing(3, 20))).toContain("3rd");
  });
});

describe("what a chip is worth against these squads", () => {
  it("warns a chaser off tripling the captain everybody has", () => {
    const said = chipNote("differ", [captained(0.7)]);

    expect(said).toContain("biggest single swing");
  });

  it("calls the same chip the safe version for a leader", () => {
    expect(chipNote("cover", [captained(0.7)])).toContain("safe version");
  });

  it("prefers the bench boost for a leader with no crowded captain", () => {
    expect(chipNote("cover", [captained(0.2)])).toContain("Bench Boost");
  });

  it("prefers the armband for a chaser with no crowded captain", () => {
    expect(chipNote("differ", [captained(0.2)])).toContain("Triple Captain");
  });
});
