/**
 * Which season the bootstrap season-total columns actually describe.
 *
 * `total_points`, `minutes`, the expected-goal columns and the ICT family are
 * published under fixed names that say nothing about their vintage. Between
 * seasons they still hold the completed season's totals: on 3 August 2026 the
 * live endpoint reported Haaland on 239 points from 2953 minutes with no
 * gameweek of 2026/27 played. Plotting that under a "this season" label is a
 * lie, and plotting it after FPL wipes the columns is a chart of zeroes.
 *
 * So the vintage is derived rather than assumed, and the page says which season
 * it is showing. When the first gameweek is scored this flips on its own.
 */

export interface VintageEvent {
  id: number;
  finished?: boolean | undefined;
  deadline_time?: string | undefined;
}

export type VintageState = "previous_season" | "live_season" | "unavailable";

export interface SeasonVintage {
  state: VintageState;
  /** The season the totals describe, `null` when there is nothing to describe. */
  season: string | null;
  completedGameweeks: number;
  /**
   * Minutes below which a player is noise rather than a small sample. Scales
   * with the season so the same idea survives from August to May.
   */
  defaultMinimumMinutes: number;
}

// Five full matches. Below this a per-90 rate is dominated by which fixtures a
// player happened to catch, and the chart is comparing a cameo to a season.
const FULL_SEASON_MINIMUM_MINUTES = 450;

// A completed season leaves regulars on thousands of minutes. If the busiest
// player in the game is under this, the columns have been wiped and there is no
// record to show yet.
const WIPED_POOL_MINUTES = 450;

const MINUTES_PER_MATCH = 90;

/**
 * @param events `bootstrap-static` events, in any order.
 * @param busiestPlayerMinutes the largest `minutes` value in the player pool.
 */
export function readSeasonVintage(
  events: readonly VintageEvent[],
  busiestPlayerMinutes: number,
): SeasonVintage {
  const ordered = [...events].sort((left, right) => left.id - right.id);
  const first = ordered.at(0);
  if (!first?.deadline_time) {
    return unavailable(0);
  }

  const startYear = new Date(first.deadline_time).getUTCFullYear();
  if (!Number.isFinite(startYear)) {
    return unavailable(0);
  }

  const completedGameweeks = ordered.filter((event) => event.finished).length;

  if (completedGameweeks > 0) {
    return {
      state: "live_season",
      season: label(startYear),
      completedGameweeks,
      defaultMinimumMinutes: scaledMinimum(completedGameweeks),
    };
  }

  if (busiestPlayerMinutes < WIPED_POOL_MINUTES) {
    return unavailable(0);
  }

  return {
    state: "previous_season",
    season: label(startYear - 1),
    completedGameweeks: 0,
    defaultMinimumMinutes: FULL_SEASON_MINIMUM_MINUTES,
  };
}

/** `2026` becomes `2026-27`. */
function label(startYear: number): string {
  return `${startYear}-${String((startYear + 1) % 100).padStart(2, "0")}`;
}

/** Half the minutes a player could have played, capped at the season figure. */
function scaledMinimum(completedGameweeks: number): number {
  return Math.min(
    FULL_SEASON_MINIMUM_MINUTES,
    Math.round((completedGameweeks * MINUTES_PER_MATCH) / 2),
  );
}

function unavailable(completedGameweeks: number): SeasonVintage {
  return {
    state: "unavailable",
    season: null,
    completedGameweeks,
    defaultMinimumMinutes: FULL_SEASON_MINIMUM_MINUTES,
  };
}
