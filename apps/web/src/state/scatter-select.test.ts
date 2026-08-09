import { describe, expect, it } from "vitest";

import type { AnalysisPlayer } from "./analysis-pool";
import { selectPlotted } from "./scatter-select";
import { DEFAULT_VIEW } from "./scatter-view";

function player(overrides: Partial<AnalysisPlayer> = {}): AnalysisPlayer {
  const minutes = overrides.minutes ?? 1800;
  return {
    elementId: 1,
    code: 1,
    name: "Test",
    position: "MID",
    club: "ARS",
    teamId: 1,
    teamCode: 3,
    available: true,
    priceTenths: 55,
    ownership: 1,
    minutes,
    ninetiesPlayed: minutes / 90,
    totalPoints: 100,
    bonus: 5,
    expectedGoals: 5,
    expectedAssists: 4,
    expectedGoalInvolvements: 9,
    ictIndex: 100,
    influence: 400,
    creativity: 500,
    threat: 600,
    defensiveContribution: 240,
    defensiveContributionPer90: 12,
    defconBarRatio: 1,
    understat: null,
    ...overrides,
  };
}

const view = { ...DEFAULT_VIEW, x: "defconPer90", y: "xGIPer90" };

describe("selectPlotted", () => {
  it("drops players below the minutes threshold and counts them", () => {
    const selection = selectPlotted(
      [player({ code: 1, minutes: 200 }), player({ code: 2, minutes: 1800 })],
      view,
    )!;

    expect(selection.points).toHaveLength(1);
    expect(selection.excluded.minutes).toBe(1);
  });

  it("draws the whole market until a price bracket is asked for", () => {
    const selection = selectPlotted(
      [
        player({ code: 1, priceTenths: 40 }),
        player({ code: 2, priceTenths: 145 }),
      ],
      view,
    )!;

    expect(selection.points).toHaveLength(2);
    expect(selection.excluded.price).toBe(0);
  });

  it("keeps only the players inside the price bracket, and counts the rest", () => {
    // A replacement has to be affordable to be a replacement.
    const selection = selectPlotted(
      [
        player({ code: 1, priceTenths: 45 }),
        player({ code: 2, priceTenths: 55 }),
        player({ code: 3, priceTenths: 90 }),
      ],
      { ...view, priceFromTenths: 45, priceToTenths: 65 },
    )!;

    expect(selection.points.map((point) => point.player.code)).toEqual([1, 2]);
    expect(selection.excluded.price).toBe(1);
  });

  it("counts the bracket edges as inside it", () => {
    const selection = selectPlotted(
      [
        player({ code: 1, priceTenths: 45 }),
        player({ code: 2, priceTenths: 65 }),
      ],
      { ...view, priceFromTenths: 45, priceToTenths: 65 },
    )!;

    expect(selection.points).toHaveLength(2);
  });

  /*
   * The reason a DefCon metric returns null for a keeper rather than zero. A
   * keeper plotted on the DefCon axis would sit on the origin looking like the
   * worst defensive player in the game, when in fact the route does not exist
   * for him.
   */
  it("refuses to plot a goalkeeper on a DefCon axis, and names him", () => {
    const selection = selectPlotted(
      [
        player({ code: 1, position: "GKP", defconBarRatio: null }),
        player({ code: 2, position: "DEF", defconBarRatio: 1.2 }),
      ],
      view,
    )!;

    expect(selection.points.map((point) => point.player.code)).toEqual([2]);
    expect(selection.excluded.noValue).toBe(1);
    expect(selection.unmeasured).toContain("Test");
  });

  it("drops a player with no Understat match from an Understat axis", () => {
    const selection = selectPlotted([player()], { ...view, y: "npxGPer90" })!;

    expect(selection.points).toHaveLength(0);
    expect(selection.excluded.noValue).toBe(1);
  });

  /* A log axis has no room for zero, and nudging it would move the player. */
  it("drops non-positive values from a log axis rather than shifting them", () => {
    const selection = selectPlotted(
      [player({ code: 1, ownership: 0 }), player({ code: 2, ownership: 4 })],
      { ...view, x: "ownership", logX: true },
    )!;

    expect(selection.points.map((point) => point.player.code)).toEqual([2]);
  });

  describe("overlooked", () => {
    /*
     * Values chosen so both medians fall strictly between points. A pool where
     * the top value is also the median has an empty "high" half, because a
     * point on the line belongs to the low side.
     *
     * DefCon per 90 medians at 11, xGI per 90 at 0.55, over twenty nineties.
     */
    const pool = [
      player({
        code: 1,
        ownership: 1,
        defensiveContributionPer90: 20,
        expectedGoalInvolvements: 20,
      }),
      player({
        code: 2,
        ownership: 40,
        defensiveContributionPer90: 19,
        expectedGoalInvolvements: 20,
      }),
      player({
        code: 3,
        ownership: 1,
        defensiveContributionPer90: 4,
        expectedGoalInvolvements: 20,
      }),
      player({
        code: 4,
        ownership: 1,
        defensiveContributionPer90: 18,
        expectedGoalInvolvements: 2,
      }),
      player({
        code: 5,
        ownership: 1,
        defensiveContributionPer90: 2,
        expectedGoalInvolvements: 2,
      }),
      player({
        code: 6,
        ownership: 1,
        defensiveContributionPer90: 3,
        expectedGoalInvolvements: 2,
      }),
    ];

    it("rings the strong quadrant of whatever the band left in", () => {
      const selection = selectPlotted(pool, {
        ...view,
        ownedFrom: 0,
        ownedTo: 5,
      })!;
      const flagged = selection.points
        .filter((point) => point.overlooked)
        .map((point) => point.player.code);

      // The band drops anyone owned above five per cent, so what is left and
      // strong on both axes is what gets ringed.
      expect(flagged).toEqual([1]);
    });

    /*
     * Ownership is a metric where low is the good half, so "strong quadrant"
     * has to follow the metric rather than always meaning top right.
     */
    it("treats the low half as strong on an axis where low is better", () => {
      const selection = selectPlotted(
        [
          player({ code: 1, ownership: 1, expectedGoalInvolvements: 30 }),
          player({ code: 2, ownership: 40, expectedGoalInvolvements: 30 }),
          player({ code: 3, ownership: 2, expectedGoalInvolvements: 2 }),
          player({ code: 4, ownership: 45, expectedGoalInvolvements: 2 }),
        ],
        {
          ...view,
          x: "ownership",
          y: "xGIPer90",
          ownedFrom: 0,
          ownedTo: 100,
        },
      )!;

      expect(
        selection.points
          .filter((point) => point.overlooked)
          .map((p) => p.player.code),
      ).toEqual([1]);
    });
  });

  it("dims everyone not highlighted, without removing them", () => {
    const selection = selectPlotted(
      [
        player({ code: 1, name: "Wieffer" }),
        player({ code: 2, name: "Gomes" }),
      ],
      { ...view, highlights: ["#1"] },
    )!;

    expect(selection.points).toHaveLength(2);
    expect(selection.points.filter((point) => point.matched)).toHaveLength(1);
  });

  it("highlights a whole club at once", () => {
    const selection = selectPlotted(
      [
        player({ code: 1, club: "LEE" }),
        player({ code: 2, club: "ARS" }),
        player({ code: 3, club: "LEE" }),
      ],
      { ...view, highlights: ["LEE"] },
    )!;

    expect(selection.points.filter((point) => point.matched)).toHaveLength(2);
  });

  // The legend is the control: clicking a shape isolates that position, and
  // clicking a second one adds to it rather than replacing it.
  it("highlights a whole position, and adds a second without dropping the first", () => {
    const squad = [
      player({ code: 1, position: "MID" }),
      player({ code: 2, position: "DEF" }),
      player({ code: 3, position: "FWD" }),
    ];

    const mids = selectPlotted(squad, { ...view, highlights: ["@MID"] })!;
    expect(mids.points.filter((point) => point.matched)).toHaveLength(1);

    const both = selectPlotted(squad, {
      ...view,
      highlights: ["@MID", "@FWD"],
    })!;
    expect(both.points.filter((point) => point.matched)).toHaveLength(2);
    // Nothing is removed, only dimmed.
    expect(both.points).toHaveLength(3);
  });

  it("keeps a position highlight from colliding with a club of the same name", () => {
    const selection = selectPlotted(
      [player({ code: 1, club: "MID", position: "FWD" })],
      { ...view, highlights: ["@MID"] },
    )!;

    expect(selection.points[0]?.matched).toBe(false);
  });

  it("has no centre and no fit when everything is filtered away", () => {
    const selection = selectPlotted([player({ minutes: 10 })], view)!;

    expect(selection.points).toHaveLength(0);
    expect(selection.centres).toBeNull();
  });
});
