import { describe, expect, it } from "vitest";

import type { ChipCall } from "./season-plan";
import {
  MINIMUM_FREE_HIT_CHANGES,
  MINIMUM_WILDCARD_CHANGES,
  WILDCARD_HORIZONS,
} from "./chip-rules";
import {
  chipCallsByEvent,
  chipCallsFor,
  freeHitSegmentGain,
  plannedRebuilds,
  resolveChipClashes,
  wildcardRunGain,
} from "./season-chips";
import { rebuildSquad } from "./squad-rebuild";
import {
  SEASON_EVENTS,
  SEASON_PLAYERS,
  bestElevenPoints,
  type SolvedGameweek,
  type SolverPlayer,
} from "./season-solver";

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
    budgetBeforeTenths: bankTenths + (bench.length + 1) * 60,
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
  it("pins broad rental and permanent rebuild thresholds", () => {
    expect(MINIMUM_FREE_HIT_CHANGES).toBe(10);
    expect(MINIMUM_WILDCARD_CHANGES).toBe(5);
    expect(WILDCARD_HORIZONS).toEqual([3, 5, 7, 9]);
  });

  it("allows adjacent unlimited chips from different halves", () => {
    const calls: ChipCall[] = [
      { event: 19, chip: "Free Hit", half: "first", gain: 8, note: "rental" },
      {
        event: 20,
        chip: "Wildcard",
        half: "second",
        gain: 10,
        note: "rebuild",
      },
    ];

    const scheduled = chipCallsFor([], calls);

    expect(callOf(scheduled, "Free Hit").event).toBe(19);
    expect(callOf(scheduled, "Wildcard").event).toBe(20);
  });

  it("charges a Free Hit for the restored run after the FT reset", () => {
    const squad = rebuildSquad(0, 1000, 1)?.squad ?? [];
    expect(squad).toHaveLength(15);
    const heldIds = new Set(squad.map((player) => player.id));
    const used = new Set<number>();
    const replacements = squad.slice(0, 2).map((outgoing) => {
      const replacement = SEASON_PLAYERS.find(
        (candidate) =>
          !heldIds.has(candidate.id) &&
          !used.has(candidate.id) &&
          candidate.position === outgoing.position,
      );
      if (replacement) used.add(replacement.id);
      return replacement;
    });
    expect(replacements.every(Boolean)).toBe(true);
    const incoming = replacements.filter(
      (player): player is SolverPlayer => player !== undefined,
    );
    const changed = [
      ...squad.filter(
        (player) =>
          !squad.slice(0, 2).some((outgoing) => outgoing.id === player.id),
      ),
      ...incoming,
    ];
    const first = {
      ...week(SEASON_EVENTS[0] as number, { bench: [1], captain: 7 }),
      starters: squad.slice(0, 11),
      bench: squad.slice(11),
    };
    const second = {
      ...week(SEASON_EVENTS[1] as number, { bench: [1], captain: 7 }),
      starters: changed.slice(0, 11),
      bench: changed.slice(11),
      transfersOut: squad.slice(0, 2),
      transfersIn: incoming,
      netExpectedPoints: bestElevenPoints(changed, 1),
    };

    expect(freeHitSegmentGain(0, [first, second], squad, 0)).toBeCloseTo(-4, 6);
  });

  it("prices a late-first-half Wildcard through gameweek 25", () => {
    const squad = rebuildSquad(0, 1000, 9)?.squad ?? [];
    expect(squad).toHaveLength(15);
    const start = SEASON_EVENTS.findIndex((event) => event === 17);
    const weeks = SEASON_EVENTS.slice(0, start + 9).map((event, index) => ({
      ...week(event, { bench: [1], captain: 7 }),
      starters: squad.slice(0, 11),
      bench: squad.slice(11),
      netExpectedPoints: bestElevenPoints(squad, index) - 1,
    }));

    expect(wildcardRunGain(squad, start, weeks, 9)).toBeCloseTo(9, 6);
  });

  it("does not call one remaining gameweek an xPts9 Wildcard horizon", () => {
    const calls = chipCallsFor(
      [week(38, { bench: [1, 1, 1, 1], captain: 7 })],
      PUBLISHED,
    );

    const wildcard = callOf(calls, "Wildcard");
    expect(wildcard.event).toBeNull();
    expect(wildcard.note).not.toContain("9 gameweeks");
  });

  it("reports the remaining Free Hit replay length near season end", () => {
    const calls = chipCallsFor(
      SEASON_EVENTS.slice(-4).map((event) =>
        week(event, { bench: [1, 1, 1, 1], captain: 7 }),
      ),
      PUBLISHED,
    );
    const freeHit = callOf(calls, "Free Hit");

    if (freeHit.event !== null) {
      expect(freeHit.note).toMatch(
        /over the [1-4]-gameweek restored-squad replay/,
      );
      expect(freeHit.note).not.toContain("nine-week");
    }
  });

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
      ["Free Hit:first", "Wildcard:first", "Triple Captain:first"],
    );

    const boost = callOf(calls, "Bench Boost");
    expect(boost.event).toBe(3);
    expect(boost.gain).toBe(14);
    // The published week 14 was somebody else's bench.
    expect(boost.note).not.toContain("published");
  });

  it("triples the captain in his biggest week", () => {
    // Free Hit and Wildcard are priced by rebuilding against the real player
    // artifact, so their gain moves every time that artifact is republished.
    // One of them outscoring this fixture's captain would take gameweek 2 and
    // leave the captain unplayed, which says nothing about the tie-break under
    // test. Spending them keeps the question to the one chip.
    const calls = chipCallsFor(
      [
        week(2, { bench: [1, 1, 1, 1], captain: 7 }),
        week(3, { bench: [1, 1, 1, 1], captain: 8 }),
      ],
      PUBLISHED,
      ["Free Hit:first", "Wildcard:first", "Bench Boost:first"],
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
    const weeks = SEASON_EVENTS.slice(0, 9).map((event, index) => {
      const remaining = 9 - index;
      const horizon = [...WILDCARD_HORIZONS]
        .reverse()
        .find((candidate) => candidate <= remaining);
      const rebuilt = rebuildSquad(index, 1000, horizon ?? 1);
      expect(rebuilt).not.toBeNull();
      const squad = rebuilt?.squad ?? [];
      return {
        ...week(event, { bench: [1], captain: 7 }),
        starters: squad.slice(0, 11),
        bench: squad.slice(11),
        bankAfterTenths: rebuilt?.bankTenths ?? 0,
        netExpectedPoints: bestElevenPoints(squad, index) - 1,
      };
    });
    const calls = chipCallsFor(weeks, PUBLISHED);
    const wildcard = callOf(calls, "Wildcard");

    expect(wildcard.event).toBeNull();
    expect(wildcard.note).toContain("5 or more");
  });

  it("never advises a free hit below ten changes", () => {
    const calls = chipCallsFor(
      [
        week(2, { bench: [1], captain: 7 }),
        week(3, { bench: [1], captain: 7 }),
      ],
      PUBLISHED,
    );
    const freeHit = callOf(calls, "Free Hit");

    expect(freeHit.event).not.toBeNull();
    const moves = /a (\d+)-change xPts1 rental/.exec(freeHit.note);
    expect(moves).not.toBeNull();
    expect(Number(moves?.[1])).toBeGreaterThanOrEqual(10);
    expect(freeHit.changes).toBeGreaterThanOrEqual(10);
    expect(freeHit.incoming).toHaveLength(freeHit.changes ?? 0);
    expect(freeHit.outgoing?.length).toBeGreaterThan(0);
    expect(freeHit.squadElementIds).toHaveLength(15);
  });

  it("measures Free Hit turnover before the ordinary transfer it replaces", () => {
    const planned = week(2, { bench: [1], captain: 7 });
    planned.transfersIn = [player(7)];
    planned.transfersOut = [player(999)];

    const freeHit = callOf(chipCallsFor([planned], PUBLISHED), "Free Hit");

    expect(freeHit.event).not.toBeNull();
    expect(freeHit.changes).toBeGreaterThanOrEqual(10);
    expect(freeHit.outgoing).toContain("P999");
  });

  it("does not badge an ordinary week with an advisory rebuild chip", () => {
    const calls = [
      { event: 4, chip: "Free Hit", half: "first", gain: 8, note: "advice" },
      { event: 6, chip: "Wildcard", half: "first", gain: 9, note: "advice" },
      {
        event: 8,
        chip: "Triple Captain",
        half: "first",
        gain: 6,
        note: "advice",
      },
    ];

    const displayed = chipCallsByEvent(calls, [
      { event: 4 },
      { event: 6 },
      { event: 8 },
    ]);

    expect(displayed.has(4)).toBe(false);
    expect(displayed.has(6)).toBe(false);
    expect(displayed.get(8)?.chip).toBe("Triple Captain");
  });

  it("badges a Free Hit only after that gameweek is re-solved", () => {
    const call = {
      event: 4,
      chip: "Free Hit",
      half: "first",
      gain: 8,
      note: "advice",
    };

    const displayed = chipCallsByEvent(
      [call],
      [{ event: 4, chip: "Free Hit" }],
    );

    expect(displayed.get(4)).toEqual(call);
  });

  it("badges a committed Wildcard without exposing an advisory Wildcard", () => {
    const call = {
      event: 6,
      chip: "Wildcard",
      half: "first",
      gain: 8,
      note: "advice",
    };

    expect(chipCallsByEvent([call], [{ event: 6 }]).has(6)).toBe(false);
    expect(
      chipCallsByEvent([call], [{ event: 6 }], {
        chip: "Wildcard",
        event: 6,
      }).get(6),
    ).toEqual(call);
  });

  it("prices the wildcard over the run it opens, not one afternoon", () => {
    const calls = chipCallsFor(
      SEASON_EVENTS.slice(0, 9).map((event) =>
        week(event, { bench: [1], captain: 7 }),
      ),
      PUBLISHED,
    );
    const wildcard = callOf(calls, "Wildcard");
    const freeHit = callOf(calls, "Free Hit");

    expect(wildcard.event).not.toBeNull();
    expect(wildcard.note).toContain("gameweeks it opens");
    expect(wildcard.squadElementIds).toHaveLength(15);
    // A kept squad scores over several weeks and a free hit over one, so the
    // two numbers cannot be the same measure. They used to be.
    expect(wildcard.gain).toBeGreaterThan(freeHit.gain);
  });

  it("hands only complete advised rebuilds to the second solve", () => {
    const squadElementIds = Array.from({ length: 15 }, (_, index) => index + 1);
    const plans = plannedRebuilds([
      {
        event: 2,
        chip: "Free Hit",
        half: "first",
        gain: 5,
        note: "rental",
        squadElementIds,
      },
      {
        event: null,
        chip: "Wildcard",
        half: "first",
        gain: 0,
        note: "blocked",
        squadElementIds,
      },
    ]);

    expect(plans.freeHitPlans).toEqual([{ event: 2, squadElementIds }]);
    expect(plans.wildcardPlans).toEqual([]);
  });

  it("resolves clashes introduced by repricing chips after the second solve", () => {
    const resolved = resolveChipClashes([
      {
        event: 2,
        chip: "Free Hit",
        half: "first",
        gain: 5.7,
        note: "rental",
      },
      {
        event: 2,
        chip: "Triple Captain",
        half: "first",
        gain: 5.5,
        note: "armband",
      },
    ]);

    expect(callOf(resolved, "Free Hit").event).toBe(2);
    expect(callOf(resolved, "Triple Captain").event).toBeNull();
  });

  it("keeps the halves apart", () => {
    const calls = chipCallsFor(
      [
        week(3, { bench: [1, 1, 1, 1], captain: 7 }),
        week(25, { bench: [9, 9, 9, 9], captain: 7 }),
      ],
      PUBLISHED,
      [
        "Free Hit:first",
        "Wildcard:first",
        "Triple Captain:first",
        "Free Hit:second",
        "Wildcard:second",
        "Triple Captain:second",
      ],
    );

    const boosts = calls.filter((call) => call.chip === "Bench Boost");
    expect(boosts.map((call) => call.half)).toEqual(["first", "second"]);
    expect(boosts[1]?.event).toBe(25);
    expect(calls.filter((call) => call.event === 3)).toHaveLength(1);
  });

  it("says nothing rather than naming a week worth nothing", () => {
    const calls = chipCallsFor(
      [week(3, { bench: [0, 0, 0, 0], captain: 7 })],
      PUBLISHED,
    );

    expect(callOf(calls, "Bench Boost").event).toBeNull();
    expect(callOf(calls, "Bench Boost").note).toContain("no week");
  });

  it("does not offer a chip the manager says he has already played", () => {
    const calls = chipCallsFor([], PUBLISHED, [
      "Bench Boost:first",
      "Wildcard:first",
    ]);

    expect(calls.map((call) => call.chip)).not.toContain("Bench Boost");
    expect(calls.map((call) => call.chip)).not.toContain("Wildcard");
    expect(calls.length).toBeGreaterThan(0);
  });

  it("still solves the chips he has left", () => {
    // The two rebuild chips are spent alongside the Bench Boost he has played,
    // for the same reason as above: their gain comes from the real artifact and
    // would otherwise decide gameweek 2 on data rather than on this fixture.
    const calls = chipCallsFor(
      [
        week(2, { bench: [1, 1, 1, 1], captain: 7 }),
        week(3, { bench: [4, 3, 2, 5], captain: 7 }),
      ],
      PUBLISHED,
      ["Bench Boost:first", "Free Hit:first", "Wildcard:first"],
    );

    expect(calls.map((call) => call.chip)).not.toContain("Bench Boost");
    expect(callOf(calls, "Triple Captain").event).toBe(2);
  });

  it("plays a committed chip in the week he named, not the best one", () => {
    const calls = chipCallsFor(
      [
        week(2, { bench: [1, 1, 1, 1], captain: 7 }),
        week(3, { bench: [4, 3, 2, 5], captain: 7 }),
      ],
      PUBLISHED,
      [],
      { chip: "Bench Boost", event: 2 },
    );

    const boost = callOf(calls, "Bench Boost");
    expect(boost.event).toBe(2);
    expect(boost.gain).toBe(4);
  });

  it("says what the week he named costs him against the week it would pick", () => {
    const calls = chipCallsFor(
      [
        week(2, { bench: [1, 1, 1, 1], captain: 7 }),
        week(3, { bench: [4, 3, 2, 5], captain: 7 }),
      ],
      PUBLISHED,
      [],
      { chip: "Bench Boost", event: 2 },
    );

    expect(callOf(calls, "Bench Boost").note).toContain("gameweek 3");
    expect(callOf(calls, "Bench Boost").note).toContain("14.0");
  });

  it("leaves the other chips alone when one is committed", () => {
    const calls = chipCallsFor(
      [
        week(2, { bench: [1, 1, 1, 1], captain: 7 }),
        week(3, { bench: [4, 3, 2, 5], captain: 7 }),
      ],
      PUBLISHED,
      [],
      { chip: "Bench Boost", event: 2 },
    );

    expect(callOf(calls, "Triple Captain").event).toBeNull();
    expect(callOf(calls, "Triple Captain").note).toContain(
      "already using gameweek 2",
    );
  });

  it("never advises two chips in the same gameweek", () => {
    const calls = chipCallsFor(
      [
        week(2, { bench: [4, 3, 2, 5], captain: 7 }),
        week(3, { bench: [1, 1, 1, 1], captain: 8 }),
      ],
      PUBLISHED,
    );
    const events = calls.flatMap((call) =>
      call.event === null ? [] : [call.event],
    );

    expect(new Set(events).size).toBe(events.length);
  });

  it("keeps the higher-gain chip and drops stale rebuild details on a clash", () => {
    const calls = [
      {
        event: 6,
        chip: "Free Hit",
        half: "first",
        gain: 12,
        note: "rental",
        changes: 10,
        incoming: ["In"],
        outgoing: ["Out"],
      },
      {
        event: 6,
        chip: "Triple Captain",
        half: "first",
        gain: 5,
        note: "armband",
      },
    ];

    const scheduled = chipCallsFor([], calls);
    const freeHit = callOf(scheduled, "Free Hit");
    const triple = callOf(scheduled, "Triple Captain");

    expect(freeHit.event).toBe(6);
    expect(triple.event).toBeNull();
    expect(triple.incoming).toBeUndefined();
    expect(triple.outgoing).toBeUndefined();
  });

  it("lets a committed chip keep its week when another chip would clash", () => {
    const calls = chipCallsFor(
      [week(2, { bench: [4, 3, 2, 5], captain: 7 })],
      PUBLISHED,
      [],
      { chip: "Triple Captain", event: 2 },
    );

    expect(callOf(calls, "Triple Captain").event).toBe(2);
    expect(
      calls.filter((call) => call.event === 2).map((call) => call.chip),
    ).toEqual(["Triple Captain"]);
  });

  it("ignores a commitment to a chip he also says he has spent", () => {
    const calls = chipCallsFor(
      [week(3, { bench: [4, 3, 2, 5], captain: 7 })],
      PUBLISHED,
      ["Bench Boost:first"],
      { chip: "Bench Boost", event: 2 },
    );

    expect(calls.map((call) => call.chip)).not.toContain("Bench Boost");
  });

  it("spending a first-half chip leaves its second-half copy", () => {
    const calls = chipCallsFor(
      [week(20, { bench: [1, 1, 1, 1], captain: 7 })],
      [
        ...PUBLISHED,
        {
          event: 25,
          chip: "Wildcard",
          half: "second",
          gain: 8,
          note: "second copy",
        },
      ],
      ["Wildcard:first"],
    );

    expect(
      calls.find((call) => call.chip === "Wildcard" && call.half === "second"),
    ).toBeDefined();
  });

  it("pins a commitment onto the published calls when nothing is solved", () => {
    const calls = chipCallsFor([], PUBLISHED, [], {
      chip: "Wildcard",
      event: 6,
    });

    expect(callOf(calls, "Wildcard").event).toBe(6);
    expect(callOf(calls, "Wildcard").note).toContain("committed");
  });
});
