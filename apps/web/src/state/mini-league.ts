import { dedupedFetch } from "./deduped-fetch";
import { retryingFetch } from "./retrying-fetch";

/**
 * The squads you are actually racing, and what they are exposed to.
 *
 * Overall rank is a contest against a field whose ownership you can only know
 * as an average. A mini-league is a contest against a dozen squads you can
 * read one by one, and that changes which number decides a transfer. If nine
 * of your twelve rivals start a player, his hauling costs you nine places and
 * his blanking gains you nine, whatever his projection says. If none of them
 * own him, the same haul is worth the whole league.
 *
 * Read post-deadline only. FPL keeps a manager's picks private until the
 * gameweek starts and answers 404 before then, which is a rule this respects
 * rather than works around: there is no legitimate reading of a league before
 * its first deadline and the panel says so instead of inventing one.
 *
 * Every request goes through the same public proxy as the rest of the page and
 * nothing here is sent anywhere. The league is read in the browser and used in
 * the browser, because a Team ID is enumerable and a server's copy of who your
 * rivals are could have been typed by anybody.
 */

/**
 * How many of the standings to actually read.
 *
 * One request per rival, against a proxy with a shared upstream budget. The
 * people you are racing in a league of five hundred are the ones above you, so
 * reading the top of the table answers the question and reading all of it
 * would spend somebody else's rate limit to say the same thing.
 */
export const RIVAL_LIMIT = 24;

export interface RivalSquad {
  entryId: number;
  entryName: string;
  managerName: string;
  rank: number;
  totalPoints: number;
  /** All fifteen. */
  squad: readonly number[];
  /** The eleven that actually scored, captain included. */
  starters: readonly number[];
  captain: number | null;
}

export interface LeagueExposure {
  elementId: number;
  /** Share of the rivals read who started him. */
  ownedShare: number;
  /** Share who captained him. */
  captainedShare: number;
  /** Owned plus captained, because a captain scores twice. */
  effective: number;
  /** True where the reader starts him too. */
  mine: boolean;
}

export interface MiniLeague {
  leagueId: number;
  leagueName: string;
  event: number;
  rivals: readonly RivalSquad[];
  /** Entries whose picks could not be read. Named rather than dropped. */
  unavailable: readonly number[];
  /** Every player anybody in the league starts, most exposed first. */
  exposure: readonly LeagueExposure[];
}

export class MiniLeagueError extends Error {
  readonly reason:
    "unreachable" | "source_contract_failed" | "before_deadline" | "empty";

