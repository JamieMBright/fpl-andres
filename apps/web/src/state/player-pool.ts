import { z } from "zod";

import { dedupedFetch } from "./deduped-fetch";
import {
  freshnessOf,
  LastGood,
  leastFresh,
  LIVE,
  type Freshness,
} from "./freshness";
import {
  rateFixtureRun,
  type FixtureRun,
  type ScheduledFixture,
} from "./fixture-run";
import { fetchGlobalFplFallback } from "./global-fpl-fallback";
import { retryingFetch } from "./retrying-fetch";
import { projectionFor, type PlayerProjection } from "./squad-projection";

/**
 * The 2026/27 player list, joined to last season's record.
 *
 * FPL publishes the new season's players, clubs and prices weeks before the
 * first deadline, which is exactly when a manager wants to know what a player
 * is worth. The prices are this season's; the record is last season's. Those
 * are two different facts and the join keeps them distinguishable rather than
 * blending them into a single invented number.
 */
const bootstrapSchema = z.object({
  elements: z.array(
    z
      .object({
        id: z.number().int().positive(),
        code: z.number().int().positive(),
        web_name: z.string().min(1),
        element_type: z.number().int().min(1).max(5),
        team: z.number().int().positive(),
        now_cost: z.number().int().positive(),
        status: z.string().min(1),
        squad_number: z.number().int().positive().max(99).nullable().optional(),
        // FPL's own live season record: what he has actually scored so far
        // this season, and in the gameweek just gone. Both start at zero
        // before a ball is kicked, which is a fact, not a missing one.
        // FPL totals can be negative after deductions (for example a red card),
        // so zero is not a valid source-contract floor here.
        total_points: z.number().int().optional(),
        event_points: z.number().int().optional(),
        // Ownership and minutes, for filtering rather than ranking: a
        // differential pick and a nailed-on starter are different questions
        // from "who returns the most points".
        selected_by_percent: z.coerce.number().min(0).max(100).optional(),
        minutes: z.number().int().min(0).optional(),
        // FPL's own advanced-stat and market fields. Optional because a
        // passthrough response is trusted for its shape, not fabricated when
        // a field is absent: a dash on screen beats an invented zero.
        expected_goals: z.coerce.number().min(0).optional(),
        expected_assists: z.coerce.number().min(0).optional(),
        expected_goal_involvements: z.coerce.number().min(0).optional(),
        expected_goals_conceded: z.coerce.number().min(0).optional(),
        defensive_contribution: z.number().int().min(0).optional(),
        transfers_in_event: z.number().int().min(0).optional(),
        transfers_out_event: z.number().int().min(0).optional(),
        cost_change_event: z.number().int().optional(),
      })
      .loose(),
  ),
  element_types: z.array(
    z
      .object({
        id: z.number().int().min(1).max(5),
        singular_name_short: z.string().min(1),
      })
      .loose(),
  ),
  teams: z.array(
    z
      .object({
        id: z.number().int().positive(),
        code: z.number().int().positive(),
        short_name: z.string().min(1),
        name: z.string().min(1),
      })
      .loose(),
  ),
  events: z.array(
    z
      .object({
        id: z.number().int().min(1).max(38),
        deadline_time: z.string(),
        is_current: z.boolean().optional(),
      })
      .loose(),
  ),
});

const historyRowSchema = z
  .object({
    event: z.number().int().min(1).max(38).nullable().optional(),
    round: z.number().int().min(1).max(38).optional(),
    fixture: z.number().int().positive(),
    kickoff_time: z.string().nullable().optional(),
    minutes: z.number().int().min(0),
    total_points: z.number().int(),
    goals_scored: z.number().int().min(0),
    assists: z.number().int().min(0),
    clean_sheets: z.number().int().min(0),
    goals_conceded: z.number().int().min(0),
    own_goals: z.number().int().min(0),
    penalties_saved: z.number().int().min(0),
    penalties_missed: z.number().int().min(0),
    yellow_cards: z.number().int().min(0),
    red_cards: z.number().int().min(0),
    saves: z.number().int().min(0),
    bonus: z.number().int().min(0),
    bps: z.number().int(),
    influence: z.coerce.number().min(0).optional(),
    creativity: z.coerce.number().min(0).optional(),
    threat: z.coerce.number().min(0).optional(),
    ict_index: z.coerce.number().min(0).optional(),
    starts: z.number().int().min(0).optional(),
    expected_goals: z.coerce.number().min(0).optional(),
    expected_assists: z.coerce.number().min(0).optional(),
    expected_goal_involvements: z.coerce.number().min(0).optional(),
    expected_goals_conceded: z.coerce.number().min(0).optional(),
    defensive_contribution: z.number().int().min(0).optional(),
  })
  .loose()
  .refine((row) => row.event !== undefined || row.round !== undefined, {
    message: "history row publishes neither event nor round",
  });

