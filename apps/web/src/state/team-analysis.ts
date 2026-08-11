import {
  publicTeamResponseSchema,
  publicTeamStateSchema,
  type PublicTeamDegradedReason,
  type PublicTeamResponse,
  type PublicTeamState,
} from "@fpl-andres/contracts";
import { z } from "zod";

import inputs from "../data/season-inputs.json";
import { SEASON_PLAYERS } from "./season-solver";

const STORAGE_PREFIX = "fpl-andres:public-team-state:v2";
const MAX_PUBLIC_ID = 4_294_967_295;
// A flaky connection should cost a second, not the whole answer. Bounded so a
// genuinely dead endpoint still fails fast enough to say so.
const MAX_ATTEMPTS = 3;
const RETRY_BASE_MS = 250;

const deadlines = inputs.deadlines as string[];
const firstDeadline = deadlines[0];
const startYear = firstDeadline
  ? new Date(firstDeadline).getUTCFullYear()
  : Number.NaN;

function rosterVersion(): string {
  let hash = 2_166_136_261;
  for (const player of [...SEASON_PLAYERS].sort(
    (left, right) => left.code - right.code,
  )) {
    for (const value of `${player.code}:${player.id}|`) {
      hash ^= value.charCodeAt(0);
      hash = Math.imul(hash, 16_777_619);
    }
  }
  return `fnv1a32:${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

export const currentTeamCacheContext = {
  season: Number.isFinite(startYear)
    ? `${startYear}-${String((startYear + 1) % 100).padStart(2, "0")}`
    : "unavailable",
  rosterVersion: rosterVersion(),
} as const;

const cachedTeamStateSchema = z
  .object({
    schemaVersion: z.literal(2),
    season: z.string(),
    rosterVersion: z.string(),
    savedAt: z.iso.datetime(),
    state: publicTeamStateSchema,
  })
  .strict();

export type TeamAnalysisState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "refreshing"; state: PublicTeamState }
  | { status: "ready"; state: PublicTeamState }
  | {
      status: "stale";
      state: PublicTeamState;
      reason: PublicTeamDegradedReason | "network_error" | "invalid_response";
    }
  | { status: "degraded"; reason: PublicTeamDegradedReason }
  | { status: "error"; reason: "network_error" | "invalid_response" }
  | {
      status: "unavailable";
      reason: "entry_unavailable" | "no_processed_event" | "picks_unavailable";
      event?: number;
    };

export type TeamAnalysisAction =
  | { type: "load"; state: PublicTeamState | null }
  | { type: "resolved"; state: TeamAnalysisState };

interface RefreshDependencies {
  fetchApi?: typeof fetch;
  storage: Storage;
  signal?: AbortSignal;
  /** Injected so tests do not wait out the real backoff. */
  wait?: (ms: number) => Promise<void>;
}

export const initialTeamAnalysisState: TeamAnalysisState = { status: "idle" };

export function reduceTeamAnalysis(
  _current: TeamAnalysisState,
  action: TeamAnalysisAction,
): TeamAnalysisState {
  if (action.type === "resolved") return action.state;
  return action.state
    ? { status: "refreshing", state: action.state }
    : { status: "loading" };
}

export function teamPublicStateStorageKey(entryId: number): string {
  requireEntryId(entryId);
  return `${STORAGE_PREFIX}:${entryId}`;
}

export function saveCachedPublicTeamState(
  storage: Storage,
  entryId: number,
  input: unknown,
): PublicTeamState {
  const state = publicTeamStateSchema.parse(input);
  if (state.entryId !== entryId) {
    throw new TypeError("Cached public state does not match the Team ID");
  }
  storage.setItem(
    teamPublicStateStorageKey(entryId),
    JSON.stringify({
      schemaVersion: 2,
      ...currentTeamCacheContext,
      savedAt: new Date().toISOString(),
      state,
    }),
  );
  return state;
}

export function loadCachedPublicTeamState(
  storage: Storage,
  entryId: number,
  now: Date = new Date(),
): PublicTeamState | null {
  const key = teamPublicStateStorageKey(entryId);
  const serialized = storage.getItem(key);
  if (serialized === null) return null;

  try {
    const parsed = cachedTeamStateSchema.safeParse(JSON.parse(serialized));
    if (
      !parsed.success ||
      parsed.data.state.entryId !== entryId ||
      parsed.data.season !== currentTeamCacheContext.season ||
      parsed.data.rosterVersion !== currentTeamCacheContext.rosterVersion ||
      !usableUntilNextDeadline(parsed.data.state.event, now)
    ) {
      storage.removeItem(key);
      return null;
    }
    return parsed.data.state;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

function usableUntilNextDeadline(event: number, now: Date): boolean {
  const next = deadlines[event];
  if (next === undefined) return event === deadlines.length;
  const boundary = Date.parse(next);
  return Number.isFinite(boundary) && now.getTime() < boundary;
}

export async function refreshTeamAnalysis(
  entryId: number,
  previous: PublicTeamState | null,
  dependencies: RefreshDependencies,
): Promise<TeamAnalysisState> {
  requireEntryId(entryId);
  const fetchApi = dependencies.fetchApi ?? fetch;
  const wait =
    dependencies.wait ??
    ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  const signal = dependencies.signal ?? new AbortController().signal;

  let response: Response | null = null;
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
    try {
      response = await fetchApi(`/api/team/${entryId}`, {
        headers: { Accept: "application/json" },
        signal,
      });
      break;
    } catch (error) {
      // An abort is the caller changing their mind, not a failure to retry.
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      if (attempt === MAX_ATTEMPTS - 1) {
        return previous
          ? { status: "stale", state: previous, reason: "network_error" }
          : { status: "error", reason: "network_error" };
      }
      await wait(RETRY_BASE_MS * 2 ** attempt);
    }
  }
  if (response === null) {
    return previous
      ? { status: "stale", state: previous, reason: "network_error" }
      : { status: "error", reason: "network_error" };
  }

  let envelope: PublicTeamResponse;
  try {
    envelope = publicTeamResponseSchema.parse(await response.json());
  } catch {
    return previous
      ? { status: "stale", state: previous, reason: "invalid_response" }
      : { status: "error", reason: "invalid_response" };
  }

  if (envelope.status === "ready") {
    let state: PublicTeamState;
    try {
      const parsed = publicTeamStateSchema.parse(envelope.state);
      if (parsed.entryId !== entryId) {
        throw new TypeError("Cached public state does not match the Team ID");
      }
      state = parsed;
    } catch {
      return previous
        ? { status: "stale", state: previous, reason: "invalid_response" }
        : { status: "error", reason: "invalid_response" };
    }
    try {
      saveCachedPublicTeamState(dependencies.storage, entryId, state);
    } catch {
      // Storage failure (quota, private mode, disabled) does not invalidate
      // the response. The current session still surfaces the fresh snapshot.
    }
    return { status: "ready", state };
  }
  if (envelope.status === "degraded") {
    return previous
      ? { status: "stale", state: previous, reason: envelope.reason }
      : { status: "degraded", reason: envelope.reason };
  }
  return envelope.reason === "picks_unavailable"
    ? {
        status: "unavailable",
        reason: envelope.reason,
        event: envelope.event,
      }
    : { status: "unavailable", reason: envelope.reason };
}

function requireEntryId(entryId: number): void {
  if (!Number.isInteger(entryId) || entryId < 1 || entryId > MAX_PUBLIC_ID) {
    throw new TypeError("Team ID is outside the supported range");
  }
}
