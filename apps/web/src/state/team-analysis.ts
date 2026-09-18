import {
  publicTeamResponseSchema,
  publicTeamStateSchema,
  type PublicTeamDegradedReason,
  type PublicTeamResponse,
  type PublicTeamState,
} from "@fpl-andres/contracts";
import { z } from "zod";

import { deadlineAfterEvent, FULL_SEASON_DEADLINES } from "./season-deadlines";
import { SEASON_PLAYERS } from "./season-solver";

const STORAGE_PREFIX = "fpl-andres:public-team-state:v2";
const MAX_PUBLIC_ID = 4_294_967_295;
// A flaky connection should cost a second, not the whole answer. Bounded so a
// genuinely dead endpoint still fails fast enough to say so.
const MAX_ATTEMPTS = 3;
const RETRY_BASE_MS = 250;
const RETRYABLE_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);

const firstDeadline = FULL_SEASON_DEADLINES[0]?.deadline;
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

type TeamDegradedReason =
  PublicTeamDegradedReason | "fpl_refused" | "fpl_rate_limited";

export type TeamAnalysisState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "refreshing"; state: PublicTeamState }
  | { status: "ready"; state: PublicTeamState }
  | {
      status: "stale";
      state: PublicTeamState;
      reason:
        | TeamDegradedReason
        | "network_error"
        | "invalid_response"
        | "cached_snapshot";
    }
  | { status: "degraded"; reason: TeamDegradedReason }
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
  storage?: Storage | undefined;
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

export function usableUntilNextDeadline(event: number, now: Date): boolean {
  const next = deadlineAfterEvent(event);
  if (next === null) {
    return event === FULL_SEASON_DEADLINES.at(-1)?.event;
  }
  const boundary = Date.parse(next.deadline);
  return Number.isFinite(boundary) && now.getTime() < boundary;
}

export async function refreshTeamAnalysis(
  entryId: number,
  previous: PublicTeamState | null,
  dependencies: RefreshDependencies,
): Promise<TeamAnalysisState> {
  requireEntryId(entryId);
  const controller = new AbortController();
  const external = dependencies.signal;
  const cancel = () => controller.abort(external?.reason);
  if (external?.aborted) cancel();
  else external?.addEventListener("abort", cancel, { once: true });
  const timer = setTimeout(
    () =>
      controller.abort(new DOMException("Import timed out", "TimeoutError")),
    20_000,
  );
  const signal = controller.signal;
  let onAbort = () => {};
  const aborted = new Promise<never>((_resolve, reject) => {
    onAbort = () => reject(signal.reason);
    if (signal.aborted) onAbort();
    else signal.addEventListener("abort", onAbort, { once: true });
  });
  try {
    return await Promise.race([
      fetchTeamAnalysis(entryId, previous, { ...dependencies, signal }),
      aborted,
    ]);
  } catch (error) {
    if (external?.aborted) throw external.reason;
    if (!signal.aborted) throw error;
    return fallbackState(entryId, previous, "network_error");
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", cancel);
    signal.removeEventListener("abort", onAbort);
  }
}

function fallbackState(
  entryId: number,
  previous: PublicTeamState | null,
  reason: "network_error" | "invalid_response",
): TeamAnalysisState {
  return previous?.entryId === entryId &&
    usableUntilNextDeadline(previous.event, new Date())
    ? { status: "stale", state: previous, reason }
    : { status: "error", reason };
}

