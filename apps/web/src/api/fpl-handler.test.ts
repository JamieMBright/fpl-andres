import type { VercelRequest, VercelResponse } from "@vercel/node";
import { afterEach, describe, expect, it, vi } from "vitest";

import fplProxyHandler from "../../../../api/fpl/[...path]";

describe("Vercel FPL handler", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("removes catch-all metadata before forwarding an allowlisted route", async () => {
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ total_players: 1 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", upstreamFetch);

    const sent: { body?: Buffer; status?: number } = {};
    const headers = new Map<string, string | number | readonly string[]>();
    const response = {
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
    const request = {
      method: "GET",
      url: "/api/fpl/bootstrap-static/?path=bootstrap-static",
    } as VercelRequest;

    await fplProxyHandler(request, response);

    expect(sent.status).toBe(200);
    expect(JSON.parse(sent.body?.toString("utf8") ?? "")).toEqual({
      total_players: 1,
    });
    expect(headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(String(upstreamFetch.mock.calls[0]?.[0])).toBe(
      "https://fantasy.premierleague.com/api/bootstrap-static/",
    );
  });

  it("uses a canonical deep route instead of Vercel's injected event query", async () => {
    const upstreamFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ elements: [] }));
    vi.stubGlobal("fetch", upstreamFetch);
    const sent: { status?: number } = {};
    const response = {
      setHeader() {
        return this;
      },
      status(status: number) {
        sent.status = status;
        return this;
      },
      send() {
        return this;
      },
    } as unknown as VercelResponse;
    const request = {
      method: "GET",
      url: "/api/fpl/event/2/live/?event=2",
    } as VercelRequest;

    await fplProxyHandler(request, response, "/api/fpl/event/2/live/");

    expect(sent.status).toBe(200);
    expect(String(upstreamFetch.mock.calls[0]?.[0])).toBe(
      "https://fantasy.premierleague.com/api/event/2/live/",
    );
  });
});
