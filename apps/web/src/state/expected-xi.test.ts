import { describe, expect, it } from "vitest";

import { buildExpectedXi } from "./expected-xi";

const seasonInputs = {
  generatedAt: "2026-08-19T20:00:00Z",
  events: [2, 3, 4],
  marketCarry: { players: { "4": [0, 0.5, 1.2, 0.4, 0, 0] } },
  evidence: { playerMarkets: { updatedAt: "2026-08-19T21:00:00Z" } },
  players: [
    {
      id: 1,
      availabilityStatus: "d",
      chanceOfPlaying: 25,
      code: 101,
      name: "Keeper",
      position: "GKP",
      club: "ARS",
      teamId: 1,
      startRate: 0.7,
      startEvidence: {
        sourceStartRate: 0.8,
        finalStartRate: 0.9,
        observedAppearances: 32,
        recentStarts: 5,
        recentMatches: 6,
        appearanceSource: "marketParticipation",
        lineupAdjustment: 0.1,
        marketAdjustment: 0,
      },
    },
    {
      id: 2,
      code: 102,
      name: "Reserve keeper",
      position: "GKP",
      club: "ARS",
      teamId: 1,
      startRate: 0.2,
    },
    {
      id: 3,
      code: 103,
      name: "Quoted",
      position: "DEF",
      club: "ARS",
      teamId: 1,
      startRate: 0.9,
    },
    {
      id: 4,
      code: 104,
      name: "Carried",
      position: "MID",
      club: "ARS",
      teamId: 1,
      startRate: 0.8,
    },
    {
      id: 5,
      code: 105,
      name: "Prior",
      position: "FWD",
      club: "ARS",
      teamId: 1,
      startRate: 0.6,
      rated: false,
    },
    ...Array.from({ length: 13 }, (_, index) => ({
      id: 10 + index,
      code: 110 + index,
      name: `Outfield ${index}`,
      position: "MID" as const,
      club: "ARS",
      teamId: 1,
      startRate: 0.59 - index * 0.01,
    })),
    {
      id: 29,
      availabilityStatus: "i",
      chanceOfPlaying: 0,
      code: 129,
      name: "Hidden injury",
      position: "FWD",
      club: "ARS",
      teamId: 1,
      startRate: 0,
    },
    {
      id: 30,
      code: 130,
      name: "Bee",
      position: "GKP",
      club: "BRE",
      teamId: 2,
      startRate: 0.9,
    },
    {
      id: 326,
      code: 201595,
      name: "Perri",
      position: "GKP",
      club: "LEE",
      teamId: 13,
      startRate: 0.365,
    },
    {
      id: 385,
      code: 432720,
      name: "Trafford",
      position: "GKP",
      club: "LEE",
      teamId: 13,
      startRate: 0.106,
    },
  ],
} as const;

const playerOdds = {
  fetchedAt: "2026-08-19T21:05:00Z",
  clubQuoteFloor: 18,
  fixtures: [
    {
      home_short: "ARS",
      away_short: "BRE",
      visited_at: "2026-08-19T21:10:00Z",
      status: "returned",
      unmatched_names: ["Mystery Player"],
    },
  ],
  players: [{ element_id: 3, club: "ARS", kickoff: "2026-08-21T19:00:00Z" }],
} as const;

const manualPriors = {
  generatedAt: "2026-08-19T21:45:00Z",
  source: "manual-team-news",
  event: 2,
  players: [
    {
      elementId: 385,
      code: 432720,
      club: "LEE",
      name: "Trafford",
      startProbability: 1,
      confidence: "high",
      reason: "Known starting goalkeeper for GW1",
    },
  ],
} as const;