  constructor(reason: MiniLeagueError["reason"], message: string) {
    super(message);
    this.name = "MiniLeagueError";
    this.reason = reason;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown, fallback: string): string {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

interface StandingsRow {
  entryId: number;
  entryName: string;
  managerName: string;
  rank: number;
  totalPoints: number;
}

export interface Standings {
  leagueId: number;
  leagueName: string;
  rows: readonly StandingsRow[];
}

export function readStandings(leagueId: number, payload: unknown): Standings {
  const root = asRecord(payload);
  const league = asRecord(root?.league);
  const standings = asRecord(root?.standings);
  const results = standings?.results;
  if (!league || !Array.isArray(results)) {
    throw new MiniLeagueError(
      "source_contract_failed",
      "the league standings were not in the shape FPL publishes",
    );
  }

  const rows: StandingsRow[] = [];
  for (const entry of results) {
    const row = asRecord(entry);
    const entryId = asNumber(row?.entry);
    if (entryId === null) continue;
    rows.push({
      entryId,
      entryName: asString(row?.entry_name, `Team ${String(entryId)}`),
      managerName: asString(row?.player_name, "a manager"),
      rank: asNumber(row?.rank) ?? 0,
      totalPoints: asNumber(row?.total) ?? 0,
    });
  }
  if (rows.length === 0) {
    throw new MiniLeagueError("empty", "the league has no standings yet");
  }
  return {
    leagueId,
    leagueName: asString(league.name, `League ${String(leagueId)}`),
    rows,
  };
}

/** One rival's gameweek, from the picks endpoint. */
export function readPicks(
  row: StandingsRow,
  payload: unknown,
): Omit<RivalSquad, keyof StandingsRow> & StandingsRow {
  const picks = asRecord(payload)?.picks;
  if (!Array.isArray(picks)) {
    throw new MiniLeagueError(
      "source_contract_failed",
      "a rival's picks were not in the shape FPL publishes",
    );
  }

  const squad: number[] = [];
  const starters: number[] = [];
  let captain: number | null = null;
  for (const entry of picks) {
    const pick = asRecord(entry);
    const elementId = asNumber(pick?.element);
    if (elementId === null) continue;
    squad.push(elementId);
    const multiplier = asNumber(pick?.multiplier) ?? 0;
    if (multiplier > 0) starters.push(elementId);
    if (pick?.is_captain === true) captain = elementId;
  }
  if (squad.length === 0) {
    throw new MiniLeagueError(
      "source_contract_failed",
      "a rival's squad named no players",
    );
  }
  return { ...row, squad, starters, captain };
}

/**
 * What the league is exposed to, and what you are exposed to differently.
 *
 * Counted over starters rather than squads: a player on a rival's bench scores
 * nothing and threatens nothing. The captain is counted a second time because
 * he scores a second time, which is the whole reason a template captain is
 * safer than a template midfielder.
 */
export function exposureOf(
  rivals: readonly RivalSquad[],
  mine: readonly number[],
): LeagueExposure[] {
  const owned = new Set(mine);
  const started = new Map<number, number>();
  const captained = new Map<number, number>();
  for (const rival of rivals) {
    for (const elementId of new Set(rival.starters)) {
      started.set(elementId, (started.get(elementId) ?? 0) + 1);
    }
    if (rival.captain !== null) {
      captained.set(rival.captain, (captained.get(rival.captain) ?? 0) + 1);
    }
  }

  const count = rivals.length;
  const elements = new Set([...started.keys(), ...owned]);
  return [...elements]
    .map((elementId) => {
      const ownedShare =
        count === 0 ? 0 : (started.get(elementId) ?? 0) / count;
      const captainedShare =
        count === 0 ? 0 : (captained.get(elementId) ?? 0) / count;
      return {
        elementId,
        ownedShare,
        captainedShare,
        effective: ownedShare + captainedShare,
        mine: owned.has(elementId),
      };
    })
    .sort(
      (left, right) =>
        right.effective - left.effective || left.elementId - right.elementId,
    );
}

/** What the league owns and you do not. The names that cost you places. */
export function threatsIn(league: MiniLeague): LeagueExposure[] {
  return league.exposure.filter((row) => !row.mine && row.effective > 0);
}

/** What you own and the league does not. The names that gain you places. */
export function overlookedIn(league: MiniLeague): LeagueExposure[] {
  return league.exposure
    .filter((row) => row.mine)
    .slice()
    .sort(
      (left, right) =>
        left.effective - right.effective || left.elementId - right.elementId,
    );
}

export interface Standing {
  place: number;
  size: number;
  pointsBehindLeader: number;
  /** Null where nobody is close enough behind to be defending against. */
  pointsAheadOfNext: number | null;
}

/** Where the reader sits in the squads that were read. */
export function standingIn(
  league: MiniLeague,
  entryId: number,
): Standing | null {
  const ordered = [...league.rivals].sort(
    (left, right) => right.totalPoints - left.totalPoints,
  );
  const index = ordered.findIndex((rival) => rival.entryId === entryId);
  if (index < 0) return null;
  const me = ordered[index];
  const leader = ordered[0];
  const next = ordered[index + 1];
  if (!me || !leader) return null;
  return {
    place: index + 1,
    size: ordered.length,
    pointsBehindLeader: leader.totalPoints - me.totalPoints,
    pointsAheadOfNext: next ? me.totalPoints - next.totalPoints : null,
  };
}

async function readJson(
  path: string,
  fetchApi: typeof fetch,
  signal?: AbortSignal,
): Promise<unknown> {
  let response: Response;
  try {
    response = await dedupedFetch(
      path,
      { headers: { Accept: "application/json" }, signal: signal ?? null },
      fetchApi,
    );
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new MiniLeagueError("unreachable", "the league could not be reached");
  }
  if (response.status === 404) {
    throw new MiniLeagueError(
      "before_deadline",
      "FPL keeps a squad private until its deadline has passed, so there is nothing to read yet",
    );
  }
  if (!response.ok) {
    throw new MiniLeagueError(
      "unreachable",
      `FPL returned ${String(response.status)} for the league`,
    );
  }
  return response.json();
}

export async function fetchMiniLeague(
  leagueId: number,
  event: number,
  mine: readonly number[],
  fetchApi: typeof fetch = retryingFetch(),
  signal?: AbortSignal,
): Promise<MiniLeague> {
  const standings = readStandings(
    leagueId,
    await readJson(
      `/api/fpl/leagues-classic/${String(leagueId)}/standings`,
      fetchApi,
      signal,
    ),
  );

  const wanted = standings.rows.slice(0, RIVAL_LIMIT);
  const rivals: RivalSquad[] = [];
  const unavailable: number[] = [];
  for (const row of wanted) {
    try {
      const payload = await readJson(
        `/api/fpl/entry/${String(row.entryId)}/event/${String(event)}/picks`,
        fetchApi,
        signal,
      );
      rivals.push(readPicks(row, payload));
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError")
        throw error;
      // One unreadable squad is not a broken league. It is named on the panel
      // so a share is read against the squads it was actually measured over.
      unavailable.push(row.entryId);
    }
  }

  if (rivals.length === 0) {
    throw new MiniLeagueError(
      "before_deadline",
      "none of the league's squads are public yet, which is what FPL does before a deadline passes",
    );
  }

  return {
    leagueId,
    leagueName: standings.leagueName,
    event,
    rivals,
    unavailable,
    exposure: exposureOf(rivals, mine),
  };
}
