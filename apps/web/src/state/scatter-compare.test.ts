import { describe, expect, it } from "vitest";

import type { AnalysisPlayer } from "./analysis-pool";
import { comparePinned } from "./scatter-compare";
import { DEFAULT_VIEW } from "./scatter-view";

/**
 * A shortlist, put side by side with the difference that decides it first.
 */

function player(overrides: Partial<AnalysisPlayer>): AnalysisPlayer {
  return {
    elementId: 1,
    code: 1,
    name: "Player",
    position: "MID",
    club: "ARS",
    teamId: 1,
    teamCode: 3,
    available: true,
    priceTenths: 60,
    ownership: 5,
    minutes: 2700,
    ninetiesPlayed: 30,
    totalPoints: 120,
    bonus: 8,
    expectedGoals: 6,
    expectedAssists: 6,
    expectedGoalInvolvements: 12,
    ictIndex: 100,
    influence: 100,
    creativity: 100,
    threat: 100,
    defensiveContribution: 150,
    defensiveContributionPer90: 5,
    defconBarRatio: 0.5,
    clearancesBlocksInterceptions: 40,
    tackles: 30,
    recoveries: 50,
    understat: null,
    ...overrides,
  };
}

const POOL = [
  player({
    code: 1,
    defensiveContributionPer90: 2,
    expectedGoalInvolvements: 3,
  }),
  player({
    code: 2,
    defensiveContributionPer90: 6,
    expectedGoalInvolvements: 9,
  }),
  player({
    code: 3,
    defensiveContributionPer90: 10,
    expectedGoalInvolvements: 15,
  }),
  player({
    code: 4,
    defensiveContributionPer90: 14,
    expectedGoalInvolvements: 21,
  }),
];

describe("comparePinned", () => {
  it("puts the player furthest into the good corner first", () => {
    // Both axes reward a bigger number, and code 4 leads on both.
    const result = comparePinned([POOL[0]!, POOL[3]!], POOL, DEFAULT_VIEW);

    expect(result.players[0]?.code).toBe(4);
    expect(result.players[1]?.code).toBe(1);
  });

  it("orders the rows by how far apart the chosen players are", () => {
    const result = comparePinned([POOL[0]!, POOL[3]!], POOL, DEFAULT_VIEW);
    const impacts = result.rows.map((row) => row.impact);

    expect(impacts).toEqual([...impacts].sort((a, b) => b - a));
  });

  it("drops a measure nobody in the shortlist differs on", () => {
    // Identical price, so it separates nothing and cannot lead the list.
    const result = comparePinned([POOL[0]!, POOL[3]!], POOL, DEFAULT_VIEW);
    const price = result.rows.find((row) => row.id === "price");

    expect(price?.impact).toBe(0);
    expect(result.rows.at(-1)?.impact).toBe(0);
  });

  it("names one leader per row and nobody when they tie", () => {
    const result = comparePinned([POOL[0]!, POOL[3]!], POOL, DEFAULT_VIEW);

    const defcon = result.rows.find((row) => row.id === "defconPer90");
    expect(defcon?.leader).toBe(0);

    const price = result.rows.find((row) => row.id === "price");
    expect(price?.leader).toBe(-1);
  });

  it("marks the lowest as the leader where low is the good number", () => {
    const cheap = player({ code: 9, priceTenths: 40 });
    const result = comparePinned([POOL[3]!, cheap], [...POOL, cheap], {
      ...DEFAULT_VIEW,
      x: "price",
      y: "ownership",
    });

    const price = result.rows.find((row) => row.id === "price");
    const cheapColumn = result.players.findIndex(
      (entry) => entry.code === cheap.code,
    );

    expect(price?.higherIsBetter).toBe(false);
    expect(price?.leader).toBe(cheapColumn);
  });

  it("compares nobody without complaint", () => {
    const result = comparePinned([], POOL, DEFAULT_VIEW);

    expect(result.players).toEqual([]);
    expect(result.rows).toEqual([]);
  });
});
