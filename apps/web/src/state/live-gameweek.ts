import { dedupedFetch } from "./deduped-fetch";
import { retryingFetch } from "./retrying-fetch";

/**
 * What every player actually did in one gameweek.
 *
 * The plan can say what it expected. Only this says what happened, and until
 * the two sit beside each other a reader has no way to tell a good call from a
 * lucky one. FPL publishes it at `event/N/live/`, which names no manager and
 * takes no id -- the proxy allows it for that reason.
 *
 * Read as a whole gameweek rather than per player: it is one request for the
 * entire game, and a squad needs fifteen of the rows in it.
 */

export interface LivePlayer {
  minutes: number;
  goals: number;
  assists: number;
  cleanSheets: number;
  bonus: number;
  /** The raw action count. The bar it faces depends on the position. */
  defensiveActions: number;
  yellowCards: number;
  redCards: number;
  totalPoints: number;
}

export interface LiveGameweek {
  event: number;
  /** Keyed by this season's element id, which is what a pick carries. */
  players: ReadonlyMap<number, LivePlayer>;
}

export class LiveGameweekError extends Error {
  readonly reason: "unreachable" | "source_contract_failed";

  constructor(reason: LiveGameweekError["reason"], message: string) {
    super(message);
    this.name = "LiveGameweekError";
    this.reason = reason;
  }
}

function count(stats: Record<string, unknown>, key: string): number {
  const value = stats[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export function readLiveGameweek(
  event: number,
  payload: unknown,
): LiveGameweek {
  if (typeof payload !== "object" || payload === null) {
    throw new LiveGameweekError(
      "source_contract_failed",
      "the live gameweek was not an object",
    );
  }
  const elements = (payload as { elements?: unknown }).elements;
  if (!Array.isArray(elements)) {
    throw new LiveGameweekError(
      "source_contract_failed",
      "the live gameweek published no elements",
    );
  }
  const players = new Map<number, LivePlayer>();
  for (const row of elements) {
    if (typeof row !== "object" || row === null) continue;
    const id = (row as { id?: unknown }).id;
    const stats = (row as { stats?: unknown }).stats;
    if (typeof id !== "number" || typeof stats !== "object" || stats === null) {
      continue;
    }
    const line = stats as Record<string, unknown>;
    players.set(id, {
      minutes: count(line, "minutes"),
      goals: count(line, "goals_scored"),
      assists: count(line, "assists"),
      cleanSheets: count(line, "clean_sheets"),
      bonus: count(line, "bonus"),
      defensiveActions: count(line, "defensive_contribution"),
      yellowCards: count(line, "yellow_cards"),
      redCards: count(line, "red_cards"),
      totalPoints: count(line, "total_points"),
    });
  }
  if (players.size === 0) {
    throw new LiveGameweekError(
      "source_contract_failed",
      "the live gameweek named no players",
    );
  }
  return { event, players };
}

export async function fetchLiveGameweek(
  event: number,
  fetchApi: typeof fetch = retryingFetch(),
  signal?: AbortSignal,
): Promise<LiveGameweek> {
  let response: Response;
  try {
    response = await dedupedFetch(
      `/api/fpl/event/${String(event)}/live`,
      { headers: { Accept: "application/json" }, signal: signal ?? null },
      fetchApi,
    );
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new LiveGameweekError(
      "unreachable",
      "the gameweek's scores could not be requested",
    );
  }
  if (!response.ok) {
    throw new LiveGameweekError(
      "unreachable",
      `FPL returned ${String(response.status)} for the gameweek's scores`,
    );
  }
  return readLiveGameweek(event, await response.json());
}