const elementSummarySchema = z.object({ history: z.array(historyRowSchema) });

const fixtureSchema = z.array(
  z
    .object({
      event: z.number().int().min(1).max(38).nullable(),
      team_h: z.number().int().positive(),
      team_a: z.number().int().positive(),
    })
    .loose(),
);

export interface PoolPlayer {
  elementId: number;
  code: number;
  name: string;
  position: string;
  club: string;
  teamId: number;
  /** The number on his back, where FPL has published one. */
  squadNumber: number | null;
  priceTenths: number;
  /** FPL's own availability flag: "a" is available, anything else is not. */
  available: boolean;
  /** Last season's record, or null where there is none. */
  record: PlayerProjection | null;
  /** Last season's points per match divided by this season's price. */
  perMillion: number | null;
  /** What he has actually scored this season so far, live from FPL. */
  seasonPoints: number;
  /** His points in the gameweek just gone, or null before any have been played. */
  lastGameweekPoints: number | null;
  /** Expected goals, assists, goal involvements and goals conceded this season, live from FPL. Null before FPL publishes them. */
  expectedGoals: number | null;
  expectedAssists: number | null;
  expectedGoalInvolvements: number | null;
  expectedGoalsConceded: number | null;
  /** Defensive-contribution points scored so far this season, null before FPL publishes it. */
  defensiveContribution: number | null;
  /** Transfers in/out FPL counted in the gameweek named by `PlayerPool.currentEvent`. */
  transfersInEvent: number | null;
  transfersOutEvent: number | null;
  /** Price move, in tenths of a million, since the gameweek named by `PlayerPool.currentEvent` started. */
  priceChangeEvent: number | null;
  /** Share of managers who own him, live from FPL. Null before FPL publishes it. */
  ownedPercent: number | null;
  /** Minutes played so far this season, live from FPL. */
  minutesPlayed: number | null;
}

export interface PlayerPool {
  players: PoolPlayer[];
  clubs: string[];
  positions: string[];
  firstDeadline: string | null;
  /** The gameweek FPL calls current, for labelling transfer/price-change columns. Null if FPL names none. */
  currentEvent: number | null;
  /** This season's club ids mapped to the code that survives a season change. */
  clubCodeByTeamId: Map<number, number>;
  fixtures: ScheduledFixture[];
  /**
   * How current this is. Never omitted, because a pool built from a retained
   * copy renders identically to a live one and a manager acts on the prices.
   */
  freshness: Freshness;
}

export function buildPlayerPool(
  payload: unknown,
  fixturePayload: unknown = [],
  freshness: Freshness = LIVE,
): PlayerPool {
  const bootstrap = bootstrapSchema.parse(payload);
  const fixtures = fixtureSchema.parse(fixturePayload);
  const positions = new Map(
    bootstrap.element_types.map((type) => [type.id, type.singular_name_short]),
  );
  const clubs = new Map(
    bootstrap.teams.map((team) => [team.id, team.short_name]),
  );

  const players = bootstrap.elements.flatMap<PoolPlayer>((element) => {
    const position = positions.get(element.element_type);
    const club = clubs.get(element.team);
    // Managers are element_type 5 and are a chip, not a footballer.
    if (!position || !club || element.element_type > 4) return [];

    const record = projectionFor(element.code);
    return [
      {
        elementId: element.id,
        code: element.code,
        name: element.web_name,
        position,
        club,
        teamId: element.team,
        squadNumber: element.squad_number ?? null,
        priceTenths: element.now_cost,
        available: element.status === "a",
        record,
        perMillion: record
          ? round(record.expectedPoints / (element.now_cost / 10))
          : null,
        seasonPoints: element.total_points ?? 0,
        lastGameweekPoints: element.event_points ?? null,
        expectedGoals: element.expected_goals ?? null,
        expectedAssists: element.expected_assists ?? null,
        expectedGoalInvolvements: element.expected_goal_involvements ?? null,
        expectedGoalsConceded: element.expected_goals_conceded ?? null,
        defensiveContribution: element.defensive_contribution ?? null,
        transfersInEvent: element.transfers_in_event ?? null,
        transfersOutEvent: element.transfers_out_event ?? null,
        priceChangeEvent: element.cost_change_event ?? null,
        ownedPercent: element.selected_by_percent ?? null,
        minutesPlayed: element.minutes ?? null,
      },
    ];
  });

  players.sort(
    (left, right) =>
      (right.record?.expectedPoints ?? -1) -
      (left.record?.expectedPoints ?? -1),
  );

  return {
    players,
    clubs: [...new Set(players.map((player) => player.club))].sort(),
    positions: ["GKP", "DEF", "MID", "FWD"].filter((code) =>
      players.some((player) => player.position === code),
    ),
    firstDeadline:
      [...bootstrap.events].sort((left, right) => left.id - right.id).at(0)
        ?.deadline_time ?? null,
    currentEvent:
      bootstrap.events.find((event) => event.is_current)?.id ?? null,
    clubCodeByTeamId: new Map(
      bootstrap.teams.map((team) => [team.id, team.code]),
    ),
    fixtures,
    freshness,
  };
}

