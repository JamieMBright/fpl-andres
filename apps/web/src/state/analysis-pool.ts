import { z } from "zod";

import {
  requireArtifactVersion,
  UNDERSTAT_SCHEMA_VERSION,
} from "./artifact-version";
import { dedupedFetch } from "./deduped-fetch";
import type { ScheduledFixture } from "./fixture-run";
import { readSeasonVintage, type SeasonVintage } from "./season-vintage";
import understatArtifact from "../data/understat.json";

requireArtifactVersion(
  "understat.json",
  understatArtifact,
  UNDERSTAT_SCHEMA_VERSION,
);

/**
 * The player pool the analysis page plots.
 *
 * Two sources with different vintages, kept apart rather than blended. The
 * record columns describe a completed season; price and ownership are what the
 * game charges and who owns him today. `season-vintage.ts` decides which season
 * the record belongs to and refuses when there is no answer.
 */

const elementSchema = z
  .object({
    id: z.number().int().positive(),
    code: z.number().int().positive(),
    web_name: z.string().min(1),
    element_type: z.number().int().min(1).max(5),
    team: z.number().int().positive(),
    now_cost: z.number().int().positive(),
    status: z.string().min(1),
    minutes: z.number().int().min(0),
    total_points: z.number().int(),
    bonus: z.number().int().min(0),
    selected_by_percent: z.coerce.number().min(0).max(100),
    expected_goals: z.coerce.number().min(0),
    expected_assists: z.coerce.number().min(0),
    expected_goal_involvements: z.coerce.number().min(0),
    ict_index: z.coerce.number().min(0),
    influence: z.coerce.number().min(0),
    creativity: z.coerce.number().min(0),
    threat: z.coerce.number().min(0),
    defensive_contribution: z.number().int().min(0),
    defensive_contribution_per_90: z.coerce.number().min(0),
  })
  .loose();

const analysisBootstrapSchema = z.object({
  elements: z.array(elementSchema),
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
        finished: z.boolean().optional(),
        deadline_time: z.string().optional(),
      })
      .loose(),
  ),
});

/**
 * Defensive contributions needed for the two points, by FPL position code.
 *
 * A goalkeeper has no route to them at all, which is why the map has a hole
 * rather than a zero: a keeper is not a defender who never gets there.
 */
export const DEFCON_THRESHOLD: Readonly<Record<string, number>> = {
  DEF: 10,
  MID: 12,
  FWD: 12,
};

export interface UnderstatRecord {
  shots: number;
  shotsPer90: number;
  expectedGoalsPerShot: number;
  expectedGoalsPer90: number;
  nonPenaltyExpectedGoals: number;
  penaltyExpectedGoals: number;
  penaltyShare: number;
  expectedGoalsAtRiskPer90: number;
}

export interface AnalysisPlayer {
  elementId: number;
  code: number;
  name: string;
  position: string;
  club: string;
  teamId: number;
  teamCode: number;
  available: boolean;
  priceTenths: number;
  /**
   * Null on an archived season. FPL publishes ownership as a live figure only,
   * so what a player was owned by in 2022-23 is not recoverable, and a zero
   * would read as "nobody owned him" rather than "nobody recorded it".
   */
  ownership: number | null;
  minutes: number;
  ninetiesPlayed: number;
  totalPoints: number;
  bonus: number;
  expectedGoals: number;
  expectedAssists: number;
  expectedGoalInvolvements: number;
  /** Null on an archived season: the corpus does not carry the ICT split. */
  ictIndex: number | null;
  influence: number | null;
  creativity: number | null;
  threat: number | null;
  /** Null before 2025-26: FPL did not record it, and zero would read as none. */
  defensiveContribution: number | null;
  defensiveContributionPer90: number | null;
  /**
   * Defensive contributions per 90 as a share of the bar he has to clear.
   *
   * One means he averages the threshold. It is deliberately not a hit rate:
   * averaging the bar and clearing it every week are different claims, and
   * season totals cannot tell them apart. `null` for goalkeepers.
   */
  defconBarRatio: number | null;
  understat: UnderstatRecord | null;
}

export interface AnalysisPool {
  players: AnalysisPlayer[];
  clubs: string[];
  positions: string[];
  vintage: SeasonVintage;
  /** Share of the plotted pool Understat could be joined to. */
  understatCoverage: number;
  understatSeason: string;
}

