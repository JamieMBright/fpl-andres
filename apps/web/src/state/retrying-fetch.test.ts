import { describe, expect, it, vi } from "vitest";

import { retryingFetch, RETRY_BASE_MS } from "./retrying-fetch";

const noWait = () => Promise.resolve();

function ok(): Response {
  return Response.json({ elements: [] });
}

describe("a transient failure costs a retry, not the tab", () => {
  it("retries a dropped connection and then succeeds", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(ok());

    const response = await retryingFetch(
      "/api/fpl/bootstrap-static",
      undefined,
      fetchApi,
      noWait,
    );

    expect(response.ok).toBe(true);
    expect(fetchApi).toHaveBeenCalledTimes(2);
  });

  /**
   * The case the reader sees. A 502 from the proxy means the function ran and
   * could not reach FPL in time, which the next attempt often can.
   */
  it("retries a retryable status and then succeeds", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        Response.json({ reason: "unreachable" }, { status: 502 }),
      )
      .mockResolvedValueOnce(ok());

    const response = await retryingFetch(
      "/api/fpl/bootstrap-static",
      undefined,
      fetchApi,
      noWait,
    );

    expect(response.status).toBe(200);
    expect(fetchApi).toHaveBeenCalledTimes(2);
  });

  it("does not retry a status the next attempt cannot improve", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ error: "nope" }, { status: 400 }));

    const response = await retryingFetch(
      "/api/fpl/bootstrap-static",
      undefined,
      fetchApi,
      noWait,
    );

    expect(response.status).toBe(400);
    expect(fetchApi).toHaveBeenCalledTimes(1);
  });

  it("gives up after a bounded number of attempts and returns the last response", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json({ reason: "unreachable" }, { status: 502 }),
      );

    const response = await retryingFetch(
      "/api/fpl/bootstrap-static",
      undefined,
      fetchApi,
      noWait,
    );

    expect(response.status).toBe(502);
    expect(fetchApi).toHaveBeenCalledTimes(3);
  });

  it("rethrows the last error when every attempt threw", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      retryingFetch("/api/fpl/fixtures", undefined, fetchApi, noWait),
    ).rejects.toThrow(TypeError);
    expect(fetchApi).toHaveBeenCalledTimes(3);
  });

  it("does not retry an abort, because that is the caller changing their mind", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new DOMException("aborted", "AbortError"));

    await expect(
      retryingFetch("/api/fpl/fixtures", undefined, fetchApi, noWait),
    ).rejects.toThrow(DOMException);
    expect(fetchApi).toHaveBeenCalledTimes(1);
  });

  it("backs off further between each attempt", async () => {
    const waits: number[] = [];
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      retryingFetch("/api/fpl/fixtures", undefined, fetchApi, (ms) => {
        waits.push(ms);
        return Promise.resolve();
      }),
    ).rejects.toThrow(TypeError);

    expect(waits).toEqual([RETRY_BASE_MS, RETRY_BASE_MS * 2]);
  });

  /**
   * A retry that ignores the signal keeps a request alive after the reader has
   * navigated away, and reports its failure into a page that is gone.
   */
  it("stops retrying once the caller's signal is aborted", async () => {
    const controller = new AbortController();
    const fetchApi = vi.fn<typeof fetch>().mockImplementation(() => {
      controller.abort();
      return Promise.reject(new TypeError("Failed to fetch"));
    });

    await expect(
      retryingFetch(
        "/api/fpl/fixtures",
        { signal: controller.signal },
        fetchApi,
        noWait,
      ),
    ).rejects.toThrow();
    expect(fetchApi).toHaveBeenCalledTimes(1);
  });
});
