import { z } from "zod";

/** One completed season on the official record. */
export const pastSeasonSchema = z
  .object({
    season_name: z.string().regex(/^\d{4}\/\d{2}$/),
    total_points: z.int().nonnegative(),
    rank: z.int().positive().nullable(),
    // FPL publishes this to one decimal, which is the only figure that
    // compares across a player base that has grown roughly fivefold.
    rank_percentage: z.number().min(0).max(100).nullable().optional(),
  })
  .loose();

export const entryHistorySchema = z
  .object({
    past: z.array(pastSeasonSchema),
  })
  .loose();

export type PastSeason = {
  season: string;
  points: number;
  rank: number;
  /** Finishing position as a share of the field. Lower is better. */
  percentile: number | null;
};

export type Archetype =
  | "newcomer"
  | "elite"
  | "contender"
  | "spiker"
  | "climber"
  | "fader"
  | "ever-present"
  | "regular";

export type ManagerProfile = {
  seasons: PastSeason[];
  seasonsPlayed: number;
  bestRank: number;
  bestSeason: string;
  /** The best finish as a share of the field, where FPL published one. */
  bestPercentile: number | null;
  medianRank: number;
  medianPercentile: number | null;
  worstRank: number;
  archetype: Archetype;
  /** Seasons finished inside the top one percent of the field. */
  standoutSeasons: number;
  /** Negative means later seasons finished better than earlier ones. */
  trend: number | null;
};

// Percentiles, because rank is not comparable across a field that has grown
// roughly fivefold. All of these are shares of the field, lower being better.
const ELITE_MEDIAN = 5;
const CONTENDER_MEDIAN_PERCENT = 15;
const STANDOUT = 1;
// A one-off means exactly that: a single outstanding year against a career
// spent well down the field. Two of them is a pattern, not variance.
const SPIKE_MEDIAN_PERCENT = 35;

const CONTENDER_MEDIAN = 100_000;
const SPIKE_BEST = 50_000;
const SPIKE_MEDIAN = 500_000;
const EVER_PRESENT_SEASONS = 8;
// A career has to move by more than this share to count as a direction rather
// than noise. Rank swings enormously season to season.
const TREND_THRESHOLD = 0.35;

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? Math.round((sorted[middle - 1]! + sorted[middle]!) / 2)
    : sorted[middle]!;
}

/** Unrounded, because a percentile of 0.3 must not become zero. */
function medianOf(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1]! + sorted[middle]!) / 2
    : sorted[middle]!;
}