async function fetchTeamAnalysis(
  entryId: number,
  previous: PublicTeamState | null,
  dependencies: RefreshDependencies & { signal: AbortSignal },
): Promise<TeamAnalysisState> {
  const fetchApi = dependencies.fetchApi ?? fetch;
  const signal = dependencies.signal;
  const wait =
    dependencies.wait ??
    ((ms: number) =>
      new Promise<void>((resolve, reject) => {
        signal.throwIfAborted();
        const onAbort = () => {
          clearTimeout(timer);
          reject(signal.reason);
        };
        const timer = setTimeout(() => {
          signal.removeEventListener("abort", onAbort);
          resolve();
        }, ms);
        signal.addEventListener("abort", onAbort, { once: true });
      }));

  let response: Response | null = null;
  let envelope: PublicTeamResponse | undefined;
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
    signal.throwIfAborted();
    try {
      response = await fetchApi(`/api/team/${entryId}`, {
        headers: { Accept: "application/json" },
        signal,
      });
      const candidate = publicTeamResponseSchema.safeParse(
        await response.json().catch(() => null),
      );
      signal.throwIfAborted();
      if (candidate.success) {
        envelope = candidate.data;
        break;
      }
      if (
        !RETRYABLE_STATUSES.has(response.status) ||
        attempt === MAX_ATTEMPTS - 1
      ) {
        break;
      }
    } catch (error) {
      signal.throwIfAborted();
      // An abort is the caller changing their mind, not a failure to retry.
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      if (attempt === MAX_ATTEMPTS - 1) {
        return fallbackState(entryId, previous, "network_error");
      }
      await wait(RETRY_BASE_MS * 2 ** attempt);
      continue;
    }
    const retryAfter = response?.headers.get("Retry-After");
    const delay = retryAfter
      ? /^\d+$/.test(retryAfter)
        ? Number(retryAfter) * 1_000
        : Math.max(0, Date.parse(retryAfter) - Date.now())
      : RETRY_BASE_MS * 2 ** attempt;
    await wait(Number.isFinite(delay) ? delay : 20_000);
  }
  if (response === null) {
    return fallbackState(entryId, previous, "network_error");
  }

  if (!envelope) return fallbackState(entryId, previous, "invalid_response");

  if (envelope.status === "ready") {
    let state: PublicTeamState;
    try {
      const parsed = publicTeamStateSchema.parse(envelope.state);
      if (parsed.entryId !== entryId) {
        throw new TypeError("Cached public state does not match the Team ID");
      }
      state = parsed;
    } catch {
      return fallbackState(entryId, previous, "invalid_response");
    }
    try {
      if (dependencies.storage) {
        saveCachedPublicTeamState(dependencies.storage, entryId, state);
      }
    } catch {
      // Storage failure (quota, private mode, disabled) does not invalidate
      // the response. The current session still surfaces the fresh snapshot.
    }
    if (response.headers.get("X-FPL-Stale") === "1") {
      if (!usableUntilNextDeadline(state.event, new Date())) {
        return { status: "degraded", reason: "fpl_source_failed" };
      }
      return {
        status: "stale",
        state,
        reason:
          upstreamReason(response) ??
          (response.headers.get("X-FPL-Cache") === "hit"
            ? "cached_snapshot"
            : "fpl_unreachable"),
      };
    }
    return { status: "ready", state };
  }
  if (envelope.status === "degraded") {
    const reason =
      envelope.reason === "fpl_unreachable" ||
      envelope.reason === "fpl_source_failed"
        ? (upstreamReason(response) ?? envelope.reason)
        : envelope.reason;
    return previous?.entryId === entryId &&
      usableUntilNextDeadline(previous.event, new Date()) &&
      envelope.reason !== "source_contract_failed"
      ? { status: "stale", state: previous, reason }
      : { status: "degraded", reason };
  }
  return envelope.reason === "picks_unavailable"
    ? {
        status: "unavailable",
        reason: envelope.reason,
        event: envelope.event,
      }
    : { status: "unavailable", reason: envelope.reason };
}

function upstreamReason(response: Response): TeamDegradedReason | null {
  const reason = response.headers.get("X-FPL-Failure");
  if (reason === "refused" || reason === "challenged") return "fpl_refused";
  if (reason === "rate_limited") return "fpl_rate_limited";
  return null;
}

function requireEntryId(entryId: number): void {
  if (!Number.isInteger(entryId) || entryId < 1 || entryId > MAX_PUBLIC_ID) {
    throw new TypeError("Team ID is outside the supported range");
  }
}
