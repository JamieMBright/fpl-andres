import { describe, expect, it } from "vitest";

import { buildMarketHealth } from "./market-health";

const DEADLINE = "2026-08-21T17:30:00Z";

const fixtureOdds = {
  generatedAt: "2026-08-19T08:00:00Z",
  fixtures: [
    {
      kickoff: "2026-08-21T19:00:00Z",
      home: "ARS",
      away: "COV",
      homeExpectedGoals: 2.65,
      awayExpectedGoals: 0.49,
      homeCleanSheet: 0.61,
      awayCleanSheet: 0.07,
      marketEvidence: {
        observed: ["alternate_totals", "h2h", "h2h_lay", "totals"],
      },
    },
    {
      kickoff: "2026-08-22T11:30:00Z",
      home: "HUL",
      away: "MUN",
      homeExpectedGoals: 0.72,
      awayExpectedGoals: 2.27,
      homeCleanSheet: 0.1,
      awayCleanSheet: 0.49,
      marketEvidence: {
        observed: ["alternate_totals", "h2h", "h2h_lay", "totals"],
      },
    },
  ],
};

const playerOdds = {
  schemaVersion: 1,
  fetchedAt: "2026-08-19T09:00:00Z",
  markets: [
    "player_goal_scorer_anytime",
    "player_first_goal_scorer",
    "player_last_goal_scorer",
    "player_assists",
    "player_to_receive_card",
    "player_to_receive_red_card",
    "player_shots",
    "player_shots_on_target",
  ],
  clubQuoteFloor: 18,
  coverage: {
    fixturesListed: 2,
    fixturesVisitedThisRun: 2,
    fixturesWithQuotes: 1,
  },
  fixtures: [
    {
      event_id: "ars-cov",
      home_team: "Arsenal",
      away_team: "Coventry City",
      home_short: "ARS",
      away_short: "COV",
      kickoff: "2026-08-21T19:00:00Z",
      status: "returned",
      visited_at: "2026-08-19T09:00:00Z",
      books: 3,
      outcomes: 50,
      offered_markets: ["player_goal_scorer_anytime", "player_assists"],
      missing_markets: ["player_to_receive_red_card"],
      player_rows_parsed: 1,
      player_rows_matched: 1,
      unmatched_names: [],
      error: null,
    },
    {
      event_id: "hul-mun",
      home_team: "Hull City",
      away_team: "Manchester United",
      home_short: "HUL",
      away_short: "MUN",
      kickoff: "2026-08-22T11:30:00Z",
      status: "no-bookmaker",
      visited_at: "2026-08-19T09:00:00Z",
      books: 0,
      outcomes: 0,
      offered_markets: [],
      missing_markets: [],
      player_rows_parsed: 0,
      player_rows_matched: 0,
      unmatched_names: [],
      error: null,
    },
  ],
  players: [
    {
      element_id: 10,
      quoted_name: "Bukayo Saka",
      home_team: "Arsenal",
      away_team: "Coventry City",
      club: "ARS",
      kickoff: "2026-08-21T19:00:00Z",
      anytime_goal: 0.25,
      anytime_assist: 0.2,
      books: 3,
      observed_at: "2026-08-19T09:00:00Z",
    },
  ],
};

const seasonInputs = {
  players: [
    {
      id: 10,
      name: "Saka",
      position: "MID",
      priceTenths: 100,
      startRate: 0.91,
      depthRank: 1,
    },
  ],
};

const deadlines = {
  deadlines: [{ event: 1, deadline: DEADLINE, finished: false }],
};

describe("market health", () => {
  it("flags incomplete player coverage inside 72 hours", () => {
    const health = buildMarketHealth(
      { fixtureOdds, playerOdds, deadlines, seasonInputs },
      new Date("2026-08-19T06:30:00Z"),
    );

    expect(health.verdict).toBe("deadline-anomaly");
    expect(health.teamFixturesCovered).toBe(2);
    expect(health.playerFixturesCovered).toBe(1);
    expect(health.fixturesExpected).toBe(2);

    const arsenal = health.teams.find((team) => team.club === "ARS");
    const coventry = health.teams.find((team) => team.club === "COV");
    const hull = health.teams.find((team) => team.club === "HUL");
    expect(arsenal).toMatchObject({
      teamMarketsCovered: 4,
      playerMarketsCovered: 2,
      playersQuoted: 1,
      quoteFloor: 18,
      providerStatus: "returned",
    });
    expect(arsenal?.players[0]).toMatchObject({
      elementId: 10,
      quotedName: "Bukayo Saka",
      name: "Saka",
      position: "MID",
      startRate: 0.91,
      books: 3,
      observedAt: "2026-08-19T09:00:00Z",
      markets: {
        "Anytime scorer": 0.25,
        "Anytime assist": 0.2,
        "Red card": null,
      },
    });
    expect(coventry).toMatchObject({
      teamMarketsCovered: 4,
      playerMarketsCovered: 0,
      playersQuoted: 0,
    });
    expect(hull?.providerStatus).toBe("no-bookmaker");
  });

  it("lists every team and player market separately", () => {
    const health = buildMarketHealth(
      { fixtureOdds, playerOdds, deadlines, seasonInputs },
      new Date("2026-08-18T06:30:00Z"),
    );

    expect(health.verdict).toBe("partial");
    expect(health.markets).toHaveLength(12);
    expect(health.markets.find((market) => market.key === "h2h")).toMatchObject(
      { kind: "team", fixturesCovered: 2 },
    );
    expect(
      health.markets.find(
        (market) => market.key === "player_goal_scorer_anytime",
      ),
    ).toMatchObject({ kind: "player", fixturesCovered: 1 });
    expect(
      health.markets.find(
        (market) => market.key === "player_to_receive_red_card",
      ),
    ).toMatchObject({ kind: "player", fixturesCovered: 0 });
  });

  it("treats missing team-market diagnostics as no observed coverage", () => {
    const withoutEvidence = {
      ...fixtureOdds,
      fixtures: fixtureOdds.fixtures.map(
        ({ marketEvidence: _marketEvidence, ...fixture }) => fixture,
      ),
    };

    const health = buildMarketHealth(
      { fixtureOdds: withoutEvidence, playerOdds, deadlines, seasonInputs },
      new Date("2026-08-18T06:30:00Z"),
    );

    expect(health.teamFixturesCovered).toBe(0);
    expect(
      health.markets
        .filter((market) => market.kind === "team")
        .map((market) => market.fixturesCovered),
    ).toEqual([0, 0, 0, 0]);
  });
});
