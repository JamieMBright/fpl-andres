import { describe, expect, it, vi } from "vitest";

import { createFplProxyResponse } from "../../../../api/_lib/fpl-proxy";

describe("FPL proxy transport", () => {
  it("forwards an allowlisted GET with fixed upstream headers only", async () => {
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ total_players: 1 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const response = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      upstreamFetch,
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ total_players: 1 });
    expect(upstreamFetch).toHaveBeenCalledTimes(1);
    const [upstreamUrl, init] = upstreamFetch.mock.calls[0] ?? [];
    expect(String(upstreamUrl)).toBe(
      "https://fantasy.premierleague.com/api/bootstrap-static/",
    );
    const headers = new Headers(init?.headers);
    expect(headers.get("Accept")).toBe("application/json");
    expect(headers.get("User-Agent")).toContain("FPLAndres/0.5");
    expect(headers.has("Authorization")).toBe(false);
    expect(headers.has("Cookie")).toBe(false);
  });

  it("rejects unsupported paths without contacting FPL", async () => {
    const upstreamFetch = vi.fn<typeof fetch>();

    const response = await createFplProxyResponse(
      "/api/fpl/private-endpoint/",
      "GET",
      upstreamFetch,
    );

    expect(response.status).toBe(400);
    expect(upstreamFetch).not.toHaveBeenCalled();
  });

  it("rejects non-GET methods and names the allowed method", async () => {
    const upstreamFetch = vi.fn<typeof fetch>();

    const response = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "POST",
      upstreamFetch,
    );

    expect(response.status).toBe(405);
    expect(response.headers.get("Allow")).toBe("GET");
    expect(upstreamFetch).not.toHaveBeenCalled();
  });

  it("rejects an oversized upstream body before reading it", async () => {
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: {
          "Content-Length": String(5 * 1024 * 1024 + 1),
          "Content-Type": "application/json",
        },
      }),
    );

    const response = await createFplProxyResponse(
      "/api/fpl/element-summary/1/",
      "GET",
      upstreamFetch,
    );

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      error: "FPL returned a response larger than the allowed limit.",
    });
  });

  it("retries a transient upstream response with bounded backoff", async () => {
    const upstreamFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "temporarily unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ total_players: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    const sleep = vi
      .fn<(milliseconds: number) => Promise<void>>()
      .mockResolvedValue();

    const response = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      upstreamFetch,
      sleep,
      () => 0.5,
    );

    expect(response.status).toBe(200);
    expect(upstreamFetch).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledWith(500);
  });

  it("does not retry a non-retryable upstream response", async () => {
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ detail: "not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const sleep = vi.fn<(milliseconds: number) => Promise<void>>();

    const response = await createFplProxyResponse(
      "/api/fpl/entry/123/",
      "GET",
      upstreamFetch,
      sleep,
    );

    expect(response.status).toBe(404);
    expect(upstreamFetch).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });

  it("does not start a retry after the total function budget is exhausted", async () => {
    let currentTime = 0;
    const upstreamFetch = vi.fn<typeof fetch>().mockImplementation(async () => {
      currentTime = 8_200;
      return new Response(
        JSON.stringify({ detail: "temporarily unavailable" }),
        {
          status: 503,
          headers: { "Content-Type": "application/json" },
        },
      );
    });
    const sleep = vi
      .fn<(milliseconds: number) => Promise<void>>()
      .mockImplementation(async (milliseconds) => {
        currentTime += milliseconds;
      });

    const response = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      upstreamFetch,
      sleep,
      () => 0.5,
      () => currentTime,
    );

    expect(response.status).toBe(503);
    expect(upstreamFetch).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });

  it("cancels a chunked response as soon as its body exceeds the limit", async () => {
    let pulls = 0;
    let cancelled = false;
    const body = new ReadableStream<Uint8Array>(
      {
        pull(controller) {
          pulls += 1;
          if (pulls === 1) {
            controller.enqueue(new Uint8Array(4 * 1024 * 1024));
            return;
          }
          if (pulls === 2) {
            controller.enqueue(new Uint8Array(2 * 1024 * 1024));
            return;
          }
          throw new Error("the proxy read beyond its configured body limit");
        },
        cancel() {
          cancelled = true;
        },
      },
      {
        highWaterMark: 0,
      },
    );
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(body, {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const response = await createFplProxyResponse(
      "/api/fpl/element-summary/1/",
      "GET",
      upstreamFetch,
    );

    expect(response.status).toBe(502);
    expect(cancelled).toBe(true);
    expect(pulls).toBeLessThanOrEqual(2);
  });
});
