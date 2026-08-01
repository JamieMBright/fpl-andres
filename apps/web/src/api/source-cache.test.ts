import { describe, expect, it, vi } from "vitest";

import { SourceCache, sourceTtlMs } from "../../../../api/_lib/source-cache";

/**
 * Audit item #87. Every call to /api/team/:id fetched the 1.3 MB bootstrap
 * document, identical for every caller and unchanged for minutes. Ten people
 * looking up their teams in the same second pulled it ten times, from the
 * Premier League's servers, under this project's user agent.
 *
 * The tests that matter are the negative ones: that a private source is never
 * held, that a failure is never cached, and that the table cannot grow without
 * bound. A cache that gets those wrong is worse than no cache.
 */

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("coalescing", () => {
  it("shares one flight between concurrent callers", async () => {
    const cache = new SourceCache<string>();
    const gate = deferred<string>();
    const load = vi.fn(() => gate.promise);

    const first = cache.resolve("k", 0, load);
    const second = cache.resolve("k", 0, load);
    gate.resolve("value");

    expect((await first).value).toBe("value");
    expect((await second).value).toBe("value");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("marks the shared caller as reused, so it is not counted as a fetch", async () => {
    const cache = new SourceCache<string>();
    const gate = deferred<string>();
    const load = vi.fn(() => gate.promise);

    const first = cache.resolve("k", 0, load);
    const second = cache.resolve("k", 0, load);
    gate.resolve("value");

    expect((await first).reused).toBe(false);
    expect((await second).reused).toBe(true);
  });

  it("does not coalesce different keys", async () => {
    const cache = new SourceCache<string>();
    const load = vi.fn(async () => "value");
    await Promise.all([
      cache.resolve("a", 0, load),
      cache.resolve("b", 0, load),
    ]);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("fetches again once the shared flight has finished", async () => {
    // Coalescing is not caching. With a TTL of zero the next caller must go
    // upstream, because the answer may have changed.
    const cache = new SourceCache<string>();
    const load = vi.fn(async () => "value");
    await cache.resolve("k", 0, load);
    await cache.resolve("k", 0, load);
    expect(load).toHaveBeenCalledTimes(2);
  });
});

describe("caching", () => {
  it("serves a repeat within the window without fetching", async () => {
    const clock = { at: 1_000 };
    const cache = new SourceCache<string>(() => clock.at);
    const load = vi.fn(async () => "value");

    await cache.resolve("k", 60_000, load);
    clock.at += 59_999;
    const repeat = await cache.resolve("k", 60_000, load);

    expect(repeat.value).toBe("value");
    expect(repeat.reused).toBe(true);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("fetches again once the window has passed", async () => {
    const clock = { at: 1_000 };
    const cache = new SourceCache<string>(() => clock.at);
    const load = vi.fn(async () => "value");

    await cache.resolve("k", 60_000, load);
    clock.at += 60_001;
    await cache.resolve("k", 60_000, load);

    expect(load).toHaveBeenCalledTimes(2);
  });

  it("never holds a source whose TTL is zero", async () => {
    const cache = new SourceCache<string>();
    const load = vi.fn(async () => "private");
    await cache.resolve("k", 0, load);
    await cache.resolve("k", 0, load);
    expect(load).toHaveBeenCalledTimes(2);
    expect(cache.size).toBe(0);
  });
});

describe("failure", () => {
  it("does not cache a rejection", async () => {
    // A cache that remembers failures turns one bad minute into several.
    const cache = new SourceCache<string>();
    const load = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error("upstream down"))
      .mockResolvedValue("value");

    await expect(cache.resolve("k", 60_000, load)).rejects.toThrow(
      "upstream down",
    );
    await expect(cache.resolve("k", 60_000, load)).resolves.toMatchObject({
      value: "value",
    });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("does not leave a rejected flight in the table", async () => {
    const cache = new SourceCache<string>();
    const load = vi
      .fn<() => Promise<string>>()
      .mockRejectedValue(new Error("down"));
    await expect(cache.resolve("k", 0, load)).rejects.toThrow();
    await expect(cache.resolve("k", 0, load)).rejects.toThrow();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("rejects every caller that shared a failed flight, without an unhandled rejection", async () => {
    const cache = new SourceCache<string>();
    const gate = deferred<string>();
    const load = vi.fn(() => gate.promise);
    const first = cache.resolve("k", 0, load);
    const second = cache.resolve("k", 0, load);
    gate.reject(new Error("down"));

    await expect(first).rejects.toThrow("down");
    await expect(second).rejects.toThrow("down");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("does not hold a value the caller says is not cacheable", async () => {
    // The trap this closes: an upstream read resolves with a failure outcome
    // rather than rejecting, so "did the promise reject" is the wrong question.
    // Caching a failure would serve the outage for a minute after upstream
    // recovered, which is worse than not caching at all.
    const clock = { at: 1_000 };
    const cache = new SourceCache<{ ok: boolean }>(() => clock.at);
    const load = vi
      .fn<() => Promise<{ ok: boolean }>>()
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValue({ ok: true });
    const cacheable = (value: { ok: boolean }) => value.ok;

    await cache.resolve("k", 60_000, load, cacheable);
    expect(cache.size).toBe(0);

    const second = await cache.resolve("k", 60_000, load, cacheable);
    expect(second.value).toEqual({ ok: true });
    expect(second.reused).toBe(false);
    expect(cache.size).toBe(1);

    const third = await cache.resolve("k", 60_000, load, cacheable);
    expect(third.reused).toBe(true);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("still shares an uncacheable value with a concurrent caller", async () => {
    // Coalescing and caching answer different questions. Two callers already
    // waiting on the same failing fetch should both get the same answer; only
    // the keeping of it is refused.
    const cache = new SourceCache<{ ok: boolean }>();
    const gate = deferred<{ ok: boolean }>();
    const load = vi.fn(() => gate.promise);
    const first = cache.resolve("k", 60_000, load, (value) => value.ok);
    const second = cache.resolve("k", 60_000, load, (value) => value.ok);
    gate.resolve({ ok: false });

    expect((await first).value).toEqual({ ok: false });
    expect((await second).reused).toBe(true);
    expect(load).toHaveBeenCalledTimes(1);
    expect(cache.size).toBe(0);
  });
});

describe("bounded state", () => {
  it("stops growing once full", async () => {
    const clock = { at: 1_000 };
    const cache = new SourceCache<string>(() => clock.at);
    for (let index = 0; index < 200; index += 1) {
      await cache.resolve(`k-${index}`, 60_000, async () => "value");
    }
    expect(cache.size).toBeLessThanOrEqual(32);
  });

  it("drops expired entries before evicting a live one", async () => {
    const clock = { at: 1_000 };
    const cache = new SourceCache<string>(() => clock.at);
    for (let index = 0; index < 32; index += 1) {
      await cache.resolve(`old-${index}`, 1_000, async () => "value");
    }
    clock.at += 5_000;
    await cache.resolve("new", 60_000, async () => "value");
    expect(cache.size).toBe(1);
  });

  it("keeps the newest entry when everything is live", async () => {
    const clock = { at: 1_000 };
    const cache = new SourceCache<string>(() => clock.at);
    for (let index = 0; index < 40; index += 1) {
      await cache.resolve(`k-${index}`, 60_000, async () => `v-${index}`);
    }
    const load = vi.fn(async () => "refetched");
    const newest = await cache.resolve("k-39", 60_000, load);
    expect(newest.value).toBe("v-39");
    expect(load).not.toHaveBeenCalled();
  });
});

describe("source policy", () => {
  it("holds only bootstrap, which is the same for every caller", () => {
    expect(sourceTtlMs("bootstrap")).toBe(60_000);
    expect(sourceTtlMs("entry")).toBe(0);
    expect(sourceTtlMs("picks")).toBe(0);
  });

  it("gives a source nobody has named a TTL of zero", () => {
    // Same direction as cachePolicyFor: private by default, shared only when
    // named. A new source becomes uncacheable rather than becoming shared.
    expect(sourceTtlMs("something-new")).toBe(0);
  });

  it("agrees with the CDN policy on how stale bootstrap may be", () => {
    // fpl-proxy tells a CDN it may hold bootstrap for 60 seconds. Two layers
    // disagreeing about the same bytes would be a bug nobody could see.
    expect(sourceTtlMs("bootstrap")).toBe(60_000);
  });
});
