import { describe, expect, it, vi } from "vitest";

import { createTeamPublicStateResponse } from "../../../../api/_lib/team-public-state-response";

const fetchedAt = "2026-09-12T12:30:00.000Z";

function bootstrapResponse(): Response {
  return jsonResponse(bootstrapDocument());
}

function bootstrapDocument() {
  return {
    events: [
      {
        id: 5,
        deadline_time: "2026-09-12T10:30:00Z",
      },
    ],
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

function entryResponse(currentEvent: number | null = 5): Response {
  return jsonResponse(entryDocument(currentEvent));
}

function entryDocument(currentEvent: number | null = 5) {
  return {
    id: 123,
    name: "Public XI",
    started_event: 1,
    current_event: currentEvent,
    last_deadline_bank: currentEvent === null ? null : 17,
    last_deadline_value: currentEvent === null ? null : 1004,
    last_deadline_total_transfers: 4,
  };
}

function picksResponse(): Response {
  return jsonResponse({
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
  });
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("public team state response", () => {
  it("fetches entry, official deadline, and processed picks into ready state", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/bootstrap-static/")) return bootstrapResponse();
        if (url.endsWith("/entry/123/")) return entryResponse();
        if (url.endsWith("/entry/123/event/5/picks/")) return picksResponse();
        throw new Error(`unexpected URL: ${url}`);
      });

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });

    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    await expect(response.json()).resolves.toMatchObject({
      status: "ready",
      state: {
        entryId: 123,
        event: 5,
        stateAsOf: "2026-09-12T10:30:00Z",
        dataAvailableAt: fetchedAt,
      },
    });
    expect(fetchUpstream).toHaveBeenCalledTimes(3);
  });

  it("resolves each pick to a named player from the bootstrap tables", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/bootstrap-static/")) return bootstrapResponse();
        if (url.endsWith("/entry/123/")) return entryResponse();
        if (url.endsWith("/entry/123/event/5/picks/")) return picksResponse();
        throw new Error(`unexpected URL: ${url}`);
      });

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });
    const body = (await response.json()) as {
      state: { picks: { elementId: number; identity: unknown }[] };
    };

    expect(body.state.picks.at(0)?.identity).toEqual({
      webName: "Player 101",
      positionCode: "GKP",
      teamShortName: "ARS",
      priceTenths: 45,
      code: 900_000,
    });
    expect(body.state.picks.every((pick) => pick.identity !== null)).toBe(true);
  });

  it("leaves a pick opaque when the bootstrap cannot resolve it", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/bootstrap-static/")) {
          // An element whose club is absent must not be half-named.
          const document = bootstrapDocument();
          document.teams = [{ id: 99, short_name: "XXX" }];
          return jsonResponse(document);
        }
        if (url.endsWith("/entry/123/")) return entryResponse();
        if (url.endsWith("/entry/123/event/5/picks/")) return picksResponse();
        throw new Error(`unexpected URL: ${url}`);
      });

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });
    const body = (await response.json()) as {
      state: { picks: { identity: unknown }[] };
    };

    expect(body.state.picks.every((pick) => pick.identity === null)).toBe(true);
  });

  it("returns unavailable before picks when the entry has no processed event", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = String(input);
        return url.endsWith("/entry/123/")
          ? entryResponse(null)
          : bootstrapResponse();
      });

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      status: "unavailable",
      reason: "no_processed_event",
    });
    expect(fetchUpstream).toHaveBeenCalledTimes(2);
  });

  it("returns unavailable without guessing why public picks are missing", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/bootstrap-static/")) return bootstrapResponse();
        if (url.endsWith("/entry/123/")) return entryResponse();
        return jsonResponse({ detail: "Not found." }, 404);
      });

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      status: "unavailable",
      reason: "picks_unavailable",
      event: 5,
    });
  });

  it("returns unavailable when the public entry does not exist", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) =>
        String(input).endsWith("/entry/123/")
          ? jsonResponse({ detail: "Not found." }, 404)
          : bootstrapResponse(),
      );

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      status: "unavailable",
      reason: "entry_unavailable",
    });
  });

  it("degrades when a required FPL source returns a non-success status", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) =>
        String(input).endsWith("/entry/123/")
          ? jsonResponse({ detail: "Upstream failed." }, 500)
          : bootstrapResponse(),
      );

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
      sleep: vi.fn().mockResolvedValue(undefined),
      random: () => 0.5,
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      status: "degraded",
      reason: "fpl_source_failed",
    });
  });

  it("degrades when FPL substitutes a different entry ID", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/bootstrap-static/")) return bootstrapResponse();
        if (url.endsWith("/entry/123/")) {
          return jsonResponse({ ...entryDocument(), id: 456 });
        }
        throw new Error(`unexpected URL: ${url}`);
      });

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      status: "degraded",
      reason: "source_contract_failed",
    });
    expect(fetchUpstream).toHaveBeenCalledTimes(2);
  });

  it("degrades when the processed event has no official deadline", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) =>
        String(input).endsWith("/entry/123/")
          ? entryResponse()
          : jsonResponse({ events: [] }),
      );

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      status: "degraded",
      reason: "source_contract_failed",
    });
    expect(fetchUpstream).toHaveBeenCalledTimes(2);
  });

  it("degrades when entry and picks evidence contradict each other", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/bootstrap-static/")) return bootstrapResponse();
        if (url.endsWith("/entry/123/")) return entryResponse();
        const picks = await picksResponse().json();
        return jsonResponse({
          ...picks,
          entry_history: { ...picks.entry_history, bank: 18 },
        });
      });

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      status: "degraded",
      reason: "source_contract_failed",
    });
  });

  it("returns degraded when a required FPL source cannot be reached", async () => {
    let time = Date.parse(fetchedAt);
    const fetchUpstream = vi.fn<typeof fetch>().mockImplementation(async () => {
      time += 3_000;
      throw new TypeError("network unavailable");
    });

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => time,
      sleep: vi.fn().mockResolvedValue(undefined),
      random: () => 0.5,
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      status: "degraded",
      reason: "fpl_unreachable",
    });
  });

  it("degrades as fpl_source_failed when upstream Content-Type is not JSON", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) =>
        String(input).endsWith("/entry/123/")
          ? new Response("<html>maintenance</html>", {
              status: 200,
              headers: { "Content-Type": "text/html" },
            })
          : bootstrapResponse(),
      );

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      status: "degraded",
      reason: "fpl_source_failed",
    });
  });

  it("degrades as fpl_source_failed when upstream exceeds the size limit", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) =>
        String(input).endsWith("/entry/123/")
          ? new Response("{}", {
              status: 200,
              headers: {
                "Content-Type": "application/json",
                "Content-Length": String(6 * 1024 * 1024),
              },
            })
          : bootstrapResponse(),
      );

    const response = await createTeamPublicStateResponse(123, "GET", {
      fetchUpstream,
      now: () => Date.parse(fetchedAt),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      status: "degraded",
      reason: "fpl_source_failed",
    });
  });

  it("rejects invalid IDs and methods before contacting FPL", async () => {
    const fetchUpstream = vi.fn<typeof fetch>();

    const invalidId = await createTeamPublicStateResponse(0, "GET", {
      fetchUpstream,
    });
    const invalidMethod = await createTeamPublicStateResponse(123, "POST", {
      fetchUpstream,
    });

    expect(invalidId.status).toBe(400);
    expect(invalidMethod.status).toBe(405);
    expect(invalidMethod.headers.get("Allow")).toBe("GET");
    expect(fetchUpstream).not.toHaveBeenCalled();
  });
});
