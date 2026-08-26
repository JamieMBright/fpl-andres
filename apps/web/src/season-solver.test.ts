import { describe, expect, it } from "vitest";

import openingSquad from "./data/opening-squad.json";
import inputs from "./data/season-inputs.json";
import { fixtureEvidenceAt } from "./state/fixture-evidence";
import {
  bestElevenPoints,
  bonusPointsAtEvent,
  defconPointsAtEvent,
  fixtureAtEvent,
  lookaheadPointsFor,
  marketCarryWeight,
  marketValueAtEvent,
  solveSeason,
  SEASON_EVENTS,
  SEASON_PLAYERS,
  type SolverPlayer,
} from "./state/season-solver";

/**
 * The season solver runs in the browser against the manager's own state, so
 * there is no offline artifact to inspect afterwards. These check it produces a
 * legal season from a realistic start, and that the chaining actually chains.
 */

function openingStart() {
  const byCode = new Map(SEASON_PLAYERS.map((player) => [player.code, player]));
  const squad = openingSquad.picks
    .map((pick) => byCode.get(pick.code))
    .filter((player): player is NonNullable<typeof player> => Boolean(player))
    .map((player) => ({
      elementId: player.id,
      sellingPriceTenths: player.priceTenths,
    }));

  return {
    squad,
    bankTenths: 0,
    availableFreeTransfers: 1,
    fromEvent: SEASON_EVENTS[0] as number,
    assumed: [],
  };
}

/**
 * A full season solve is tens of seconds under vitest, not milliseconds,
 * against a 5s default.
 *
 * This is deliberately far above any measurement the suite makes. The speed
 * assertion below is a ratio and is load-independent by construction; the
 * timeout is wall-clock and is not, so it must never be the thing that decides
 * the test. Measured here: one 38-gameweek solve takes about 30s under vitest
 * on a loaded Windows laptop and about 7s on an idle desktop, and the file runs
 * roughly three solves' worth in total.
 */
const SOLVE_TIMEOUT = 120_000;

/** One full season solve, shared. Each is a few seconds; eight is a slow suite. */
let cached: ReturnType<typeof solveSeason> extends Generator<infer T>
  ? T[] | null
  : never = null;

function season() {
  cached ??= [...solveSeason(openingStart())];
  return cached;
}

