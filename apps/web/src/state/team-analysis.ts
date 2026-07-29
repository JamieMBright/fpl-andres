import {
  publicTeamResponseSchema,
  publicTeamStateSchema,
  type PublicTeamDegradedReason,
  type PublicTeamResponse,
  type PublicTeamState,
} from "@fpl-andres/contracts";

const STORAGE_PREFIX = "fpl-andres:public-team-state:v1";
const MAX_PUBLIC_ID = 4_294_967_295;

export type TeamAnalysisState =
  | { status: "idle" }
  | { status: "loading" }
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
  { type: "load" } | { type: "resolved"; state: TeamAnalysisState };

interface RefreshDependencies {
  fetchApi?: typeof fetch;
  storage: Storage;
  signal?: AbortSignal;
}

export const initialTeamAnalysisState: TeamAnalysisState = { status: "idle" };

export function reduceTeamAnalysis(
  _current: TeamAnalysisState,
  action: TeamAnalysisAction,
): TeamAnalysisState {
  return action.type === "load" ? { status: "loading" } : action.state;
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
  storage.setItem(teamPublicStateStorageKey(entryId), JSON.stringify(state));
  return state;
}

export function loadCachedPublicTeamState(
  storage: Storage,
  entryId: number,
): PublicTeamState | null {
  const key = teamPublicStateStorageKey(entryId);
  const serialized = storage.getItem(key);
  if (serialized === null) return null;

  try {
    const parsed = publicTeamStateSchema.safeParse(JSON.parse(serialized));
    if (!parsed.success || parsed.data.entryId !== entryId) {
      storage.removeItem(key);
      return null;
    }
    return parsed.data;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

export async function refreshTeamAnalysis(
  entryId: number,
  previous: PublicTeamState | null,
  dependencies: RefreshDependencies,
): Promise<TeamAnalysisState> {
  requireEntryId(entryId);
  const fetchApi = dependencies.fetchApi ?? fetch;
  let response: Response;
  try {
    response = await fetchApi(`/api/team/${entryId}`, {
      headers: { Accept: "application/json" },
      signal: dependencies.signal ?? new AbortController().signal,
    });
  } catch {
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
    try {
      const state = saveCachedPublicTeamState(
        dependencies.storage,
        entryId,
        envelope.state,
      );
      return { status: "ready", state };
    } catch {
      return previous
        ? { status: "stale", state: previous, reason: "invalid_response" }
        : { status: "error", reason: "invalid_response" };
    }
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
