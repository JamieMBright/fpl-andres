import { z } from "zod";

import { dedupedFetch } from "./deduped-fetch";

/**
 * Completed seasons, fetched rather than bundled.
 *
 * The live bootstrap carries exactly one season of totals and rewrites them the
 * moment a new one starts, which makes "what did this look like in 2023-24" a
 * question the scatter could not answer. This is that answer, published from
 * the corpus, and it is a megabyte and a half — so it is downloaded when a
 * reader asks for a past season and never on first paint.
 *
 * Prices are the closing price of the window rather than today's. Comparing
 * what a player did in 2022-23 against what he costs now is a category error,
 * and the window slider makes it an easy one to commit.
 */

export const ANALYSIS_SEASONS_URL = "/analysis-seasons.json";

/** Gameweek, minutes, points, price in tenths. */
const eventRowSchema = z.tuple([
  z.number().int(),
  z.number().int(),
  z.number().int(),
  z.number().int(),
]);

const playerSchema = z
  .object({
    code: z.number().int().positive(),
    name: z.string(),
    position: z.string(),
    club: z.string(),
    byEvent: z.array(eventRowSchema),
    minutes: z.number().int(),
    appearances: z.number().int(),
    totalPoints: z.number().int(),
    goals: z.number().int(),
    assists: z.number().int(),
    bonus: z.number().int(),
    cleanSheets: z.number().int(),
    saves: z.number().int(),
    goalsConceded: z.number().int(),
    yellowCards: z.number().int(),
    redCards: z.number().int(),
    expectedGoals: z.number(),
    expectedAssists: z.number(),
    expectedGoalInvolvements: z.number(),
    defensiveContribution: z.number().int(),
    defensiveContributionPer90: z.number().nullable(),
    ceiling: z.number().nullable(),
    ceilingRatio: z.number().nullable(),
    priceTenths: z.number().int().nullable(),
  })
  .loose();

const artifactSchema = z.object({
  schemaVersion: z.number().int(),
  seasons: z.array(
    z.object({
      season: z.string(),
      events: z.array(z.number().int()),
      players: z.array(playerSchema),
    }),
  ),
});

export type ArchivedPlayer = z.infer<typeof playerSchema>;
export type ArchivedSeason = z.infer<typeof artifactSchema>["seasons"][number];

export async function fetchArchivedSeasons(
  fetchApi: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<ArchivedSeason[]> {
  const response = await dedupedFetch(
    ANALYSIS_SEASONS_URL,
    signal ? { signal } : undefined,
    fetchApi,
  );
  if (!response.ok) {
    throw new Error(`archive responded ${String(response.status)}`);
  }
  return artifactSchema.parse(await response.json()).seasons;
}

export interface WindowTotals {
  minutes: number;
  appearances: number;
  totalPoints: number;
  /** Closing price of the window, which is what he cost by the end of it. */
  priceTenths: number | null;
}

/**
 * Re-total a player over a gameweek window.
 *
 * Only the columns that can be summed from the per-gameweek rows are
 * recomputed. Expected goals and defensive contributions are published as
 * season totals, so a window narrower than the season leaves them alone rather
 * than pro-rating them, which would invent a number.
 */
export function totalsWithin(
  player: ArchivedPlayer,
  fromEvent: number,
  toEvent: number,
): WindowTotals {
  const inside = player.byEvent.filter(
    ([event]) => event >= fromEvent && event <= toEvent,
  );
  return {
    minutes: inside.reduce((total, [, minutes]) => total + minutes, 0),
    appearances: inside.length,
    totalPoints: inside.reduce((total, [, , points]) => total + points, 0),
    priceTenths: inside.at(-1)?.[3] ?? player.priceTenths,
  };
}