export type PoolFailure = "unreachable" | "source_contract_failed";

export class PlayerPoolError extends Error {
  constructor(
    readonly reason: PoolFailure,
    message: string,
  ) {
    super(message);
    this.name = "PlayerPoolError";
  }
}

/**
 * The last pool that was built successfully, for the length of the tab.
 *
 * The proxy's retained copy dies with its serverless instance, so a cold start
 * during an outage still leaves the browser with nothing from that direction.
 * This is the second line: a reader who already has the list on screen does not
 * lose it because a later request failed.
 */
const lastGood = new LastGood<PlayerPool>();

/** Test seam. Production code has no reason to call this. */
export function forgetLastGoodPool(): void {
  lastGood.forget();
}

export interface LivePlayerDetail {
  seasonPoints: number;
  lastGameweekPoints: number | null;
  expectedGoals: number | null;
  expectedAssists: number | null;
  expectedGoalInvolvements: number | null;
  expectedGoalsConceded: number | null;
  defensiveContribution: number | null;
  minutesPlayed: number | null;
  ownedPercent: number | null;
  run: FixtureRun | undefined;
  history: LivePlayerHistory[] | null;
}

export interface LivePlayerHistory {
  event: number;
  fixture: number;
  kickoffTime: string | null;
  minutes: number;
  totalPoints: number;
  goals: number;
  assists: number;
  cleanSheets: number;
  goalsConceded: number;
  ownGoals: number;
  penaltiesSaved: number;
  penaltiesMissed: number;
  yellowCards: number;
  redCards: number;
  saves: number;
  bonus: number;
  bps: number;
  influence: number | null;
  creativity: number | null;
  threat: number | null;
  ictIndex: number | null;
  starts: number | null;
  expectedGoals: number | null;
  expectedAssists: number | null;
  expectedGoalInvolvements: number | null;
  expectedGoalsConceded: number | null;
  defensiveContribution: number | null;
}

function liveDetailIn(pool: PlayerPool, code: number): LivePlayerDetail | null {
  const player = pool.players.find((candidate) => candidate.code === code);
  return player
    ? {
        seasonPoints: player.seasonPoints,
        lastGameweekPoints: player.lastGameweekPoints,
        expectedGoals: player.expectedGoals,
        expectedAssists: player.expectedAssists,
        expectedGoalInvolvements: player.expectedGoalInvolvements,
        expectedGoalsConceded: player.expectedGoalsConceded,
        defensiveContribution: player.defensiveContribution,
        minutesPlayed: player.minutesPlayed,
        ownedPercent: player.ownedPercent,
        run: rateFixtureRun(
          pool.clubCodeByTeamId,
          pool.fixtures.filter(
            (fixture) =>
              pool.currentEvent === null ||
              (fixture.event !== null && fixture.event > pool.currentEvent),
          ),
          player.teamId,
          player.position,
          5,
        ),
        history: null,
      }
    : null;
}

