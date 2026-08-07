import { describe, expect, it } from "vitest";

import { findSpells } from "./SeasonFixtures";
import type { RunMatch } from "../state/fixture-run";

function match(event: number, multiplier: number | null): RunMatch {
  return {
    event,
    opponent: multiplier === null ? "" : "OPP",
    home: true,
    multiplier,
  };
}

describe("findSpells", () => {
  it("names a run of three easy ties for an attacker", () => {
    // A forward's route is what the opponents concede, so high is good. Week 4
    // is hard enough to pull any window containing it back under the margin.
    const spells = findSpells(
      [match(1, 1.3), match(2, 1.25), match(3, 1.2), match(4, 0.8)],
      true,
    );

    expect(spells).toHaveLength(1);
    expect(spells[0]?.kind).toBe("good");
    expect(spells[0]?.from).toBe(1);
    expect(spells[0]?.to).toBe(3);
  });

  it("reads the same fixtures as hard for a defender", () => {
    // A defender's route is what the opponents score, so the identical numbers
    // mean the opposite. A single difficulty scale cannot express this.
    const spells = findSpells(
      [match(1, 1.3), match(2, 1.25), match(3, 1.2), match(4, 0.8)],
      false,
    );

    expect(spells).toHaveLength(1);
    expect(spells[0]?.kind).toBe("hard");
  });

  it("merges overlapping windows into one spell and rescores it", () => {
    const spells = findSpells(
      [match(1, 1.3), match(2, 1.3), match(3, 1.3), match(4, 1.3)],
      true,
    );

    expect(spells).toHaveLength(1);
    expect(spells[0]?.from).toBe(1);
    expect(spells[0]?.to).toBe(4);
    expect(spells[0]?.mean).toBeCloseTo(1.3, 5);
  });

  it("does not call three near-average ties a spell", () => {
    expect(
      findSpells([match(1, 1.05), match(2, 1.02), match(3, 1.04)], true),
    ).toEqual([]);
  });

  it("will not span a blank gameweek", () => {
    // Gameweek 2 is missing, so weeks 1, 3 and 4 are not a run of fixtures.
    expect(
      findSpells([match(1, 1.3), match(3, 1.3), match(4, 1.3)], true),
    ).toEqual([]);
  });

  it("lets an unrated opponent break the run rather than assuming it is average", () => {
    // Gameweek 2 is a promoted club I hold no measurement for. Calling weeks 1,
    // 3 and 4 a spell would claim the schedule is soft across a week I cannot
    // rate at all, so the run is cut instead.
    expect(
      findSpells(
        [match(1, 1.3), match(2, null), match(3, 1.3), match(4, 1.3)],
        true,
      ),
    ).toEqual([]);
  });
});