const understat = understatArtifact as {
  season: string;
  coverage: number;
  players: (UnderstatRecord & { code: number })[];
};

const understatByCode = new Map(
  understat.players.map(({ code, ...record }) => [code, record]),
);

export function buildAnalysisPool(payload: unknown): AnalysisPool {
  const bootstrap = analysisBootstrapSchema.parse(payload);
  const positions = new Map(
    bootstrap.element_types.map((type) => [type.id, type.singular_name_short]),
  );
  const clubs = new Map(bootstrap.teams.map((team) => [team.id, team]));

  const players = bootstrap.elements.flatMap<AnalysisPlayer>((element) => {
    const position = positions.get(element.element_type);
    const club = clubs.get(element.team);
    // Managers are a chip, not a footballer.
    if (!position || !club || element.element_type > 4) return [];

    const ninetiesPlayed = element.minutes / 90;
    const threshold = DEFCON_THRESHOLD[position];

    return [
      {
        elementId: element.id,
        code: element.code,
        name: element.web_name,
        position,
        club: club.short_name,
        teamId: element.team,
        teamCode: club.code,
        available: element.status === "a",
        priceTenths: element.now_cost,
        ownership: element.selected_by_percent,
        minutes: element.minutes,
        ninetiesPlayed,
        totalPoints: element.total_points,
        bonus: element.bonus,
        expectedGoals: element.expected_goals,
        expectedAssists: element.expected_assists,
        expectedGoalInvolvements: element.expected_goal_involvements,
        ictIndex: element.ict_index,
        influence: element.influence,
        creativity: element.creativity,
        threat: element.threat,
        defensiveContribution: element.defensive_contribution,
        defensiveContributionPer90: element.defensive_contribution_per_90,
        defconBarRatio:
          threshold === undefined
            ? null
            : element.defensive_contribution_per_90 / threshold,
        understat: understatByCode.get(element.code) ?? null,
      },
    ];
  });

  const busiest = players.reduce(
    (most, player) => Math.max(most, player.minutes),
    0,
  );

  const joined = players.filter((player) => player.understat !== null).length;

  return {
    players,
    clubs: [...new Set(players.map((player) => player.club))].sort(),
    positions: ["GKP", "DEF", "MID", "FWD"].filter((code) =>
      players.some((player) => player.position === code),
    ),
    vintage: readSeasonVintage(bootstrap.events, busiest),
    understatCoverage: players.length === 0 ? 0 : joined / players.length,
    understatSeason: understat.season,
  };
}

export type AnalysisFailure = "unreachable" | "source_contract_failed";

export class AnalysisPoolError extends Error {
  constructor(
    readonly reason: AnalysisFailure,
    message: string,
    /** What the proxy said, so a production failure can be diagnosed from the
     *  page rather than only from the platform logs. */
    readonly detail: string | null = null,
  ) {
    super(message);
    this.name = "AnalysisPoolError";
  }
}

export interface AnalysisData {
  pool: AnalysisPool;
  fixtures: ScheduledFixture[];
  clubCodeByTeamId: Map<number, number>;
}

export async function fetchAnalysisPool(
  fetchApi: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<AnalysisData> {
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
    throw new AnalysisPoolError(
      "unreachable",
      "the player list could not be requested",
    );
  }

  if (!bootstrap.ok) {
    const requestId = bootstrap.headers.get("x-fpl-andres-request-id");
    throw new AnalysisPoolError(
      "unreachable",
      `FPL returned ${bootstrap.status}`,
      `HTTP ${String(bootstrap.status)}${requestId ? ` \u00b7 ${requestId}` : ""}`,
    );
  }

  try {
    const payload = (await bootstrap.json()) as {
      teams: { id: number; code: number }[];
    };
    const pool = buildAnalysisPool(payload);
    return {
      pool,
      // A missing fixture list costs the fixture column on a pinned card and
      // nothing else.
      fixtures: fixtures.ok
        ? ((await fixtures.json()) as ScheduledFixture[])
        : [],
      clubCodeByTeamId: new Map(
        payload.teams.map((team) => [team.id, team.code]),
      ),
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new AnalysisPoolError(
      "source_contract_failed",
      "the player list did not match the expected shape",
    );
  }
}
