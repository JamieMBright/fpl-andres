import {
  EVENT_INDEX,
  SEASON_EVENTS,
  SEASON_PLAYERS,
  pointsAtEvent,
} from "./season-solver";

/**
 * Expected points added up over the next few gameweeks.
 *
 * A transfer is not made for Saturday. It is made for the run the player is
 * about to have, and the two answers differ: a striker with one soft fixture
 * and then City, Arsenal and Liverpool outranks a steadier one on a single
 * week and is the worse buy on any horizon that reaches the hard part.
 *
 * A plain sum, not the decayed lookahead the solver optimises against. The
 * solver discounts later weeks because it will get another transfer before
 * them; a reader choosing between two players over nine gameweeks is asking
 * what those nine gameweeks are worth, and a discount would answer a different
 * question quietly.
 *
 * Doubles count twice and blanks count nothing, because `pointsAtEvent` sums
 * over the gameweek's fixtures and a blank has none. That is the whole reason
 * this is worth showing next to a per-match figure.
 */

/** The horizons offered. Odd numbers, so a median fixture exists in each. */
export const HORIZONS = [1, 3, 5, 7, 9] as const;

export type Horizon = (typeof HORIZONS)[number];

export const DEFAULT_HORIZON: Horizon = 5;

/** The gameweek the horizon counts from, being the first one still to be played. */
function firstEvent(from?: number): number | null {
  if (from !== undefined) return EVENT_INDEX.has(from) ? from : null;
  return SEASON_EVENTS[0] ?? null;
}

/**
 * One player's expected points over `weeks` gameweeks, or null past the end.
 *
 * Null rather than a short sum: a player whose horizon runs off the end of the
 * season has fewer gameweeks in his total than everyone else, and sorting a
 * table on that ranks him last for a reason that is nothing to do with him.
 */
export function horizonPoints(
  code: number,
  weeks: Horizon,
  from?: number,
): number | null {
  const start = firstEvent(from);
  if (start === null) return null;
  const index = EVENT_INDEX.get(start);
  if (index === undefined || index + weeks > SEASON_EVENTS.length) return null;

  const player = SEASON_PLAYERS.find((entry) => entry.code === code);
  if (!player) return null;

  let total = 0;
  for (let ahead = 0; ahead < weeks; ahead += 1) {
    total += pointsAtEvent(player, index + ahead);
  }
  return total;
}

/** The same for every player at once, which is what a sortable table needs. */
export function horizonPointsByCode(
  weeks: Horizon,
  from?: number,
): Map<number, number> {
  const start = firstEvent(from);
  const index = start === null ? undefined : EVENT_INDEX.get(start);
  const totals = new Map<number, number>();
  if (index === undefined || index + weeks > SEASON_EVENTS.length)
    return totals;

  for (const player of SEASON_PLAYERS) {
    let total = 0;
    for (let ahead = 0; ahead < weeks; ahead += 1) {
      total += pointsAtEvent(player, index + ahead);
    }
    totals.set(player.code, total);
  }
  return totals;
}

/** How many gameweeks the horizon actually has left to run. */
export function horizonsAvailable(from?: number): Horizon[] {
  const start = firstEvent(from);
  const index = start === null ? undefined : EVENT_INDEX.get(start);
  if (index === undefined) return [];
  return HORIZONS.filter((weeks) => index + weeks <= SEASON_EVENTS.length);
}
