import { describe, expect, it, vi } from "vitest";

import { buildPlayerPool, fetchPlayerPool } from "./player-pool";

// Bruno Fernandes, present in the published record.
const KNOWN_CODE = 141746;

function bootstrap(
  overrides: Partial<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    events: [
      { id: 2, deadline_time: "2026-08-28T17:30:00Z" },
      { id: 1, deadline_time: "2026-08-21T17:30:00Z" },
    ],
    element_types: [
      { id: 1, singular_name_short: "GKP" },
      { id: 2, singular_name_short: "DEF" },
      { id: 3, singular_name_short: "MID" },
      { id: 4, singular_name_short: "FWD" },
      { id: 5, singular_name_short: "AM" },
    ],
    teams: [
      { id: 1, code: 3, short_name: "ARS", name: "Arsenal" },
      { id: 2, code: 1, short_name: "MUN", name: "Man Utd" },
    ],
    elements: [
      {
        id: 1,
        code: KNOWN_CODE,
        web_name: "B.Fernandes",
        element_type: 3,
        team: 2,
        now_cost: 100,
        status: "a",
      },
      {
        id: 2,
        code: 999_999_999,
        web_name: "Debutant",
        element_type: 4,
        team: 1,
        now_cost: 55,
        status: "a",
      },
      {
        id: 3,
        code: 888_888_888,
        web_name: "The Gaffer",
        element_type: 5,
        team: 1,
        now_cost: 15,
        status: "a",
      },
    ],
    ...overrides,
  };
}

describe("buildPlayerPool", () => {
  it("joins this season's price to last season's record", () => {
    const pool = buildPlayerPool(bootstrap());
    const bruno = pool.players.find((player) => player.code === KNOWN_CODE);

    expect(bruno?.priceTenths).toBe(100);
    expect(bruno?.record?.expectedPoints).toBe(5.05);
    // 5.05 points per match at £10.0m.
    expect(bruno?.perMillion).toBeCloseTo(0.51, 2);
  });

  it("keeps a player with no record rather than dropping him", () => {
    const pool = buildPlayerPool(bootstrap());
    const debutant = pool.players.find((player) => player.name === "Debutant");

    expect(debutant).toBeDefined();
    expect(debutant?.record).toBeNull();
    expect(debutant?.perMillion).toBeNull();
  });

  it("leaves managers out: a chip is not a footballer", () => {
    expect(
      buildPlayerPool(bootstrap()).players.some(
        (player) => player.name === "The Gaffer",
      ),
    ).toBe(false);
  });

  it("orders by record, with the unknown players last", () => {
    const pool = buildPlayerPool(bootstrap());

    expect(pool.players.at(0)?.code).toBe(KNOWN_CODE);
    expect(pool.players.at(-1)?.record).toBeNull();
  });

  it("reports the earliest deadline whatever order FPL lists events in", () => {
    expect(buildPlayerPool(bootstrap()).firstDeadline).toBe(
      "2026-08-21T17:30:00Z",
    );
  });

  it("refuses a payload that does not match the source contract", () => {
    expect(() => buildPlayerPool({ elements: [] })).toThrow();
  });
});

describe("fetchPlayerPool", () => {
  it("reads the proxied bootstrap and fixture list", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockImplementation((input) =>
        Promise.resolve(
          String(input).includes("fixtures")
            ? Response.json([{ event: 1, team_h: 1, team_a: 2 }])
            : Response.json(bootstrap()),
        ),
      );

    const pool = await fetchPlayerPool(fetchApi);

    expect(fetchApi.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/fpl/bootstrap-static/",
      "/api/fpl/fixtures/",
    ]);
    expect(pool.players).toHaveLength(2);
    expect(pool.fixtures).toHaveLength(1);
    expect(pool.clubCodeByTeamId.get(1)).toBe(3);
  });

  it("loses the fixture column rather than the page when fixtures fail", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockImplementation((input) =>
        Promise.resolve(
          String(input).includes("fixtures")
            ? new Response("", { status: 500 })
            : Response.json(bootstrap()),
        ),
      );

    const pool = await fetchPlayerPool(fetchApi);

    expect(pool.players).toHaveLength(2);
    expect(pool.fixtures).toEqual([]);
  });

  it("fails loudly rather than returning an empty pool", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("", { status: 503 }));

    await expect(fetchPlayerPool(fetchApi)).rejects.toThrow(/503/);
  });

  it("separates a source that broke its contract from one that never answered", async () => {
    const contract = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ elements: [] }));
    await expect(fetchPlayerPool(contract)).rejects.toMatchObject({
      reason: "source_contract_failed",
    });

    const offline = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("network"));
    await expect(fetchPlayerPool(offline)).rejects.toMatchObject({
      reason: "unreachable",
    });
  });
});