describe("season inputs artifact", () => {
  it("aligns every fixture-evidence row to its published event index", () => {
    for (const club of Object.keys(inputs.fixtureLadder)) {
      for (const [index, event] of inputs.events.entries()) {
        const evidence = fixtureEvidenceAt(club, index);
        if (evidence !== null) expect(evidence.event, club).toBe(event);
      }
    }
  });

  it("decays a quoted market deviation with a two-gameweek half-life", () => {
    expect(marketCarryWeight(0, 0, 2)).toBe(1);
    expect(marketCarryWeight(1, 0, 2)).toBeCloseTo(Math.SQRT1_2);
    expect(marketCarryWeight(2, 0, 2)).toBe(0.5);
    expect(marketCarryWeight(8, 0, 2)).toBeCloseTo(0.0625);
    expect(marketCarryWeight(0, 1, 2)).toBe(0);
  });

  it("carries the quote fully now and fades it toward history later", () => {
    expect(marketValueAtEvent(10, 4, 0, 0, 2)).toBe(10);
    expect(marketValueAtEvent(10, 4, 2, 0, 2)).toBe(7);
    expect(marketValueAtEvent(10, 4, 8, 0, 2)).toBeCloseTo(4.375);
  });

  it("uses a fixture BPS override instead of adding it to historical bonus", () => {
    expect(bonusPointsAtEvent(0.6, 1, 1.4)).toBe(1.4);
  });

  it("keeps historical bonus when no BPS override was published", () => {
    expect(bonusPointsAtEvent(0.6, 2, undefined)).toBe(1.2);
  });

  it("raises DefCon under pressure without exceeding its two-point route", () => {
    const adjusted = defconPointsAtEvent(0.8, 1.8, 1);

    expect(adjusted).toBeGreaterThan(0.8);
    expect(adjusted).toBeLessThan(2);
  });

  it("carries a fixture ladder for every club a player belongs to", () => {
    const clubs = new Set(SEASON_PLAYERS.map((player) => player.club));
    for (const club of clubs) {
      expect(inputs.fixtureLadder).toHaveProperty(club);
    }
  });

  it("has one ladder rung per gameweek", () => {
    for (const [club, ladder] of Object.entries(inputs.fixtureLadder)) {
      expect(ladder.defensive, club).toHaveLength(inputs.events.length);
      expect(ladder.attacking, club).toHaveLength(inputs.events.length);
    }
  });

  it("ships a deadline for every gameweek", () => {
    expect(inputs.deadlines).toHaveLength(inputs.events.length);
    for (const deadline of inputs.deadlines) {
      expect(Number.isNaN(Date.parse(deadline))).toBe(false);
    }
  });

  it("contains every player in the published opening squad", () => {
    // The browser solve starts from that squad. A cheap bench enabler is picked
    // for what he costs, not what he scores, so a top-forty-by-points pool drops
    // him and the solve begins with fourteen men and a validation error.
    const codes = new Set(SEASON_PLAYERS.map((player) => player.code));
    const absent = openingSquad.picks.filter((pick) => !codes.has(pick.code));

    expect(absent.map((pick) => pick.name)).toEqual([]);
  });

  it("rates the archived opening squad over the current five-gameweek run", () => {
    const byCode = new Map(
      SEASON_PLAYERS.map((player) => [player.code, player]),
    );

    for (const pick of openingSquad.picks) {
      const player = byCode.get(pick.code);
      expect(player, pick.name).toBeDefined();
      const fixtures = Array.from({ length: 5 }, (_, index) =>
        fixtureAtEvent(player!, index),
      );
      const fixtureCount = fixtures.reduce(
        (total, fixture) => total + (fixture?.opponents.length ?? 0),
        0,
      );
      const points = fixtures.reduce(
        (total, fixture) => total + (fixture?.points ?? 0),
        0,
      );
      expect(fixtureCount, pick.name).toBeGreaterThan(0);
      expect(Number.isFinite(points), pick.name).toBe(true);
    }
  });
});

