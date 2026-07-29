import type { VercelRequest, VercelResponse } from "@vercel/node";
import { afterEach, describe, expect, it, vi } from "vitest";

import teamPublicStateHandler from "../../../../api/team/[id]";

describe("Vercel public team handler", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("normalizes the route ID and forwards a ready JSON response", async () => {
    const fetchUpstream = vi
      .fn<typeof fetch>()
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/bootstrap-static/")) {
          return jsonResponse({
            events: [{ id: 5, deadline_time: "2026-09-12T10:30:00Z" }],
          });
        }
        if (url.endsWith("/entry/123/")) {
          return jsonResponse({
            id: 123,
            name: "Public XI",
            started_event: 1,
            current_event: 5,
            last_deadline_bank: 17,
            last_deadline_value: 1004,
            last_deadline_total_transfers: 4,
          });
        }
        return jsonResponse({
          active_chip: null,
          entry_history: {
            event: 5,
            bank: 17,
            value: 1004,
            event_transfers: 0,
            event_transfers_cost: 0,
          },
          picks: Array.from({ length: 15 }, (_, index) => ({
            element: index + 1,
            position: index + 1,
            multiplier: index === 0 ? 2 : index > 10 ? 0 : 1,
            is_captain: index === 0,
            is_vice_captain: index === 1,
          })),
        });
      });
    vi.stubGlobal("fetch", fetchUpstream);
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-09-12T12:30:00Z"));

    const sent: { body?: Buffer; status?: number } = {};
    const headers = new Map<string, string | number | readonly string[]>();
    const response = responseDouble(sent, headers);
    const request = {
      method: "GET",
      query: { id: "123" },
    } as unknown as VercelRequest;

    await teamPublicStateHandler(request, response);

    expect(sent.status).toBe(200);
    expect(JSON.parse(sent.body?.toString("utf8") ?? "")).toMatchObject({
      status: "ready",
      state: { entryId: 123, event: 5 },
    });
    expect(headers.get("cache-control")).toBe("private, no-store");
    expect(fetchUpstream).toHaveBeenCalledTimes(3);
  });

  it("rejects an array route parameter before upstream access", async () => {
    const fetchUpstream = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchUpstream);
    const sent: { body?: Buffer; status?: number } = {};
    const response = responseDouble(sent, new Map());
    const request = {
      method: "GET",
      query: { id: ["123", "456"] },
    } as unknown as VercelRequest;

    await teamPublicStateHandler(request, response);

    expect(sent.status).toBe(400);
    expect(fetchUpstream).not.toHaveBeenCalled();
  });
});

function jsonResponse(payload: unknown): Response {
  return Response.json(payload, {
    headers: { "Content-Type": "application/json" },
  });
}

function responseDouble(
  sent: { body?: Buffer; status?: number },
  headers: Map<string, string | number | readonly string[]>,
): VercelResponse {
  return {
    setHeader(name: string, value: string | number | readonly string[]) {
      headers.set(name.toLowerCase(), value);
      return this;
    },
    status(status: number) {
      sent.status = status;
      return this;
    },
    send(body: Buffer) {
      sent.body = body;
      return this;
    },
  } as unknown as VercelResponse;
}
