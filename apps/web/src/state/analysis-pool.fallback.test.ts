import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchAnalysisPool, forgetLastGoodAnalysis } from "./analysis-pool";

function bootstrap() {
  return {
    events: [
      {
        id: 1,
        finished: true,
        deadline_time: "2026-08-21T17:30:00Z",
      },
      {
        id: 2,
        finished: true,
        deadline_time: "2026-08-28T17:30:00Z",
      },
    ],
    element_types: [
      { id: 1, singular_name_short: "GKP" },
      { id: 2, singular_name_short: "DEF" },
      { id: 3, singular_name_short: "MID" },
      { id: 4, singular_name_short: "FWD" },
    ],
    teams: [{ id: 1, code: 3, short_name: "ARS", name: "Arsenal" }],
    elements: [
      {
        id: 1,
        code: 999_001,
        web_name: "Player",
        element_type: 2,
        team: 1,
        now_cost: 50,
        status: "a",
        minutes: 180,
        total_points: 100,
        bonus: 10,
        selected_by_percent: "1.2",
        expected_goals: "2.0",
        expected_assists: "1.0",
        expected_goal_involvements: "3.0",
        ict_index: "50.0",
        influence: "60.0",
        creativity: "70.0",
        threat: "80.0",
        defensive_contribution: 200,
        defensive_contribution_per_90: "10.0",
        clearances_blocks_interceptions: 100,
        tackles: 40,
        recoveries: 60,
      },
    ],
  };
}

beforeEach(() => forgetLastGoodAnalysis());

describe("Analysis cold FPL fallback", () => {
  it("plots a live player pool without a stale warning", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockImplementation((input) =>
        Promise.resolve(
          String(input).includes("fixtures")
            ? Response.json([{ event: 3, team_h: 1, team_a: 2 }])
            : Response.json(bootstrap()),
        ),
      );

    const live = await fetchAnalysisPool(fetchApi);

    expect(live.pool.players).toHaveLength(1);
    expect(live.pool.vintage.state).toBe("live_season");
    expect(live.freshness.stale).toBe(false);
    expect(fetchApi).not.toHaveBeenCalledWith(
      "/fpl-global.json",
      expect.anything(),
    );
  });

  it("plots the daily static snapshot when live FPL fails", async () => {
    const generatedAt = new Date(Date.now() - 3_600_000).toISOString();
    const fetchApi = vi.fn<typeof fetch>().mockImplementation((input) =>
      Promise.resolve(
        String(input) === "/fpl-global.json"
          ? Response.json({
              schemaVersion: 1,
              generatedAt,
              bootstrap: bootstrap(),
              fixtures: [{ event: 1, team_h: 1, team_a: 2 }],
            })
          : new Response("", { status: 503 }),
      ),
    );

    const fallback = await fetchAnalysisPool(fetchApi);

    expect(fallback.pool.players).toHaveLength(1);
    expect(fallback.fixtures).toHaveLength(1);
    expect(fallback.freshness.stale).toBe(true);
    expect(fallback.freshness.ageSeconds).toBeGreaterThanOrEqual(3_599);
    expect(fallback.pool.vintage.state).toBe("live_season");
    expect(fallback.pool.vintage.completedGameweeks).toBe(2);
  });

  it("refuses a malformed static snapshot", async () => {
    const fetchApi = vi.fn<typeof fetch>().mockImplementation((input) =>
      Promise.resolve(
        String(input) === "/fpl-global.json"
          ? Response.json({
              schemaVersion: 1,
              generatedAt: new Date().toISOString(),
              bootstrap: { elements: [] },
              fixtures: [],
            })
          : new Response("", { status: 503 }),
      ),
    );

    await expect(fetchAnalysisPool(fetchApi)).rejects.toMatchObject({
      reason: "source_contract_failed",
    });
  });
});