function mean(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

/** Share by which the later half of a career improved on the earlier half. */
function careerTrend(ranks: number[]): number | null {
  if (ranks.length < 4) return null;
  const split = Math.floor(ranks.length / 2);
  const early = mean(ranks.slice(0, split));
  const late = mean(ranks.slice(-split));
  if (early <= 0) return null;
  return (late - early) / early;
}

function classify(
  seasonsPlayed: number,
  bestRank: number,
  medianRank: number,
  medianPercentile: number | null,
  standoutSeasons: number,
  trend: number | null,
): Archetype {
  if (seasonsPlayed <= 2) return "newcomer";
  if (medianPercentile !== null) {
    if (medianPercentile <= ELITE_MEDIAN) return "elite";
    if (medianPercentile <= CONTENDER_MEDIAN_PERCENT) return "contender";
    // One outstanding year is variance. Several is a manager having a bad run.
    if (standoutSeasons === 1 && medianPercentile >= SPIKE_MEDIAN_PERCENT) {
      return "spiker";
    }
  } else {
    if (medianRank <= CONTENDER_MEDIAN) return "contender";
    if (bestRank <= SPIKE_BEST && medianRank >= SPIKE_MEDIAN) return "spiker";
  }
  if (trend !== null && trend <= -TREND_THRESHOLD) return "climber";
  if (trend !== null && trend >= TREND_THRESHOLD) return "fader";
  if (seasonsPlayed >= EVER_PRESENT_SEASONS) return "ever-present";
  return "regular";
}

/**
 * Read a manager's record out of an `entry/{id}/history/` payload.
 *
 * Seasons without a rank were never completed, so they are dropped rather than
 * given a placeholder that would drag every summary toward the middle.
 */
export function readManagerProfile(payload: unknown): ManagerProfile | null {
  const parsed = entryHistorySchema.safeParse(payload);
  if (!parsed.success) return null;

  const seasons: PastSeason[] = parsed.data.past
    .filter((entry) => entry.rank !== null && entry.rank > 0)
    .map((entry) => ({
      season: entry.season_name,
      points: entry.total_points,
      rank: entry.rank as number,
      percentile: entry.rank_percentage ?? null,
    }));

  if (seasons.length === 0) return null;

  const ranks = seasons.map((entry) => entry.rank);
  const percentiles = seasons
    .map((entry) => entry.percentile)
    .filter((value): value is number => value !== null);
  const bestRank = Math.min(...ranks);
  const best = seasons.find((entry) => entry.rank === bestRank)!;
  const medianRank = median(ranks);
  const medianPercentile =
    percentiles.length === seasons.length ? medianOf(percentiles) : null;
  const standoutSeasons = percentiles.filter(
    (value) => value <= STANDOUT,
  ).length;
  const trend = careerTrend(ranks);

  return {
    seasons,
    seasonsPlayed: seasons.length,
    bestRank,
    bestSeason: best.season,
    bestPercentile: best.percentile,
    medianRank,
    medianPercentile,
    worstRank: Math.max(...ranks),
    archetype: classify(
      seasons.length,
      bestRank,
      medianRank,
      medianPercentile,
      standoutSeasons,
      trend,
    ),
    standoutSeasons,
    trend,
  };
}

/**
 * Andres on the record. Rule-based rather than generated, so the same history
 * always produces the same read and every claim traces to a number above it.
 */
export function commentary(profile: ManagerProfile): string {
  const best = profile.bestRank.toLocaleString("en-GB");
  const seasons = profile.seasonsPlayed;
  const bestFinish =
    profile.bestPercentile === null
      ? best
      : `top ${share(profile.bestPercentile)}`;
  const typical =
    profile.medianPercentile === null
      ? profile.medianRank.toLocaleString("en-GB")
      : `top ${share(profile.medianPercentile)}`;
  const standout =
    profile.standoutSeasons > 1
      ? ` You have finished in the top one percent ${profile.standoutSeasons} times, which almost nobody does.`
      : "";

  switch (profile.archetype) {
    case "newcomer":
      return `${seasons} season${seasons === 1 ? "" : "s"} on record. Not enough to tell me anything about you yet, so I won't pretend otherwise. Your best is ${bestFinish}.`;
    case "elite":
      return `${seasons} seasons and a typical finish of ${typical}. That is not variance, that is somebody who knows what they are doing.${standout} Honestly, you may be able to teach me more than I can teach you.`;
    case "contender":
      return `${seasons} seasons, typically ${typical}, best of ${bestFinish}.${standout} Consistently in the upper reaches of a field of millions. You do the work.`;
    case "spiker":
      return `${bestFinish} in ${profile.bestSeason}, against a career typically around ${typical}. One outstanding season on its own is mostly variance — the interesting question is whether the process behind it can be repeated.`;
    case "climber":
      return `${seasons} seasons and the graph is pointing the right way. Your later years are comfortably better than your early ones.${standout} Whatever you changed, keep doing it.`;
    case "fader":
      return `${seasons} seasons, and I have to be honest: your recent finishes are worse than where you started. A best of ${bestFinish} says the ability is there.${standout} Something has drifted since.`;
    case "ever-present":
      return `${seasons} seasons. You have been here longer than most of the players, typically finishing ${typical}, best of ${bestFinish}.${standout} You are the backbone of every mini-league in the country.`;
    default:
      return `${seasons} seasons, best of ${bestFinish}, typically ${typical}.${standout} Comfortably inside the half of the game that takes it seriously.`;
  }
}

/** One decimal below ten percent, whole numbers above it. */
function share(percentile: number): string {
  return percentile < 10
    ? `${percentile.toFixed(1)}%`
    : `${Math.round(percentile)}%`;
}
