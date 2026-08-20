import { describe, expect, it } from "vitest";

import type { MarketHealth } from "../state/market-health";
import { statusCopy } from "./MarketsPage";

const baseHealth: MarketHealth = {
  verdict: "deadline-anomaly",
  deadline: "2026-08-21T17:30:00Z",
  hoursUntilDeadline: 36,
  fixtureMarketsAsOf: "2026-08-19T08:00:00Z",
  playerMarketsAsOf: "2026-08-19T09:00:00Z",
  playerArtifactAgeHours: 1,
  fixturesExpected: 10,
  teamFixturesCovered: 10,
  playerFixturesCovered: 10,
  markets: [
    {
      key: "player_goal_scorer_anytime",
      label: "Anytime scorer",
      kind: "player",
      fixturesCovered: 10,
      fixturesExpected: 10,
      status: "complete",
    },
    {
      key: "player_shots",
      label: "Total shots",
      kind: "player",
      fixturesCovered: 0,
      fixturesExpected: 10,
      status: "missing",
    },
    {
      key: "h2h",
      label: "Match result",
      kind: "team",
      fixturesCovered: 10,
      fixturesExpected: 10,
      status: "complete",
    },
  ],
  teams: [],
};

describe("MarketsPage status copy", () => {
  it("explains late markets when fixtures are covered but market classes are not", () => {
    const status = statusCopy(baseHealth);

    expect(status.detail).toContain("10/10 fixtures have player prices");
    expect(status.detail).toContain("1/2 player markets are complete");
    expect(status.detail).toContain("Total shots");
    expect(status.detail).not.toContain("I expected the round by now");
  });

  it("keeps fixture-gap wording when fixtures themselves are missing", () => {
    const status = statusCopy({ ...baseHealth, playerFixturesCovered: 8 });

    expect(status.detail).toContain("8/10 fixtures have usable player prices");
    expect(status.detail).toContain("I expected the round by now");
  });
});
