import { afterEach, describe, expect, it, vi } from "vitest";

import { refreshTeamAnalysis } from "./team-analysis";

const ENTRY = 212279;

function storage(): Storage {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
    clear: () => map.clear(),
    key: () => null,
    length: 0,
  } as unknown as Storage;
}

const noWait = () => Promise.resolve();

afterEach(() => vi.useRealTimers());

describe("a flaky connection costs a retry, not the answer", () => {
  it("retries a dropped connection and then succeeds", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(
        Response.json({ status: "unavailable", reason: "no_processed_event" }),
      );

    const result = await refreshTeamAnalysis(ENTRY, null, {
      fetchApi,
      storage: storage(),
      wait: noWait,
    });

    expect(fetchApi).toHaveBeenCalledTimes(2);
    expect(result.status).toBe("unavailable");
  });

  it("does not repeat an import after the server exhausted upstream retries", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        Response.json(
          { status: "degraded", reason: "fpl_unreachable" },
          { status: 503 },
        ),
      )
      .mockResolvedValueOnce(
        Response.json({ status: "unavailable", reason: "no_processed_event" }),
      );

    const result = await refreshTeamAnalysis(ENTRY, null, {
      fetchApi,
      storage: storage(),
      wait: noWait,
    });

    expect(fetchApi).toHaveBeenCalledTimes(1);
    expect(result).toEqual({
      status: "degraded",
      reason: "fpl_unreachable",
    });
  });

  it("bounds a stalled import to twenty seconds", async () => {
    vi.useFakeTimers();
    const settled = vi.fn();
    const fetchApi = vi.fn<typeof fetch>(() => new Promise(() => {}));
    void refreshTeamAnalysis(ENTRY, null, {
      fetchApi,
      storage: storage(),
    }).then(settled);

    await vi.advanceTimersByTimeAsync(20_000);

    expect(settled).toHaveBeenCalledWith({
      status: "error",
      reason: "network_error",
    });
    expect(fetchApi.mock.calls[0]?.[1]?.signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancels during backoff without starting another request", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const fetchApi = vi.fn<typeof fetch>().mockRejectedValue(new TypeError());
    const settled = vi.fn();
    void refreshTeamAnalysis(ENTRY, null, {
      fetchApi,
      storage: storage(),
      signal: controller.signal,
    }).catch(settled);
    await vi.advanceTimersByTimeAsync(1);

    controller.abort();
    await vi.advanceTimersByTimeAsync(1_000);

    expect(settled).toHaveBeenCalledWith(expect.any(DOMException));
    expect(fetchApi).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("gives up after a bounded number of attempts", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("Failed to fetch"));

    const result = await refreshTeamAnalysis(ENTRY, null, {
      fetchApi,
      storage: storage(),
      wait: noWait,
    });

    expect(fetchApi).toHaveBeenCalledTimes(3);
    expect(result).toEqual({ status: "error", reason: "network_error" });
  });

  it("backs off further between each attempt", async () => {
    const waits: number[] = [];
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("Failed to fetch"));

    await refreshTeamAnalysis(ENTRY, null, {
      fetchApi,
      storage: storage(),
      wait: (ms) => {
        waits.push(ms);
        return Promise.resolve();
      },
    });

    expect(waits).toEqual([250, 500]);
  });

  it("does not retry an abort, because that is the caller changing their mind", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new DOMException("aborted", "AbortError"));

    await expect(
      refreshTeamAnalysis(ENTRY, null, {
        fetchApi,
        storage: storage(),
        wait: noWait,
      }),
    ).rejects.toThrow(DOMException);
    expect(fetchApi).toHaveBeenCalledTimes(1);
  });

  it("does not retry a response that arrived, however bad it is", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ nonsense: true }));

    const result = await refreshTeamAnalysis(ENTRY, null, {
      fetchApi,
      storage: storage(),
      wait: noWait,
    });

    expect(fetchApi).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ status: "error", reason: "invalid_response" });
  });
});
