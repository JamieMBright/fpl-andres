import type { VercelRequest, VercelResponse } from "@vercel/node";
import { afterEach, describe, expect, it, vi } from "vitest";

import fplProxyHandler from "../../../../api/fpl/[...path]";

/**
 * The same request budget, at the handler rather than the limiter.
 *
 * The counters live in module scope because they have to outlive an invocation
 * to mean anything, and that is exactly the thing a unit test of the limiter
 * cannot check. These assert that the handler consults them, refuses with the
 * right status and headers, and does not reach FPL when it refuses -- the last
 * being the whole point.
 */

function request(url: string, address: string): VercelRequest {
  return {
    url,
    method: "GET",
    headers: { "x-vercel-forwarded-for": address },
    query: {},
  } as unknown as VercelRequest;
}

function response(): {
  vercel: VercelResponse;
  headers: Record<string, string>;
  status: () => number;
  body: () => string;
} {
  const headers: Record<string, string> = {};
  let status = 0;
  let body = "";
  const vercel = {
    setHeader(name: string, value: string) {
      headers[name] = value;
      return vercel;
    },
    status(code: number) {
      status = code;
      return vercel;
    },
    send(payload: unknown) {
      body = Buffer.isBuffer(payload)
        ? payload.toString("utf8")
        : String(payload);
      return vercel;
    },
  } as unknown as VercelResponse;
  return { vercel, headers, status: () => status, body: () => body };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("proxy request budget", () => {
  it("refuses past the budget without contacting FPL", async () => {
    const upstream = vi.fn<typeof fetch>().mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", upstream);

    let refused: ReturnType<typeof response> | null = null;
    for (let index = 0; index < 80; index += 1) {
      const current = response();
      await fplProxyHandler(
        request("/api/fpl/bootstrap-static/", "203.0.113.9"),
        current.vercel,
      );
      if (current.status() === 429) {
        refused = current;
        break;
      }
    }

    expect(refused).not.toBeNull();
    expect(upstream.mock.calls.length).toBeLessThanOrEqual(60);
    expect(refused?.headers["Retry-After"]).toMatch(/^\d+$/);
    expect(refused?.headers["Cache-Control"]).toBe("no-store");
    expect(JSON.parse(refused?.body() ?? "{}")).toMatchObject({
      reason: "rate_limited",
    });
  });

  it("advertises the budget on a request it allowed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response("{}", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const current = response();
    await fplProxyHandler(
      request("/api/fpl/bootstrap-static/", "198.51.100.22"),
      current.vercel,
    );

    expect(current.status()).toBe(200);
    expect(current.headers["RateLimit-Limit"]).toBe("60");
    expect(
      Number(current.headers["RateLimit-Remaining"]),
    ).toBeGreaterThanOrEqual(0);
  });

  it("does not charge one address for another's requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response("{}", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const first = response();
    await fplProxyHandler(
      request("/api/fpl/bootstrap-static/", "192.0.2.1"),
      first.vercel,
    );
    const second = response();
    await fplProxyHandler(
      request("/api/fpl/bootstrap-static/", "192.0.2.2"),
      second.vercel,
    );

    expect(first.headers["RateLimit-Remaining"]).toBe("59");
    expect(second.headers["RateLimit-Remaining"]).toBe("59");
  });
});
