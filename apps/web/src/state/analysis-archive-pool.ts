import type { AnalysisPlayer, AnalysisPool } from "./analysis-pool";
import { totalsWithin, type ArchivedSeason } from "./analysis-archive";

/**
 * A completed season, shaped like the live pool so the chart cannot tell them
 * apart.
 *
 * What the corpus does not carry is left null rather than zeroed. Ownership was
 * never recorded historically and the ICT split is not in the corpus, so a
 * player plotted on those axes is dropped and counted as unmeasured — which is
 * the truth — instead of appearing at the origin as though he had been measured
 * and found worthless.
 *
 * Rate statistics are the exception the window cannot fix: expected goals and
 * defensive contributions are published as season totals, so narrowing the
 * window re-sums points and minutes but leaves them whole. The control says so.
 */

/** Season totals that a narrower window would misreport if it pro-rated them. */
export const WHOLE_SEASON_METRICS = [
  "xG",
  "xA",
  "xGI",
  "xGIPer90",
  "defconTotal",
  "defconPer90",
  "defconBarRatio",
  "cbiPer90",
  "tacklesPer90",
  "recoveriesPer90",
];

/**
 * The first season FPL recorded defensive contributions.
 *
 * Earlier seasons are published as zero because the column exists in the
 * corpus and had nothing to put in it. Zero is a claim that a defender made no
 * tackles all year, so it is turned back into "not measured" here.
 */
const DEFCON_FROM_SEASON = "2025-26";

export function poolFromArchive(
  season: ArchivedSeason,
  fromEvent: number,
  toEvent: number,
  teamCodeByClub: ReadonlyMap<string, number>,
): AnalysisPool {
  const measuredDefcon = season.season >= DEFCON_FROM_SEASON;
  const players = season.players.map<AnalysisPlayer>((player) => {
    const window = totalsWithin(player, fromEvent, toEvent);
    const ninetiesPlayed = window.minutes / 90;
    return {
      // The archive is keyed on the code, which is the identity that survives a
      // season change. There is no element id to give.
      elementId: 0,
      code: player.code,
      name: player.name,
      position: player.position,
      club: player.club,
      teamId: 0,
      teamCode: teamCodeByClub.get(player.club) ?? 0,
      available: true,
      priceTenths: window.priceTenths ?? 0,
      ownership: null,
      minutes: window.minutes,
      ninetiesPlayed,
      totalPoints: window.totalPoints,
      bonus: player.bonus,
      expectedGoals: player.expectedGoals,
      expectedAssists: player.expectedAssists,
      expectedGoalInvolvements: player.expectedGoalInvolvements,
      ictIndex: null,
      influence: null,
      creativity: null,
      threat: null,
      defensiveContribution: measuredDefcon
        ? player.defensiveContribution
        : null,
      defensiveContributionPer90: measuredDefcon
        ? player.defensiveContributionPer90
        : null,
      defconBarRatio: null,
      clearancesBlocksInterceptions: measuredDefcon
        ? (player.clearancesBlocksInterceptions ?? null)
        : null,
      tackles: measuredDefcon ? (player.tackles ?? null) : null,
      recoveries: measuredDefcon ? (player.recoveries ?? null) : null,
      understat: null,
    };
  });

  const clubs = [...new Set(players.map((player) => player.club))].sort();
  const positions = [...new Set(players.map((player) => player.position))];

  return {
    players,
    clubs,
    positions,
    vintage: {
      season: season.season,
      state: "previous_season",
      completedGameweeks: season.events.length,
      // The window is already a minutes filter of a kind, so this is the whole-
      // season floor rather than one scaled to a part-played season.
      defaultMinimumMinutes: 450,
    },
    understatCoverage: 0,
    understatSeason: "",
  };
}
