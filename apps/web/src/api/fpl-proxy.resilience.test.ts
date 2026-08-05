import { describe, expect, it, vi } from "vitest";

import { FplDocumentStore } from "../../../../api/_lib/fpl-document-store";
import {
  createFplProxyResponse,
  type FplProxyOutcome,
  publicTtlMsFor,
} from "../../../../api/_lib/fpl-proxy";
import { SourceCache } from "../../../../api/_lib/source-cache";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("FPL proxy resilience", () => {
  it("treats public documents as reusable and per-manager paths as private", () => {
    expect(publicTtlMsFor("/api/bootstrap-static/")).toBeGreaterThan(0);
    expect(publicTtlMsFor("/api/fixtures/")).toBeGreaterThan(0);
    expect(publicTtlMsFor("/api/element-summary/1/")).toBeGreaterThan(0);
    expect(publicTtlMsFor("/api/entry/1/")).toBe(0);
    expect(publicTtlMsFor("/api/entry/1/event/2/picks/")).toBe(0);
    expect(publicTtlMsFor("/api/leagues-classic/1/standings/")).toBe(0);
  });

  it("serves a second bootstrap request from cache without asking FPL again", async () => {
    const upstreamFetch = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => jsonResponse({ total_players: 1 }));
    const cache = new SourceCache<FplProxyOutcome>();

    for (let call = 0; call < 2; call += 1) {
      const response = await createFplProxyResponse(
        "/api/fpl/bootstrap-static/",
        "GET",
        upstreamFetch,
        undefined,
        undefined,
        undefined,
        undefined,
        { cache },
      );
      expect(response.status).toBe(200);
      await expect(response.json()).resolves.toEqual({ total_players: 1 });
    }

    expect(upstreamFetch).toHaveBeenCalledTimes(1);
  });

  it("never caches a failure, so one bad moment is not held for a minute", async () => {
    const upstreamFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ detail: "nope" }, 404))
      .mockResolvedValue(jsonResponse({ total_players: 1 }));
    const cache = new SourceCache<FplProxyOutcome>();
    const sleep = vi
      .fn<(milliseconds: number) => Promise<void>>()
      .mockResolvedValue();

    const first = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      upstreamFetch,
      sleep,
      () => 0.5,
      undefined,
      undefined,
      { cache },
    );
    expect(first.status).toBe(404);

    const second = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      upstreamFetch,
      sleep,
      () => 0.5,
      undefined,
      undefined,
      { cache },
    );
    expect(second.status).toBe(200);
  });

  it("serves the last known-good bootstrap, labelled, when FPL stops answering", async () => {
    const store = new FplDocumentStore();
    const good = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => jsonResponse({ total_players: 7 }));
    const sleep = vi
      .fn<(milliseconds: number) => Promise<void>>()
      .mockResolvedValue();

    const fresh = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      good,
      sleep,
      () => 0.5,
      undefined,
      undefined,
      { store },
    );
    expect(fresh.status).toBe(200);
    expect(fresh.headers.get("X-FPL-Stale")).toBeNull();

    const broken = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("connection reset"));
    const stale = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      broken,
      sleep,
      () => 0.5,
      undefined,
      undefined,
      { store },
    );

    expect(stale.status).toBe(200);
    expect(stale.headers.get("X-FPL-Stale")).toBe("1");
    expect(stale.headers.get("X-FPL-Stale-Age")).not.toBeNull();
    expect(stale.headers.get("X-FPL-Captured-At")).not.toBeNull();
    expect(stale.headers.get("Cache-Control")).toBe(
      "public, s-maxage=30, stale-while-revalidate=600",
    );
    await expect(stale.json()).resolves.toEqual({ total_players: 7 });
  });

  it("does not retain a per-manager response as a shared last known-good copy", async () => {
    const store = new FplDocumentStore();
    const good = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => jsonResponse({ id: 1 }));
    const sleep = vi
      .fn<(milliseconds: number) => Promise<void>>()
      .mockResolvedValue();

    await createFplProxyResponse(
      "/api/fpl/entry/1/",
      "GET",
      good,
      sleep,
      () => 0.5,
      undefined,
      undefined,
      { store },
    );
    expect(store.size).toBe(0);

    const broken = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("connection reset"));
    const failed = await createFplProxyResponse(
      "/api/fpl/entry/1/",
      "GET",
      broken,
      sleep,
      () => 0.5,
      undefined,
      undefined,
      { store },
    );
    expect(failed.status).toBe(502);
  });

  it("still fails when there is nothing retained to fall back to", async () => {
    const broken = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("connection reset"));
    const sleep = vi
      .fn<(milliseconds: number) => Promise<void>>()
      .mockResolvedValue();
    const tiers: string[] = [];

    const response = await createFplProxyResponse(
      "/api/fpl/bootstrap-static/",
      "GET",
      broken,
      sleep,
      () => 0.5,
      undefined,
      undefined,
      {
        store: new FplDocumentStore(),
        onOutcome: ({ tier }) => tiers.push(tier),
      },
    );

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      error: "FPL could not be reached within the request budget.",
      reason: "unreachable",
    });
    expect(tiers).toEqual(["failed"]);
  });

  it("reports which tier answered", async () => {
    const store = new FplDocumentStore();
    const cache = new SourceCache<FplProxyOutcome>();
    const upstreamFetch = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => jsonResponse({ total_players: 1 }));
    const tiers: string[] = [];
    const call = (fetchApi: typeof fetch) =>
      createFplProxyResponse(
        "/api/fpl/fixtures/",
        "GET",
        fetchApi,
        async () => {},
        () => 0.5,
        undefined,
        undefined,
        { cache, store, onOutcome: ({ tier }) => tiers.push(tier) },
      );

    await call(upstreamFetch);
    await call(upstreamFetch);
    cache.clear();
    await call(vi.fn<typeof fetch>().mockRejectedValue(new TypeError("down")));

    expect(tiers).toEqual(["fresh", "reused", "stale"]);
  });

  it("forgets a retained copy once it is past its retention window", () => {
    let clock = 0;
    const store = new FplDocumentStore(() => clock, 1_000);
    store.put("key", new ArrayBuffer(2));
    expect(store.get("key")).not.toBeNull();
    clock = 1_001;
    expect(store.get("key")).toBeNull();
    expect(store.size).toBe(0);
  });
});
