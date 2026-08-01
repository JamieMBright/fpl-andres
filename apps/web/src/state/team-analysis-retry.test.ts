import { describe, expect, it, vi } from "vitest";

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
