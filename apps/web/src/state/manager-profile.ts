import { z } from "zod";

/** One completed season on the official record. */
export const pastSeasonSchema = z
  .object({
    season_name: z.string().regex(/^\d{4}\/\d{2}$/),
    total_points: z.int().nonnegative(),
    rank: z.int().positive().nullable(),
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
};

export type Archetype =
  | "newcomer"
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
  medianRank: number;
  worstRank: number;
  archetype: Archetype;
  /** Negative means later seasons finished better than earlier ones. */
  trend: number | null;
};

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
  trend: number | null,
): Archetype {
  if (seasonsPlayed <= 2) return "newcomer";
  if (medianRank <= CONTENDER_MEDIAN) return "contender";
  if (bestRank <= SPIKE_BEST && medianRank >= SPIKE_MEDIAN) return "spiker";
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
    }));

  if (seasons.length === 0) return null;

  const ranks = seasons.map((entry) => entry.rank);
  const bestRank = Math.min(...ranks);
  const best = seasons.find((entry) => entry.rank === bestRank)!;
  const medianRank = median(ranks);
  const trend = careerTrend(ranks);

  return {
    seasons,
    seasonsPlayed: seasons.length,
    bestRank,
    bestSeason: best.season,
    medianRank,
    worstRank: Math.max(...ranks),
    archetype: classify(seasons.length, bestRank, medianRank, trend),
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

  switch (profile.archetype) {
    case "newcomer":
      return `${seasons} season${seasons === 1 ? "" : "s"} on record. Not enough to tell me anything about you yet, so I won't pretend otherwise. Your best is ${best}.`;
    case "contender":
      return `${seasons} seasons, and you keep finishing near the top. A median of ${profile.medianRank.toLocaleString("en-GB")} is not luck — that is somebody who does the work. You do not need me as much as most.`;
    case "spiker":
      return `You finished ${best} in ${profile.bestSeason} and have spent the rest of your career around ${profile.medianRank.toLocaleString("en-GB")}. One brilliant season is mostly variance. The interesting question is whether you can do it twice.`;
    case "climber":
      return `${seasons} seasons and the graph is pointing the right way. Your later years are comfortably better than your early ones. Whatever you changed, keep doing it.`;
    case "fader":
      return `${seasons} seasons, and I have to be honest: your recent form is worse than where you started. Best of ${best} says you can do it. Something has drifted since.`;
    case "ever-present":
      return `${seasons} seasons. You have been here longer than most of the players. Steady rather than spectacular, best of ${best} — you are the backbone of every mini-league in the country.`;
    default:
      return `${seasons} seasons, best of ${best}, typically around ${profile.medianRank.toLocaleString("en-GB")}. Solidly mid-table, which is where most of the eleven million live.`;
  }
}