describe("solveSeason", () => {
  it(
    "starts the first remaining gameweek from the archived opening squad",
    () => {
      const opener = solveSeason(openingStart()).next().value;

      expect(opener).toBeDefined();
      expect(opener?.event).toBe(SEASON_EVENTS[0]);
      expect(opener?.transfersIn).toHaveLength(1);
      expect(opener?.transfersOut).toHaveLength(1);
      expect(opener?.transfersIn[0]?.position).toBe(
        opener?.transfersOut[0]?.position,
      );
      expect(opener?.transferCostPoints).toBe(0);
    },
    SOLVE_TIMEOUT,
  );

  it(
    "gives the armband to the current-gameweek leaders in the XI",
    () => {
      const opener = solveSeason(openingStart()).next().value;
      expect(opener).toBeDefined();
      const ranked = [...(opener?.starters ?? [])]
        .filter(
          (player) => player.position === "MID" || player.position === "FWD",
        )
        .sort(
          (left, right) =>
            (opener?.expected[String(right.code)] ?? 0) -
            (opener?.expected[String(left.code)] ?? 0),
        );

      expect(opener?.captain.id).toBe(ranked[0]?.id);
      expect(opener?.viceCaptain.id).toBe(ranked[1]?.id);
    },
    SOLVE_TIMEOUT,
  );

  it(
    "plans every gameweek from the one it was given",
    () => {
      const solved = season();

      expect(solved).toHaveLength(SEASON_EVENTS.length);
      expect(solved.map((week) => week.event)).toEqual(SEASON_EVENTS);
    },
    SOLVE_TIMEOUT,
  );

  it(
    "starts at the first unfinished event in the published artifact",
    () => {
      const opener = season()[0];

      expect(opener?.event).toBe(SEASON_EVENTS[0]);
    },
    SOLVE_TIMEOUT,
  );

  it("fields a legal squad in every gameweek", () => {
    for (const week of season()) {
      expect(week.starters).toHaveLength(11);
      expect(week.bench).toHaveLength(4);
      expect(
        new Set([...week.starters, ...week.bench].map((p) => p.id)).size,
      ).toBe(15);
      expect(week.starters.map((p) => p.id)).toContain(week.captain.id);
      expect(week.captain.id).not.toBe(week.viceCaptain.id);
      expect(["MID", "FWD"]).toContain(week.captain.position);
      expect(["MID", "FWD"]).toContain(week.viceCaptain.position);
      expect(week.starters.filter((p) => p.position === "GKP")).toHaveLength(1);
    }
  });

  it("never fields four players from one club", () => {
    for (const week of season()) {
      const counts = new Map<string, number>();
      for (const player of [...week.starters, ...week.bench]) {
        counts.set(player.club, (counts.get(player.club) ?? 0) + 1);
      }
      for (const [club, count] of counts) {
        expect(count, `${club} in gameweek ${week.event}`).toBeLessThanOrEqual(
          3,
        );
      }
    }
  });

  it("carries the squad forward instead of restarting it", () => {
    const solved = season();

    solved.forEach((week, index) => {
      const before = solved[index - 1];
      if (!before) return;

      const previous = new Set(
        [...before.starters, ...before.bench].map((p) => p.id),
      );
      for (const player of week.transfersOut)
        expect(previous).toContain(player.id);

      const expected = new Set(previous);
      for (const player of week.transfersOut) expected.delete(player.id);
      for (const player of week.transfersIn) expected.add(player.id);
      expect(
        new Set([...week.starters, ...week.bench].map((p) => p.id)),
      ).toEqual(expected);
    });
  });

  it("balances transfers and never spends money it does not have", () => {
    for (const week of season()) {
      expect(week.transfersIn).toHaveLength(week.transfersOut.length);
      expect(week.bankAfterTenths).toBeGreaterThanOrEqual(0);
      expect(week.freeTransfersBefore).toBeGreaterThanOrEqual(1);
      expect(week.freeTransfersBefore).toBeLessThanOrEqual(5);
    }
  });

  it(
    "starts from a mid-season gameweek when given one",
    () => {
      // Late enough that the solve is short. What is under test is that it
      // begins where the manager arrived and still runs to the end, which does
      // not need thirty weeks of solving to demonstrate.
      const start = { ...openingStart(), fromEvent: 33 };
      const solved = [...solveSeason(start)];

      // The whole reason this runs client-side: a manager arriving mid-season
      // has a squad nobody could have precomputed a plan for.
      expect(solved[0]?.event).toBe(33);
      expect(solved.at(-1)?.event).toBe(SEASON_EVENTS.at(-1));
      expect(solved[0]?.confidence).toBe("firm");
    },
    SOLVE_TIMEOUT,
  );

  it("degrades confidence with distance and never regains it", () => {
    const order = { firm: 0, projected: 1, provisional: 2 };
    const bands = season().map((week) => order[week.confidence]);

    bands.forEach((band, index) => {
      const previous = bands[index - 1];
      if (previous !== undefined) expect(band).toBeGreaterThanOrEqual(previous);
    });
  });

  it("refuses a gameweek that is not in the published season", () => {
    expect(() => [
      ...solveSeason({ ...openingStart(), fromEvent: 99 }),
    ]).toThrow(/not in the published season/);
  });

  it(
    "solves at a cost that stays roughly linear in the gameweeks asked for",
    () => {
      const eight = performance.now();
      const short = [...solveSeason({ ...openingStart(), fromEvent: 31 })];
      const shortMs = performance.now() - eight;

      const started = performance.now();
      const longer = [...solveSeason({ ...openingStart(), fromEvent: 20 })];
      const elapsed = performance.now() - started;

      expect(short).toHaveLength(8);
      expect(longer).toHaveLength(19);
      // A ratio, not a duration. The same assertion against the clock fails
      // whenever the suite's other workers are busy, which measures the machine
      // rather than the solver. Nineteen gameweeks against eight is 2.4x the
      // work, so anything under 6 is comfortably linear-ish; the full
      // thirty-eight used to be measured here and cost twenty seconds to prove
      // the same property.
      expect(elapsed / shortMs).toBeLessThan(6);
    },
    SOLVE_TIMEOUT,
  );
});

