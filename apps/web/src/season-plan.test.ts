import { describe, expect, it } from "vitest";

import plan from "./data/season-plan.json";
import { readSeasonPlan } from "./state/season-plan";

/**
 * The season plan is generated offline and committed, so nothing at runtime
 * would notice it going wrong. These check the artifact is internally coherent
 * and that the view layer cannot quietly invent a player.
 */

type GeneratedWeek = (typeof plan.gameweeks)[number];
const weeks = plan.gameweeks as readonly (GeneratedWeek & {
  chip?: string;
  revertsAfter?: boolean;
  revertsTo?: number[];
})[];
const players = plan.players as Record<string, { position: string }>;

describe("season plan artifact", () => {
  it("covers a contiguous run of gameweeks", () => {
    const events = weeks.map((week) => week.event);
    const first = events.at(0);

    expect(events.length).toBeGreaterThan(1);
    expect(first).toBeDefined();
    expect(events).toEqual(events.map((_, index) => (first ?? 0) + index));
  });

  it("fields a legal squad in every gameweek", () => {
    for (const week of weeks) {
      const squad = [...week.starters, ...week.bench];
      expect(squad).toHaveLength(15);
      expect(new Set(squad).size).toBe(15);
      expect(week.starters).toHaveLength(11);
      expect(week.starters).toContain(week.captain);
      expect(week.starters).toContain(week.viceCaptain);
      expect(week.captain).not.toBe(week.viceCaptain);
      expect(["MID", "FWD"], `GW${String(week.event)} captain`).toContain(
        players[String(week.captain)]?.position,
      );
      expect(["MID", "FWD"], `GW${String(week.event)} vice-captain`).toContain(
        players[String(week.viceCaptain)]?.position,
      );
    }
  });

  it("balances every transfer and accounts for its cost", () => {
    for (const week of weeks) {
      expect(week.transfersIn).toHaveLength(week.transfersOut.length);
      expect(week.netExpectedPoints).toBeCloseTo(
        week.projectedPoints - week.transferCostPoints,
        6,
      );
    }
  });

  it("carries the squad across gameweeks rather than restarting it", () => {
    // A Free Hit is the one break in the chain: it fields fifteen for the
    // afternoon and hands them back, so the plan resumes from the squad it
    // publishes as `revertsTo` rather than the eleven and four it fielded.
    let held: Set<number> | null = null;
    for (const week of weeks) {
      const fielded = new Set([...week.starters, ...week.bench]);
      if (held && !week.revertsAfter) {
        for (const code of week.transfersOut) expect(held).toContain(code);
        const expected = new Set(held);
        for (const code of week.transfersOut) expected.delete(code);
        for (const code of week.transfersIn) expected.add(code);
        expect(fielded).toEqual(expected);
      }
      if (week.revertsAfter) {
        expect(week.revertsTo).toHaveLength(15);
        held = new Set(week.revertsTo);
      } else {
        held = fielded;
      }
    }
  });

  it("never charges more than two hits in a gameweek", () => {
    // Two is the point at which a week is buying a rebuild one transfer at a
    // time, which is what the Wildcard is for. Beyond it the plan is spending
    // a chip's worth of points and keeping the chip.
    for (const week of weeks) {
      expect(week.transferCostPoints).toBeLessThanOrEqual(8);
    }
  });

  it("never plays a wildcard that moves fewer than five of the fifteen", () => {
    // A rebuild the free transfer could have made over a few weeks costs
    // nothing to make over a few weeks, and leaves the chip in hand.
    for (const week of weeks) {
      if (week.chip !== "Wildcard") continue;
      expect(week.transfersIn.length).toBeGreaterThanOrEqual(5);
    }
  });

  it("names every player it references", () => {
    const known = new Set(Object.keys(plan.players).map(Number));
    for (const week of weeks) {
      for (const code of [
        ...week.starters,
        ...week.bench,
        ...week.transfersIn,
        ...week.transfersOut,
      ]) {
        expect(known).toContain(code);
      }
    }
  });

  it("records where its transfer rules came from", () => {
    // Neither number is published in the FPL bootstrap. An artifact that cannot
    // say where they came from was built on a guess.
    expect(plan.rulesReference.trim().length).toBeGreaterThan(0);
    expect(plan.weeklyFreeTransfers).toBeGreaterThan(0);
    expect(plan.transferCostPoints).toBeGreaterThan(0);
  });

  it("labels confidence on every gameweek and never regains it", () => {
    const rank = { firm: 0, projected: 1, provisional: 2 };
    const bands = weeks.map(
      (week) => rank[week.confidence as keyof typeof rank],
    );

    expect(new Set(bands).size).toBeGreaterThan(1);
    expect(bands.at(0)).toBe(rank.firm);
    expect(bands.at(-1)).toBe(rank.provisional);
    bands.forEach((band, index) => {
      const previous = bands[index - 1];
      if (previous !== undefined) expect(band).toBeGreaterThanOrEqual(previous);
    });
  });
});

describe("readSeasonPlan", () => {
  it("resolves player codes into named players", () => {
    const first = readSeasonPlan().gameweeks.at(0);

    expect(first).toBeDefined();
    expect(first?.captain.name.length).toBeGreaterThan(0);
    expect(first?.captain.club.length).toBeGreaterThan(0);
    expect(first?.starters).toHaveLength(11);
  });

  it("puts the eleven in team-sheet order", () => {
    const order = ["GKP", "DEF", "MID", "FWD"];
    for (const week of readSeasonPlan().gameweeks) {
      const positions = week.starters.map((player) =>
        order.indexOf(player.position),
      );
      expect(positions).toEqual([...positions].sort((a, b) => a - b));
    }
  });

  it("leaves the bench in the published order", () => {
    const read = readSeasonPlan().gameweeks.at(0);
    expect(read?.bench.map((player) => player.code)).toEqual(
      weeks.at(0)?.bench,
    );
  });
});