function historyFrom(payload: unknown): LivePlayerHistory[] {
  return elementSummarySchema.parse(payload).history.map((row) => {
    const event = row.event ?? row.round;
    if (event === undefined) {
      throw new TypeError("history row publishes no gameweek");
    }
    return {
      event,
      fixture: row.fixture,
      kickoffTime: row.kickoff_time ?? null,
      minutes: row.minutes,
      totalPoints: row.total_points,
      goals: row.goals_scored,
      assists: row.assists,
      cleanSheets: row.clean_sheets,
      goalsConceded: row.goals_conceded,
      ownGoals: row.own_goals,
      penaltiesSaved: row.penalties_saved,
      penaltiesMissed: row.penalties_missed,
      yellowCards: row.yellow_cards,
      redCards: row.red_cards,
      saves: row.saves,
      bonus: row.bonus,
      bps: row.bps,
      influence: row.influence ?? null,
      creativity: row.creativity ?? null,
      threat: row.threat ?? null,
      ictIndex: row.ict_index ?? null,
      starts: row.starts ?? null,
      expectedGoals: row.expected_goals ?? null,
      expectedAssists: row.expected_assists ?? null,
      expectedGoalInvolvements: row.expected_goal_involvements ?? null,
      expectedGoalsConceded: row.expected_goals_conceded ?? null,
      defensiveContribution: row.defensive_contribution ?? null,
    };
  });
}

async function fetchPlayerHistory(
  elementId: number,
  fetchApi: typeof fetch,
): Promise<LivePlayerHistory[] | null> {
  const response = await dedupedFetch(
    `/api/fpl/element-summary/${String(elementId)}`,
    { headers: { Accept: "application/json" } },
    fetchApi,
  );
  if (!response.ok) return null;
  return historyFrom(await response.json());
}

/** Current FPL evidence for a projection-only card such as Top Picks. */
export async function fetchLivePlayerDetail(
  code: number,
  fetchApi: typeof fetch = retryingFetch(),
): Promise<LivePlayerDetail | null> {
  const held = lastGood.recall();
  const pool = held?.value ?? (await fetchPlayerPool(fetchApi));
  const detail = liveDetailIn(pool, code);
  if (detail === null) return null;
  const player = pool.players.find((candidate) => candidate.code === code);
  if (!player) return detail;
  try {
    return {
      ...detail,
      history: await fetchPlayerHistory(player.elementId, fetchApi),
    };
  } catch {
    return detail;
  }
}

export async function fetchPlayerPool(
  fetchApi: typeof fetch = retryingFetch(),
  signal?: AbortSignal,
): Promise<PlayerPool> {
  const init = {
    headers: { Accept: "application/json" },
    signal: signal ?? null,
  };
  let bootstrap: Response;
  let fixtures: Response;
  try {
    [bootstrap, fixtures] = await Promise.all([
      dedupedFetch("/api/fpl/bootstrap-static", init, fetchApi),
      dedupedFetch("/api/fpl/fixtures", init, fetchApi),
    ]);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    return fallbackOrFail(
      "the player list could not be requested",
      fetchApi,
      signal,
    );
  }
  if (!bootstrap.ok) {
    return fallbackOrFail(
      `FPL returned ${String(bootstrap.status)}`,
      fetchApi,
      signal,
    );
  }
  try {
    // A missing fixture list costs the run column and nothing else, so it is
    // not worth failing the whole page over.
    const pool = buildPlayerPool(
      await bootstrap.json(),
      fixtures.ok ? await fixtures.json() : [],
      leastFresh([
        freshnessOf(bootstrap),
        ...(fixtures.ok ? [freshnessOf(fixtures)] : []),
      ]),
    );
    // Only a live pool is worth remembering. Retaining a stale one would let
    // its age reset every time it was served back to itself.
    if (!pool.freshness.stale) lastGood.remember(pool);
    return pool;
  } catch {
    // A shape this code cannot read is not an outage, and an older pool would
    // hide a contract change that is this project's to fix.
    throw new PlayerPoolError(
      "source_contract_failed",
      "the player list did not match the expected shape",
    );
  }
}

/**
 * An older list, labelled, beats an empty page. Nothing at all is still an
 * error -- the reader is told, rather than shown a blank table.
 */
async function fallbackOrFail(
  message: string,
  fetchApi: typeof fetch,
  signal?: AbortSignal,
): Promise<PlayerPool> {
  const held = lastGood.recall();
  if (held) return { ...held.value, freshness: held.freshness };
  try {
    const fallback = await fetchGlobalFplFallback(fetchApi, signal);
    return buildPlayerPool(
      fallback.bootstrap,
      fallback.fixtures,
      fallback.freshness,
    );
  } catch (error) {
    if (error instanceof z.ZodError) {
      throw new PlayerPoolError(
        "source_contract_failed",
        "the shipped player list did not match the expected shape",
      );
    }
    throw new PlayerPoolError("unreachable", message);
  }
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}
