import { beforeEach, describe, expect, it, vi } from "vitest";

import { SourceCache } from "../../../../api/_lib/source-cache";
import {
  createTeamPublicStateResponse,
  resetSourceCache,
} from "../../../../api/_lib/team-public-state-response";

/**
 * Audit item #87, end to end rather than at the cache.
 *
 * The saving claimed here is upstream requests avoided, so it is counted
 * directly. The number that matters: two managers looked up in the same minute
 * used to pull the 1.3 MB bootstrap document twice.
 */

function bootstrapDocument() {
  return {
    events: [{ id: 5, deadline_time: "2026-09-12T10:30:00Z" }],
    element_types: [
      { id: 1, singular_name_short: "GKP" },
      { id: 2, singular_name_short: "DEF" },
      { id: 3, singular_name_short: "MID" },
      { id: 4, singular_name_short: "FWD" },
    ],
    teams: [
      { id: 1, short_name: "ARS" },
      { id: 2, short_name: "AVL" },
    ],
    elements: Array.from({ length: 15 }, (_, index) => ({
      id: 101 + index,
      web_name: `Player ${101 + index}`,
      code: 900_000 + index,
      element_type: ((index % 4) + 1) as 1 | 2 | 3 | 4,
      team: (index % 2) + 1,
      now_cost: 45 + index,
    })),
  };
}

function entryDocument(entryId: number) {
  return {
    id: entryId,
    name: `Team ${entryId}`,
    started_event: 1,
    current_event: 5,
    last_deadline_bank: 17,
    last_deadline_value: 1004,
    last_deadline_total_transfers: 4,
  };
}

function picksDocument() {
  return {
    active_chip: null,
    entry_history: {
      event: 5,
      bank: 17,
      value: 1004,
      event_transfers: 1,
      event_transfers_cost: 0,
    },
    picks: Array.from({ length: 15 }, (_, index) => ({
      element: 101 + index,
      position: index + 1,
      multiplier: index === 0 ? 2 : index > 10 ? 0 : 1,
      is_captain: index === 0,
      is_vice_captain: index === 1,
    })),
  };
}

function json(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function counting(): {
  fetchUpstream: typeof fetch;
  byPath: Map<string, number>;
} {
  const byPath = new Map<string, number>();
  const fetchUpstream = vi
    .fn<typeof fetch>()
    .mockImplementation(async (input) => {
      const url = new URL(String(input));
      byPath.set(url.pathname, (byPath.get(url.pathname) ?? 0) + 1);
      if (url.pathname.endsWith("/bootstrap-static/"))
        return json(bootstrapDocument());
      if (url.pathname.includes("/picks/")) return json(picksDocument());
      const entryId = Number(url.pathname.split("/")[3]);
      return json(entryDocument(entryId));
    });
  return { fetchUpstream, byPath };
}

beforeEach(() => {
  resetSourceCache();
  vi.restoreAllMocks();
});

describe("upstream load", () => {
  it("pulls bootstrap once for two managers in the same minute", async () => {
    const clock = { at: Date.parse("2026-09-12T12:30:00.000Z") };
    const cache = new SourceCache<never>(() => clock.at) as never;
    const { fetchUpstream, byPath } = counting();

    for (const entryId of [123, 456]) {
      const response = await createTeamPublicStateResponse(entryId, "GET", {
        fetchUpstream,
        now: () => clock.at,
        cache,
      });
      expect(response.status).toBe(200);
    }

    expect(byPath.get("/api/bootstrap-static/")).toBe(1);
    // The per-manager sources are never shared, whatever the saving would be.
    expect(byPath.get("/api/entry/123/")).toBe(1);
    expect(byPath.get("/api/entry/456/")).toBe(1);
  });

  it("pulls bootstrap again after its window", async () => {
    const clock = { at: Date.parse("2026-09-12T12:30:00.000Z") };
    const cache = new SourceCache<never>(() => clock.at) as never;
    const { fetchUpstream, byPath } = counting();

    await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => clock.at,
      cache,
    });
    clock.at += 60_001;
    await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => clock.at,
      cache,
    });

    expect(byPath.get("/api/bootstrap-static/")).toBe(2);
  });

  it("never serves one manager's entry to another", async () => {
    // The failure this guards is the reason entry and picks have a TTL of
    // zero. It would be silent: both responses parse, both are well formed,
    // and one manager sees the other's squad.
    const clock = { at: Date.parse("2026-09-12T12:30:00.000Z") };
    const cache = new SourceCache<never>(() => clock.at) as never;
    const { fetchUpstream } = counting();

    const first = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => clock.at,
      cache,
    });
    const second = await createTeamPublicStateResponse(456, "GET", {
      fetchUpstream,
      now: () => clock.at,
      cache,
    });

    const firstBody = (await first.json()) as { state: { entryId: number } };
    const secondBody = (await second.json()) as { state: { entryId: number } };
    expect(firstBody.state.entryId).toBe(123);
    expect(secondBody.state.entryId).toBe(456);
  });

  it("does not hold a failed bootstrap", async () => {
    const clock = { at: Date.parse("2026-09-12T12:30:00.000Z") };
    const cache = new SourceCache<never>(() => clock.at) as never;
    let bootstrapCalls = 0;
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = new URL(String(input));
        if (url.pathname.endsWith("/bootstrap-static/")) {
          bootstrapCalls += 1;
          if (bootstrapCalls <= 3) {
            return new Response("nope", {
              status: 500,
              headers: { "Content-Type": "application/json" },
            });
          }
          return json(bootstrapDocument());
        }
        if (url.pathname.includes("/picks/")) return json(picksDocument());
        return json(entryDocument(123));
      });

    const failed = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      sleep: async () => {},
      random: () => 0,
      now: () => clock.at,
      cache,
    });
    expect(failed.status).toBe(503);

    const recovered = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      sleep: async () => {},
      random: () => 0,
      now: () => clock.at,
      cache,
    });
    expect(recovered.status).toBe(200);
  });

  it("coalesces two concurrent lookups of the same manager into one fetch each", async () => {
    const clock = { at: Date.parse("2026-09-12T12:30:00.000Z") };
    const cache = new SourceCache<never>(() => clock.at) as never;
    const { fetchUpstream, byPath } = counting();

    await Promise.all([
      createTeamPublicStateResponse(123, "GET", {
        fetchUpstream,
        now: () => clock.at,
        cache,
      }),
      createTeamPublicStateResponse(123, "GET", {
        fetchUpstream,
        now: () => clock.at,
        cache,
      }),
    ]);

    expect(byPath.get("/api/entry/123/")).toBe(1);
    expect(byPath.get("/api/bootstrap-static/")).toBe(1);
  });

  it("marks a reused source in the log so it is not counted as a fetch", async () => {
    const lines: string[] = [];
    vi.spyOn(console, "log").mockImplementation((line: unknown) => {
      lines.push(String(line));
    });
    const clock = { at: Date.parse("2026-09-12T12:30:00.000Z") };
    const cache = new SourceCache<never>(() => clock.at) as never;
    const { fetchUpstream } = counting();

    await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => clock.at,
      cache,
    });
    await createTeamPublicStateResponse(456, "GET", {
      fetchUpstream,
      now: () => clock.at,
      cache,
    });

    const bootstrapLines = lines
      .map((line) => JSON.parse(line) as Record<string, unknown>)
      .filter(
        (line) =>
          line.event === "upstream_outcome" && line.source === "bootstrap",
      );
    expect(bootstrapLines.map((line) => line.reused)).toEqual([false, true]);
  });
});
