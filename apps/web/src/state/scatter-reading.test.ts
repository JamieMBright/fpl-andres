import { describe, expect, it } from "vitest";

import type { AnalysisPlayer } from "./analysis-pool";
import { readChart } from "./scatter-reading";
import { selectPlotted } from "./scatter-select";
import { DEFAULT_VIEW } from "./scatter-view";

/**
 * A chart nobody has been told how to read is decoration.
 */

function player(index: number, defcon: number, xgi: number): AnalysisPlayer {
  return {
    elementId: index,
    code: index,
    name: `Player ${index.toString()}`,
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
    expectedGoals: xgi / 2,
    expectedAssists: xgi / 2,
    expectedGoalInvolvements: xgi,
    ictIndex: 100,
    influence: 100,
    creativity: 100,
    threat: 100,
    defensiveContribution: defcon * 30,
    defensiveContributionPer90: defcon,
    defconBarRatio: defcon / 12,
    understat: null,
  };
}

/** Defensive work rising as involvement falls, which is the real pattern. */
const OPPOSED = Array.from({ length: 12 }, (_, index) =>
  player(index + 1, 2 + index, 30 - index * 2),
);

describe("readChart", () => {
  const plot = (players: AnalysisPlayer[], view = DEFAULT_VIEW) => {
    const selection = selectPlotted(players, view);
    if (!selection) throw new Error("nothing plotted");
    return selection;
  };

  it("says which corner is the good one, in the words of the axes", () => {
    const reading = readChart(plot(OPPOSED), DEFAULT_VIEW);

    expect(reading.corner).toContain("top right");
    expect(reading.corner).toContain("DefCon per 90");
    expect(reading.corner).toContain("xGI per 90");
  });

  it("puts the good corner where a low number is the good one", () => {
    const view = { ...DEFAULT_VIEW, x: "price", y: "ownership" };

    const reading = readChart(plot(OPPOSED, view), view);

    // Cheap and unowned: bottom left, because neither rewards a big number.
    expect(reading.corner).toContain("bottom left");
  });

  it("describes the relationship without being asked for a trend line", () => {
    // The default view has the trend toggle off. The sentence is still there.
    expect(DEFAULT_VIEW.trend).toBe(false);

    const reading = readChart(plot(OPPOSED), DEFAULT_VIEW);

    expect(reading.relationship).toContain("negative");
    expect(reading.relationship).toContain("r = -");
  });

  it("names the player furthest into the good corner", () => {
    const reading = readChart(plot(OPPOSED), DEFAULT_VIEW);

    expect(reading.standout).toMatch(/^Player \d+ \(ARS\) sits furthest/);
  });

  it("says what the disc size means", () => {
    const reading = readChart(plot(OPPOSED), DEFAULT_VIEW);

    expect(reading.size).toContain("ownership");
    expect(reading.size).toContain("area");
  });

  it("says nothing about a relationship it cannot measure", () => {
    const alone = [player(1, 5, 10)];

    const reading = readChart(plot(alone), DEFAULT_VIEW);

    expect(reading.relationship).toBeNull();
    expect(reading.standout).toBeNull();
  });
});
