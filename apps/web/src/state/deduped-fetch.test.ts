import { afterEach, describe, expect, it, vi } from "vitest";

import { clearInFlight, dedupedFetch } from "./deduped-fetch";

/**
 * Audit item #119. Two components mounting at once, or a StrictMode double
 * render in development, produce two identical requests for the same URL. The
 * second is pure waste, and the proxy behind it has a rate limit.
 */

afterEach(() => {
  clearInFlight();
  vi.restoreAllMocks();
});

function deferred() {
  let resolve!: (value: Response) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Response>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("dedupedFetch", () => {
  it("issues one request for two concurrent identical calls", async () => {
    const gate = deferred();
    const fetchApi = vi.fn(() => gate.promise);

    const first = dedupedFetch(
      "/api/fpl/bootstrap-static/",
      undefined,
      fetchApi,
    );
    const second = dedupedFetch(
      "/api/fpl/bootstrap-static/",
      undefined,
      fetchApi,
    );
    gate.resolve(new Response(JSON.stringify({ elements: [] })));

    await Promise.all([first, second]);

    expect(fetchApi).toHaveBeenCalledTimes(1);
  });

  it("gives both callers a readable body", async () => {
    // A Response body can only be read once, so sharing one without cloning
    // would give the second caller an already-consumed stream.
    const fetchApi = vi.fn(
      async () => new Response(JSON.stringify({ ok: true })),
    );

    const [first, second] = await Promise.all([
      dedupedFetch("/api/team/1", undefined, fetchApi),
      dedupedFetch("/api/team/1", undefined, fetchApi),
    ]);

    expect(await first.json()).toEqual({ ok: true });
    expect(await second.json()).toEqual({ ok: true });
  });

  it("does not deduplicate different urls", async () => {
    const fetchApi = vi.fn(async () => new Response("{}"));

    await Promise.all([
      dedupedFetch("/api/fpl/bootstrap-static/", undefined, fetchApi),
      dedupedFetch("/api/fpl/fixtures/", undefined, fetchApi),
    ]);

    expect(fetchApi).toHaveBeenCalledTimes(2);
  });

  it("issues a fresh request once the first has settled", async () => {
    // A coalescer, not a cache. The data behind these urls changes on a
    // deadline, so a second request after the first finishes must go out.
    const fetchApi = vi.fn(async () => new Response("{}"));

    await dedupedFetch("/api/fpl/fixtures/", undefined, fetchApi);
    await dedupedFetch("/api/fpl/fixtures/", undefined, fetchApi);

    expect(fetchApi).toHaveBeenCalledTimes(2);
  });

  it("clears the entry when the request fails", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("network down"))
      .mockResolvedValueOnce(new Response("{}"));

    await expect(
      dedupedFetch("/api/team/2", undefined, fetchApi),
    ).rejects.toThrow("network down");
    // A failed request left in the map would poison every later call.
    await expect(
      dedupedFetch("/api/team/2", undefined, fetchApi),
    ).resolves.toBeInstanceOf(Response);
    expect(fetchApi).toHaveBeenCalledTimes(2);
  });

  it("propagates the failure to every waiting caller", async () => {
    const gate = deferred();
    const fetchApi = vi.fn(() => gate.promise);

    const first = dedupedFetch("/api/team/3", undefined, fetchApi);
    const second = dedupedFetch("/api/team/3", undefined, fetchApi);
    gate.reject(new TypeError("network down"));

    await expect(first).rejects.toThrow("network down");
    await expect(second).rejects.toThrow("network down");
  });

  it("never shares a request that carries an abort signal", async () => {
    // Sharing would let the first caller's abort cancel the second caller's
    // request, which is a bug that only appears when a component unmounts.
    const fetchApi = vi.fn(async () => new Response("{}"));
    const controller = new AbortController();

    await Promise.all([
      dedupedFetch("/api/team/4", { signal: controller.signal }, fetchApi),
      dedupedFetch("/api/team/4", { signal: controller.signal }, fetchApi),
    ]);

    expect(fetchApi).toHaveBeenCalledTimes(2);
  });
});
