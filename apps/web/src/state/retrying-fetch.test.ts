import { describe, expect, it, vi } from "vitest";

import { retryingFetch } from "./retrying-fetch";

const noWait = () => Promise.resolve();

describe("a transient proxy failure costs a retry, not the page", () => {
  it("retries a dropped connection and then succeeds", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(Response.json({ ok: true }));

    const response = await retryingFetch({ fetchApi, wait: noWait })("/api/x");

    expect(fetchApi).toHaveBeenCalledTimes(2);
    expect(response.ok).toBe(true);
  });

  it("retries a 503 from the proxy", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("", { status: 503 }))
      .mockResolvedValueOnce(Response.json({ ok: true }));

    const response = await retryingFetch({ fetchApi, wait: noWait })("/api/x");

    expect(fetchApi).toHaveBeenCalledTimes(2);
    expect(response.status).toBe(200);
  });

  it("returns a non-retryable status without asking again", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("", { status: 404 }));

    const response = await retryingFetch({ fetchApi, wait: noWait })("/api/x");

    expect(fetchApi).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(404);
  });

  it("gives up after a bounded number of attempts and surfaces the failure", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      retryingFetch({ fetchApi, wait: noWait })("/api/x"),
    ).rejects.toBeInstanceOf(TypeError);
    expect(fetchApi).toHaveBeenCalledTimes(3);
  });

  it("returns the last response when every attempt is retryable", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("", { status: 429 }));

    const response = await retryingFetch({ fetchApi, wait: noWait })("/api/x");

    expect(fetchApi).toHaveBeenCalledTimes(3);
    expect(response.status).toBe(429);
  });

  it("does not retry an abort", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new DOMException("aborted", "AbortError"));

    await expect(
      retryingFetch({ fetchApi, wait: noWait })("/api/x"),
    ).rejects.toBeInstanceOf(DOMException);
    expect(fetchApi).toHaveBeenCalledTimes(1);
  });

  it("backs off further between each attempt", async () => {
    const waits: number[] = [];
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      retryingFetch({
        fetchApi,
        wait: (ms) => {
          waits.push(ms);
          return Promise.resolve();
        },
      })("/api/x"),
    ).rejects.toBeInstanceOf(TypeError);

    expect(waits).toEqual([250, 500]);
  });
});
