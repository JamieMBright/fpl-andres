import { describe, expect, it } from "vitest";

import type { ChipCall } from "./season-plan";
import { chipCallsFor } from "./season-chips";
import type { SolvedGameweek, SolverPlayer } from "./season-solver";

/**
 * The published chip calls belong to the published fifteen. These assert that
 * a solved season takes back the two chips it can size, and does not pretend
 * to the two it cannot.
 */

function player(code: number): SolverPlayer {
  return {
    id: code,
    code,
    name: `P${String(code)}`,
    position: "MID",
    positionId: 3,
    club: "ARS",
    teamId: 1,
    priceTenths: 60,
    basePoints: 4,
    routes: {} as SolverPlayer["routes"],
    startRate: 0.9,
  };
}

function week(
  event: number,
  {
    bench,
    captain,
    // Enough that a rebuild can actually buy a legal fifteen. A squad of two
    // invented players has no realistic sale value of its own.
    bankTenths = 880,
  }: { bench: number[]; captain: number; bankTenths?: number },
): SolvedGameweek {
  const expected: Record<string, number> = { [String(captain)]: 6 };
  bench.forEach((points, index) => {
    expected[String(100 + index)] = points;
  });
  return {
    event,
    deadline: "2026-08-21T17:30:00Z",
    confidence: "projected",
    starters: [player(captain)],
    bench: bench.map((_, index) => player(100 + index)),
    captain: player(captain),
    viceCaptain: player(captain),
    transfersIn: [],
    transfersOut: [],
    opponents: {},
    difficulty: {},
    expected,
    paidTransfers: 0,
    transferCostPoints: 0,
    projectedPoints: 0,
    netExpectedPoints: 0,
    bankAfterTenths: bankTenths,
    freeTransfersBefore: 1,
  };
}

const PUBLISHED: ChipCall[] = [
  { event: 4, chip: "Free Hit", half: "first", gain: 2.5, note: "published" },
  { event: 19, chip: "Wildcard", half: "first", gain: 0.7, note: "published" },
  {
    event: 14,
    chip: "Bench Boost",
    half: "first",
    gain: 10.9,
    note: "published",
  },
  {
    event: 6,
    chip: "Triple Captain",
    half: "first",
    gain: 7.5,
    note: "published",
  },
];

function callOf(calls: readonly ChipCall[], chip: string): ChipCall {
  const found = calls.find((call) => call.chip === chip);
  if (!found) throw new Error(`no ${chip} call`);
  return found;
}

describe("chipCallsFor", () => {
  it("hands back the published calls when nothing has been solved", () => {
    expect(chipCallsFor([], PUBLISHED)).toEqual(PUBLISHED);
  });

  it("boosts the bench in the week this squad's bench is best", () => {
    const calls = chipCallsFor(
      [
        week(2, { bench: [1, 1, 1, 1], captain: 7 }),
        week(3, { bench: [4, 3, 2, 5], captain: 7 }),
        week(4, { bench: [2, 2, 2, 2], captain: 7 }),
      ],
      PUBLISHED,
    );

    const boost = callOf(calls, "Bench Boost");
    expect(boost.event).toBe(3);
    expect(boost.gain).toBe(14);
    // The published week 14 was somebody else's bench.
    expect(boost.note).not.toContain("published");
  });

  it("triples the captain in his biggest week", () => {
    const calls = chipCallsFor(
      [
        week(2, { bench: [1, 1, 1, 1], captain: 7 }),
        week(3, { bench: [1, 1, 1, 1], captain: 8 }),
      ],
      PUBLISHED,
    );

    // Both weeks score the captain at 6; the first solved week wins the tie.
    expect(callOf(calls, "Triple Captain").event).toBe(2);
    expect(callOf(calls, "Triple Captain").gain).toBe(6);
  });

  // The rebuild reads the real player artifact, so a fixture squad of two
  // invented players is beaten by any legal fifteen the budget buys. What is
  // pinned here is that both chips are now solved rather than carried over.
  it("solves the two rebuild chips instead of repeating the published week", () => {
    const calls = chipCallsFor(
      [
        week(2, { bench: [1], captain: 7 }),
        week(3, { bench: [1], captain: 7 }),
      ],
      PUBLISHED,
    );

    for (const chip of ["Free Hit", "Wildcard"] as const) {
      const call = callOf(calls, chip);
      expect(call.note).not.toContain("published");
      expect(call.event).not.toBe(callOf(PUBLISHED, chip).event);
    }
    // One squad cannot be both handed back and kept.
    expect(callOf(calls, "Free Hit").event).not.toBe(
      callOf(calls, "Wildcard").event,
    );
  });

  it("refuses a wildcard that would move fewer than five of the fifteen", () => {
    // The report that motivated it: a Wildcard offered for gameweek 3 against
    // a single transfer. A chip that buys a move the free transfer could have
    // made is a chip thrown away, however well that move scores.
    const calls = chipCallsFor(
      [
        week(2, { bench: [1], captain: 7 }),
        week(3, { bench: [1], captain: 7 }),
      ],
      PUBLISHED,
    );
    const wildcard = callOf(calls, "Wildcard");

    if (wildcard.event === null) {
      expect(wildcard.note).toContain("5 or more");
      return;
    }
    const moves = /moves (\d+) of your fifteen/.exec(wildcard.note);
    expect(moves).not.toBeNull();
    expect(Number(moves?.[1])).toBeGreaterThanOrEqual(5);
  });

  it("prices the wildcard over the run it opens, not one afternoon", () => {
    const calls = chipCallsFor(
      [
        week(2, { bench: [1], captain: 7 }),
        week(3, { bench: [1], captain: 7 }),
      ],
      PUBLISHED,
    );
    const wildcard = callOf(calls, "Wildcard");
    const freeHit = callOf(calls, "Free Hit");

    if (wildcard.event === null) return;
    expect(wildcard.note).toContain("gameweeks it opens");
    // A kept squad scores over several weeks and a free hit over one, so the
    // two numbers cannot be the same measure. They used to be.
    expect(wildcard.gain).toBeGreaterThan(freeHit.gain);
  });

  it("keeps the halves apart", () => {
    const calls = chipCallsFor(
      [
        week(3, { bench: [1, 1, 1, 1], captain: 7 }),
        week(25, { bench: [9, 9, 9, 9], captain: 7 }),
      ],
      PUBLISHED,
    );

    const boosts = calls.filter((call) => call.chip === "Bench Boost");
    expect(boosts.map((call) => call.event)).toEqual([3, 25]);
    expect(boosts.map((call) => call.half)).toEqual(["first", "second"]);
  });

  it("says nothing rather than naming a week worth nothing", () => {
    const calls = chipCallsFor([week(3, { bench: [], captain: 7 })], PUBLISHED);

    expect(callOf(calls, "Bench Boost").event).toBeNull();
    expect(callOf(calls, "Bench Boost").note).toContain("no week");
  });
});
