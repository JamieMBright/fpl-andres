import teamStateCases from "../../../../packages/contracts/fixtures/public-team-state-cases.json";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  initialTeamAnalysisState,
  loadCachedPublicTeamState,
  reduceTeamAnalysis,
  refreshTeamAnalysis,
  saveCachedPublicTeamState,
  teamPublicStateStorageKey,
} from "./team-analysis";

const ENTRY_ID = 123;
const readyState = teamStateCases.valid[0];

describe("team analysis state machine", () => {
  beforeEach(() => localStorage.clear());

  it("moves idle to loading to ready and caches only validated state", async () => {
    const loading = reduceTeamAnalysis(initialTeamAnalysisState, {
      type: "load",
    });
    expect(loading).toEqual({ status: "loading" });

    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ status: "ready", state: readyState }));
    const result = await refreshTeamAnalysis(ENTRY_ID, null, {
      fetchApi,
      storage: localStorage,
    });

    expect(result).toEqual({ status: "ready", state: readyState });
    expect(loadCachedPublicTeamState(localStorage, ENTRY_ID)).toEqual(
      readyState,
    );
    expect(fetchApi).toHaveBeenCalledWith("/api/team/123", {
      headers: { Accept: "application/json" },
      signal: expect.any(AbortSignal),
    });
  });

  it("preserves a cached ready snapshot as stale when refresh is degraded", async () => {
    saveCachedPublicTeamState(localStorage, ENTRY_ID, readyState);
    const cached = loadCachedPublicTeamState(localStorage, ENTRY_ID);
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json(
          { status: "degraded", reason: "fpl_unreachable" },
          { status: 503 },
        ),
      );

    const result = await refreshTeamAnalysis(ENTRY_ID, cached, {
      fetchApi,
      storage: localStorage,
    });

    expect(result).toEqual({
      status: "stale",
      state: readyState,
      reason: "fpl_unreachable",
    });
  });

  it("returns degraded or unavailable without manufacturing a snapshot", async () => {
    const degraded = await refreshTeamAnalysis(ENTRY_ID, null, {
      fetchApi: vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          Response.json(
            { status: "degraded", reason: "fpl_source_failed" },
            { status: 503 },
          ),
        ),
      storage: localStorage,
    });
    const unavailable = await refreshTeamAnalysis(ENTRY_ID, null, {
      fetchApi: vi.fn<typeof fetch>().mockResolvedValue(
        Response.json({
          status: "unavailable",
          reason: "no_processed_event",
        }),
      ),
      storage: localStorage,
    });

    expect(degraded).toEqual({
      status: "degraded",
      reason: "fpl_source_failed",
    });
    expect(unavailable).toEqual({
      status: "unavailable",
      reason: "no_processed_event",
    });
  });

  it("returns error for malformed JSON and removes invalid cached bytes", async () => {
    const key = teamPublicStateStorageKey(ENTRY_ID);
    localStorage.setItem(key, JSON.stringify({ entryId: ENTRY_ID }));

    expect(loadCachedPublicTeamState(localStorage, ENTRY_ID)).toBeNull();
    expect(localStorage.getItem(key)).toBeNull();

    const result = await refreshTeamAnalysis(ENTRY_ID, null, {
      fetchApi: vi.fn<typeof fetch>().mockResolvedValue(
        new Response("not-json", {
          headers: { "Content-Type": "application/json" },
        }),
      ),
      storage: localStorage,
    });
    expect(result).toEqual({ status: "error", reason: "invalid_response" });
  });

  it("rejects a valid snapshot bound to a different Team ID", async () => {
    const result = await refreshTeamAnalysis(ENTRY_ID, null, {
      fetchApi: vi.fn<typeof fetch>().mockResolvedValue(
        Response.json({
          status: "ready",
          state: { ...readyState, entryId: ENTRY_ID + 1 },
        }),
      ),
      storage: localStorage,
    });

    expect(result).toEqual({ status: "error", reason: "invalid_response" });
    expect(localStorage.length).toBe(0);
  });

  it("rejects invalid IDs before storage or network access", async () => {
    const fetchApi = vi.fn<typeof fetch>();

    await expect(
      refreshTeamAnalysis(0, null, { fetchApi, storage: localStorage }),
    ).rejects.toThrow("Team ID");
    expect(() => teamPublicStateStorageKey(1.5)).toThrow("Team ID");
    expect(fetchApi).not.toHaveBeenCalled();
  });
});
