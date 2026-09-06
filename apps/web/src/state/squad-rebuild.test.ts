import { describe, expect, it } from "vitest";

import {
  LINEUP_SHAPE,
  SEASON_EVENTS,
  SEASON_PLAYERS,
  SQUAD_SHAPE_BY_CODE,
} from "./season-solver";
import { rebuildSquad, rebuildUplift } from "./squad-rebuild";

/**
 * A wildcard is only advice if the fifteen it names could actually be bought.
 * These run against the published pool, so a rule broken here is a rule broken
 * on the page.
 */

const BUDGET = 1000;

describe("rebuildSquad", () => {
  it("buys a legal fifteen inside the budget", () => {
    const rebuilt = rebuildSquad(0, BUDGET);

    expect(rebuilt).not.toBeNull();
    const squad = rebuilt?.squad ?? [];
    expect(squad).toHaveLength(15);

    const spent = squad.reduce(
      (total, player) => total + player.priceTenths,
      0,
    );
    expect(spent).toBeLessThanOrEqual(BUDGET);
    expect(rebuilt?.bankTenths).toBe(BUDGET - spent);

    for (const [code, quota] of Object.entries(SQUAD_SHAPE_BY_CODE)) {
      const held = squad.filter((player) => player.position === code);
      expect(held).toHaveLength(quota);
    }

    const perClub = new Map<string, number>();
    for (const player of squad) {
      perClub.set(player.club, (perClub.get(player.club) ?? 0) + 1);
    }
    expect(Math.max(...perClub.values())).toBeLessThanOrEqual(3);

    // Nobody is bought twice.
    expect(new Set(squad.map((player) => player.id)).size).toBe(15);
  });

  it("refuses a budget no legal fifteen fits inside", () => {
    expect(rebuildSquad(0, 100)).toBeNull();
  });

  it("does not buy a recent club arrival during his hold gameweek", () => {
    const event = SEASON_EVENTS[0] as number;
    const blocked = new Set(
      SEASON_PLAYERS.filter(
        (player) =>
          player.recentClubChange !== undefined &&
          event <= player.recentClubChange.avoidUntilEvent,
      ).map((player) => player.id),
    );
    const rebuilt = rebuildSquad(0, BUDGET);

    if (blocked.size === 0) return;
    expect(rebuilt?.squad.some((player) => blocked.has(player.id))).toBe(false);
  });

  it("can field a legal eleven from what it bought", () => {
    const squad = rebuildSquad(0, BUDGET)?.squad ?? [];

    for (const [code, shape] of Object.entries(LINEUP_SHAPE)) {
      const held = squad.filter((player) => player.position === code).length;
      expect(held).toBeGreaterThanOrEqual(shape.min);
    }
  });
});

describe("rebuildUplift", () => {
  it("reports nothing to gain against a squad that is already the best", () => {
    const squad = rebuildSquad(0, BUDGET, 1)?.squad ?? [];
    const { gain } = rebuildUplift(SEASON_EVENTS[0] as number, squad, BUDGET);

    // The rebuild is deterministic, so rebuilding the same squad on the same
    // budget must not invent a gain out of nothing.
    expect(gain).toBeCloseTo(0, 6);
  });

  it("finds a gain against a squad bought on a smaller budget", () => {
    // The universal price floor is £60.0m, but the cheapest legal fifteen also
    // depends on who clears the current start-rate filter and the club limit.
    // Find that boundary from the published pool instead of guessing it.
    let poor: ReturnType<typeof rebuildSquad> = null;
    for (let budget = 600; budget < BUDGET && poor === null; budget += 10) {
      poor = rebuildSquad(0, budget, 1);
    }

    expect(poor).not.toBeNull();
    const squad = poor?.squad ?? [];
    expect(squad).toHaveLength(15);

    const { gain } = rebuildUplift(SEASON_EVENTS[0] as number, squad, BUDGET);

    expect(gain).toBeGreaterThan(0);
  });

  it("says nothing for a gameweek that is not in the season", () => {
    expect(rebuildUplift(99, [], BUDGET)).toEqual({
      gain: 0,
      changes: 0,
      rebuilt: null,
    });
  });
});