describe("expected XI reader", () => {
  it("carries official availability into the player explanation", () => {
    const arsenal = buildExpectedXi({ seasonInputs, playerOdds }).teams.find(
      (team) => team.club === "ARS",
    );
    const keeper = [
      ...(arsenal?.starters ?? []),
      ...(arsenal?.reserves ?? []),
    ].find((player) => player.id === 1);

    expect(keeper).toMatchObject({
      availabilityStatus: "d",
      chanceOfPlaying: 25,
    });
    expect(keeper?.explanation.factors).toContainEqual({
      label: "FPL availability",
      value: "Doubtful",
      detail: "FPL publishes a 25% chance of playing.",
    });
  });

  it("caps a doubtful starter's xStart at FPL's own published chance of playing", () => {
    const arsenal = buildExpectedXi({ seasonInputs, playerOdds }).teams.find(
      (team) => team.club === "ARS",
    );
    const keeper = arsenal?.starters.find((player) => player.id === 1);

    // Model rate is 0.7; FPL says a doubtful 25% chance, and the lower one wins.
    expect(keeper?.startProbability).toBeCloseTo(0.25, 5);
  });

  it("cannot show a high xStart for a player FPL has flagged as unavailable", () => {
    const arsenal = buildExpectedXi({ seasonInputs, playerOdds }).teams.find(
      (team) => team.club === "ARS",
    );
    const hidden = arsenal?.availabilityFlags.find(
      (player) => player.name === "Hidden injury",
    );

    expect(hidden?.startProbability).toBeLessThanOrEqual(0.03);
  });

  it("keeps flags visible below the seven reserves", () => {
    const arsenal = buildExpectedXi({ seasonInputs, playerOdds }).teams.find(
      (team) => team.club === "ARS",
    );

    expect(arsenal?.availabilityFlags).toEqual([
      expect.objectContaining({
        name: "Hidden injury",
        availabilityStatus: "i",
        chanceOfPlaying: 0,
      }),
    ]);
  });

  it("selects one keeper and the ten likeliest outfield starters", () => {
    const arsenal = buildExpectedXi({ seasonInputs, playerOdds }).teams.find(
      (team) => team.club === "ARS",
    );

    expect(arsenal?.starters).toHaveLength(11);
    expect(arsenal?.starters[0]?.name).toBe("Keeper");
    expect(
      arsenal?.starters.some((player) => player.name === "Reserve keeper"),
    ).toBe(false);
    expect(
      arsenal?.reserves.some((player) => player.name === "Reserve keeper"),
    ).toBe(true);
  });

  it("keeps market, model and prior evidence separate per player", () => {
    const arsenal = buildExpectedXi({ seasonInputs, playerOdds }).teams.find(
      (team) => team.club === "ARS",
    );

    expect(
      arsenal?.starters.find((player) => player.name === "Quoted")?.evidence,
    ).toBe("market");
    expect(
      arsenal?.starters.find((player) => player.name === "Carried")?.evidence,
    ).toBe("market");
    expect(
      arsenal?.starters.find((player) => player.name === "Prior")?.evidence,
    ).toBe("prior");
    expect(
      arsenal?.starters.find((player) => player.name === "Keeper")?.evidence,
    ).toBe("model");
  });

  it("explains the published source-to-final start-rate trail", () => {
    const arsenal = buildExpectedXi({ seasonInputs, playerOdds }).teams.find(
      (team) => team.club === "ARS",
    );
    const keeper = arsenal?.starters.find((player) => player.name === "Keeper");
    expect(keeper?.explanation.factors[0]).toMatchObject({
      label: "Math",
      value: "90%",
    });
    expect(keeper?.explanation.factors[0]?.detail).toContain(
      "80% source rate -> 90% published rate",
    );
    expect(keeper?.explanation.factors[0]?.detail).toContain(
      "32 recorded appearances",
    );
    expect(
      keeper?.explanation.factors.find(
        (factor) => factor.label === "Last lineups",
      ),
    ).toMatchObject({
      value: "+10pp",
    });
  });

  it("uses singular wording for one recorded appearance", () => {
    const withOneAppearance = {
      ...seasonInputs,
      players: seasonInputs.players.map((player) =>
        player.id === 1
          ? {
              ...player,
              startEvidence: {
                ...("startEvidence" in player ? player.startEvidence : {}),
                observedAppearances: 1,
              },
            }
          : player,
      ),
    };
    const arsenal = buildExpectedXi({
      seasonInputs: withOneAppearance,
      playerOdds,
    }).teams.find((team) => team.club === "ARS");
    const keeper = arsenal?.starters.find((player) => player.name === "Keeper");

    expect(keeper?.explanation.factors[0]?.detail).toContain(
      "1 recorded appearance",
    );
    expect(keeper?.explanation.factors[0]?.detail).not.toContain(
      "1 recorded appearances",
    );
  });

  it("attaches team market health to the squad", () => {
    const arsenal = buildExpectedXi({ seasonInputs, playerOdds }).teams.find(
      (team) => team.club === "ARS",
    );

    expect(arsenal).toMatchObject({
      marketStatus: "returned",
      playersQuoted: 1,
      quoteFloor: 18,
      unmatchedNames: ["Mystery Player"],
      updatedAt: "2026-08-19T21:10:00Z",
    });
    // The starting keeper is doubtful at a published 25% chance of playing,
    // which caps his contribution to the average well below his raw rate.
    expect(arsenal?.averageStartProbability).toBeGreaterThan(0.55);
    expect(arsenal?.averageStartProbability).toBeLessThan(0.6);
  });

  it("lets a manual xStart prior correct a known starting goalkeeper", () => {
    const leeds = buildExpectedXi({
      seasonInputs,
      playerOdds,
      manualPriors,
    }).teams.find((team) => team.club === "LEE");

    expect(leeds?.starters[0]).toMatchObject({
      name: "Trafford",
      startProbability: 1,
      evidence: "manual",
    });
    expect(
      leeds?.reserves.find((player) => player.name === "Perri"),
    ).toMatchObject({
      startProbability: 0.01,
    });
    expect(leeds?.starters[0]?.explanation.factors.at(-1)).toMatchObject({
      label: "Manual",
      detail: "Known starting goalkeeper for GW1",
    });
  });

  it("ignores a manual prior written for a gameweek that has already passed", () => {
    const staleManualPriors = { ...manualPriors, event: 1 };

    const leeds = buildExpectedXi({
      seasonInputs,
      playerOdds,
      manualPriors: staleManualPriors,
    }).teams.find((team) => team.club === "LEE");

    // seasonInputs' current gameweek is 2; a prior written for gameweek 1 must
    // not silently keep overriding the model once that gameweek is over.
    expect(leeds?.starters[0]?.name).not.toBe("Trafford");
    expect(
      leeds?.starters.every((player) => player.evidence !== "manual"),
    ).toBe(true);
  });
});