describe("chip squad valuation", () => {
  it("doubles the best midfielder or forward, not the highest-scoring defender", () => {
    const rows: [SolverPlayer["position"], number][] = [
      ["GKP", 20],
      ["GKP", 0],
      ["DEF", 19],
      ["DEF", 0],
      ["DEF", 0],
      ["DEF", 0],
      ["DEF", 0],
      ["MID", 8],
      ["MID", 7],
      ["MID", 0],
      ["MID", 0],
      ["MID", 0],
      ["FWD", 6],
      ["FWD", 0],
      ["FWD", 0],
    ];
    const positionId = { GKP: 1, DEF: 2, MID: 3, FWD: 4 } as const;
    const squad = rows.map(([position, points], index): SolverPlayer => ({
      id: 10_001 + index,
      code: 20_001 + index,
      name: `Player ${String(index + 1)}`,
      position,
      positionId: positionId[position],
      club: "ARS",
      teamId: 1,
      priceTenths: 50,
      basePoints: points,
      routes: { appearance: points },
      startRate: 1,
    }));

    expect(bestElevenPoints(squad, 0)).toBe(68);
  });
});

/**
 * A wildcard resets the long-term view. Five gameweeks is the right yardstick
 * for a squad you keep and the wrong one for a squad you have already decided
 * to throw away, so a player is valued only as far as the rebuild.
 */
describe("a committed rebuild", () => {
  const best = [...SEASON_PLAYERS].sort(
    (left, right) => right.basePoints - left.basePoints,
  )[0];

  it("stops paying for gameweeks the squad will not be around for", () => {
    expect(best).toBeDefined();
    expect(lookaheadPointsFor(best!, 0, 2)).toBeLessThan(
      lookaheadPointsFor(best!, 0),
    );
  });

  it("pays only the week itself on the last week before it", () => {
    const alone = fixtureAtEvent(best!, 1)?.points ?? 0;

    expect(lookaheadPointsFor(best!, 1, 2)).toBeCloseTo(alone, 6);
  });

  it("gives the whole run back from the rebuild onwards", () => {
    expect(lookaheadPointsFor(best!, 2, 2)).toBe(lookaheadPointsFor(best!, 2));
    expect(lookaheadPointsFor(best!, 5, 2)).toBe(lookaheadPointsFor(best!, 5));
  });

  it("leaves the run alone when nothing is committed", () => {
    expect(lookaheadPointsFor(best!, 0, undefined)).toBe(
      lookaheadPointsFor(best!, 0),
    );
  });
});

describe("a committed Free Hit", () => {
  it(
    "does not mark a week when the solve cannot move five players",
    () => {
      const solved = [
        ...solveSeason({
          ...openingStart(),
          fromEvent: 6,
          freeHitAtEvent: 6,
        }),
      ];
      const hitIndex = solved.findIndex((week) => week.chip === "Free Hit");
      expect(hitIndex).toBe(-1);
      expect(solved.every((week) => week.chip !== "Free Hit")).toBe(true);
    },
    SOLVE_TIMEOUT,
  );
});
