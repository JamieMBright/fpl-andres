import { afterEach, describe, expect, it, vi } from "vitest";

import { createTeamPublicStateResponse } from "../../../../api/_lib/team-public-state-response";

/**
 * Audit items #85, #88, #92 and #93.
 *
 * A spike in 502s was invisible until someone reported it, a contract failure
 * recorded neither which source failed nor what status it arrived with, there
 * was no timing anywhere, and the sequential picks fetch inherited whatever
 * deadline the two parallel fetches had left behind.
 *
 * These assert the log lines themselves rather than that logging happened,
 * because the point of the line is that an alert can be written against its
 * fields. A rename that keeps the line but loses the field breaks the alert
 * silently, and nothing else would notice.
 */

function captured(): {
  info: string[];
  warn: string[];
  all: () => Record<string, unknown>[];
} {
  const info: string[] = [];
  const warn: string[] = [];
  vi.spyOn(console, "log").mockImplementation((line: unknown) => {
    info.push(String(line));
  });
  vi.spyOn(console, "warn").mockImplementation((line: unknown) => {
    warn.push(String(line));
  });
  return {
    info,
    warn,
    all: () =>
      [...info, ...warn].map(
        (line) => JSON.parse(line) as Record<string, unknown>,
      ),
  };
}

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

function entryDocument(currentEvent: number | null = 5) {
  return {
    id: 123,
    name: "Public XI",
    started_event: 1,
    current_event: currentEvent,
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

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Overrides = {
  entry?: () => Response;
  bootstrap?: () => Response;
  picks?: () => Response;
};

function upstream(overrides: Overrides = {}) {
  return vi.fn<typeof fetch>().mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/bootstrap-static/"))
      return (overrides.bootstrap ?? (() => json(bootstrapDocument())))();
    if (url.endsWith("/entry/123/"))
      return (overrides.entry ?? (() => json(entryDocument())))();
    if (url.includes("/picks/"))
      return (overrides.picks ?? (() => json(picksDocument())))();
    throw new Error(`unexpected URL: ${url}`);
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("upstream outcome lines", () => {
  it("records one line per source, naming the source and its status", async () => {
    const log = captured();
    await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream(),
      now: () => Date.parse("2026-09-12T12:30:00.000Z"),
    });

    const outcomes = log
      .all()
      .filter((line) => line.event === "upstream_outcome");
    expect(outcomes.map((line) => line.source).sort()).toEqual([
      "bootstrap",
      "entry",
      "picks",
    ]);
    for (const outcome of outcomes) {
      expect(outcome.status).toBe(200);
      expect(outcome.reason).toBeNull();
      expect(outcome.route).toBe("/api/team/:id");
      expect(typeof outcome.durationMs).toBe("number");
    }
  });

  it("raises the level to warn when a source could not be read", async () => {
    const log = captured();
    await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream({
        entry: () => new Response("<html>gateway</html>", { status: 502 }),
      }),
      sleep: async () => {},
      random: () => 0,
      now: () => Date.parse("2026-09-12T12:30:00.000Z"),
    });

    const failed = log
      .all()
      .filter(
        (line) => line.event === "upstream_outcome" && line.source === "entry",
      );
    expect(failed).toHaveLength(1);
    expect(failed[0]?.level).toBe("warn");
    expect(log.warn.length).toBeGreaterThan(0);
  });

  it("shares one request id across every line of a request", async () => {
    const log = captured();
    await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream(),
      now: () => Date.parse("2026-09-12T12:30:00.000Z"),
    });

    const ids = new Set(log.all().map((line) => line.requestId));
    expect(ids.size).toBe(1);
    expect([...ids][0]).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe("handler outcome line", () => {
  it("splits the total into upstream wait and local processing", async () => {
    const log = captured();
    // A clock that advances 100ms per read: three fetches wait, the rest is ours.
    let clock = Date.parse("2026-09-12T12:30:00.000Z");
    await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream(),
      now: () => {
        clock += 100;
        return clock;
      },
    });

    const outcome = log.all().find((line) => line.event === "handler_outcome");
    expect(outcome).toBeDefined();
    expect(outcome?.status).toBe(200);
    expect(outcome?.route).toBe("/api/team/:id");
    expect(Number(outcome?.upstreamMs)).toBeGreaterThan(0);
    expect(Number(outcome?.totalMs)).toBeGreaterThan(0);
    expect(Number(outcome?.localMs)).toBeGreaterThanOrEqual(0);
  });

  it("never reports negative local time when the clock disagrees with itself", async () => {
    const log = captured();
    // Concurrent sources overlap, so summed upstream time can exceed the wall
    // clock. That must read as zero local time, not as negative work.
    await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream(),
      now: () => Date.parse("2026-09-12T12:30:00.000Z"),
    });
    const outcome = log.all().find((line) => line.event === "handler_outcome");
    expect(Number(outcome?.localMs)).toBeGreaterThanOrEqual(0);
  });

  it("carries the refusal reason, so an alert can group by cause", async () => {
    const log = captured();
    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream({
        picks: () => json({ detail: "Not found." }, 404),
      }),
      now: () => Date.parse("2026-09-12T12:30:00.000Z"),
    });

    expect(response.status).toBe(200);
    const outcome = log.all().find((line) => line.event === "handler_outcome");
    expect(outcome?.reason).toBe("picks_unavailable");
    expect(outcome?.level).toBe("info");
  });

  it("warns on a degraded response, which is the line an alert fires on", async () => {
    const log = captured();
    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream({
        bootstrap: () => new Response("nope", { status: 500 }),
      }),
      sleep: async () => {},
      random: () => 0,
      now: () => Date.parse("2026-09-12T12:30:00.000Z"),
    });

    expect(response.status).toBe(503);
    const outcome = log.all().find((line) => line.event === "handler_outcome");
    expect(outcome?.level).toBe("warn");
    expect(outcome?.status).toBe(503);
    expect(String(outcome?.reason)).toContain("fpl_");
  });
});

describe("contract failure diagnostics", () => {
  it("names the upstream statuses so a schema change is told from a block page", async () => {
    const log = captured();
    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream({
        // A 200 whose shape no longer matches: this is a schema change.
        entry: () => json({ id: 123, current_event: 5, unexpected: true }),
        picks: () => json({ ...picksDocument(), entry_history: undefined }),
      }),
      now: () => Date.parse("2026-09-12T12:30:00.000Z"),
    });

    expect(response.status).toBe(503);
    const failure = log
      .all()
      .find((line) => line.event === "source_contract_failed");
    expect(failure).toBeDefined();
    expect(failure?.upstreamStatuses).toMatchObject({
      entry: 200,
      bootstrap: 200,
    });
  });

  it("records the failing field path but never a payload value", async () => {
    const log = captured();
    await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream({
        entry: () =>
          json({ id: 123, current_event: 5, name: "Secret Manager Name" }),
        picks: () =>
          json({
            ...picksDocument(),
            entry_history: { ...picksDocument().entry_history, bank: 999 },
          }),
      }),
      now: () => Date.parse("2026-09-12T12:30:00.000Z"),
    });

    const failure = log
      .all()
      .find((line) => line.event === "source_contract_failed");
    expect(failure).toBeDefined();
    expect(JSON.stringify(failure)).not.toContain("Secret Manager Name");
    expect(JSON.stringify(failure)).not.toContain("999");
  });

  it("still answers source_contract_failed to the caller", async () => {
    captured();
    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream: upstream({
        entry: () => json({ id: 999, current_event: 5 }),
      }),
      now: () => Date.parse("2026-09-12T12:30:00.000Z"),
    });
    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toMatchObject({
      status: "degraded",
      reason: "source_contract_failed",
    });
  });
});

describe("picks budget", () => {
  it("gives picks a full budget rather than the remainder of the first two", async () => {
    // Audit item #88. The opening pair run concurrently, so they cannot starve
    // each other. Picks is sequential and used to inherit their deadline: a
    // pair that took eight of eight and a half seconds left picks a quarter
    // second, and the request degraded on the one fetch that had done nothing
    // wrong. Here the clock jumps eight seconds during the pair.
    captured();
    let clock = Date.parse("2026-09-12T12:30:00.000Z");
    let servedPicks = false;
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/bootstrap-static/")) {
          clock += 8_000;
          return json(bootstrapDocument());
        }
        if (url.endsWith("/entry/123/")) return json(entryDocument());
        if (url.includes("/picks/")) {
          servedPicks = true;
          return json(picksDocument());
        }
        throw new Error(`unexpected URL: ${url}`);
      });

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      sleep: async () => {},
      random: () => 0,
      now: () => clock,
    });

    expect(servedPicks).toBe(true);
    expect(response.status).toBe(200);
  });
});
