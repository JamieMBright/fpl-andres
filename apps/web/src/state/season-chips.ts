import type { ChipCall } from "./season-plan";
import type { SolvedGameweek } from "./season-solver";
import { rebuildUplift } from "./squad-rebuild";

/**
 * Which week to play a chip, for the squad actually being solved.
 *
 * The published chip calls belong to the published opening fifteen. Handing
 * them to a manager who locked in his own squad names weeks that suit somebody
 * else's bench, which is worse than saying nothing.
 *
 * All four are solved here. Bench Boost and Triple Captain fall out of the
 * gameweeks on screen; Wildcard and Free Hit are priced by rebuilding the
 * fifteen from the pool, in `squad-rebuild.ts`.
 */

const HALVES = [
  { half: "first", from: 1, to: 19 },
  { half: "second", from: 20, to: 38 },
] as const;

function pointsOf(week: SolvedGameweek, code: number): number {
  return week.expected[String(code)] ?? 0;
}

/** What the bench would add if all four played. */
export function benchPoints(week: SolvedGameweek): number {
  return week.bench.reduce(
    (total, player) => total + pointsOf(week, player.code),
    0,
  );
}

/** What a third copy of the captain adds, over the two he already returns. */
export function tripleCaptainPoints(week: SolvedGameweek): number {
  return pointsOf(week, week.captain.code);
}

function bestWeek(
  weeks: readonly SolvedGameweek[],
  score: (week: SolvedGameweek) => number,
): { week: SolvedGameweek; gain: number } | null {
  let best: { week: SolvedGameweek; gain: number } | null = null;
  for (const week of weeks) {
    const gain = score(week);
    if (!best || gain > best.gain) best = { week, gain };
  }
  return best;
}

function callFor(
  chip: string,
  half: string,
  weeks: readonly SolvedGameweek[],
  score: (week: SolvedGameweek) => number,
  note: (gain: number, week: SolvedGameweek) => string,
): ChipCall {
  const best = bestWeek(weeks, score);
  if (!best || best.gain <= 0) {
    return {
      event: null,
      chip,
      half,
      gain: 0,
      note: "no week in this half is worth it",
    };
  }
  return {
    event: best.week.event,
    chip,
    half,
    gain: Math.round(best.gain * 100) / 100,
    note: note(best.gain, best.week),
  };
}

/**
 * What a squad entering this gameweek is worth if it were all sold.
 *
 * Selling price is not list price, but the solved plan does not carry one per
 * player, so this uses list. It overstates a risen player's value by half his
 * rise, which is named in the chip note rather than hidden.
 */
function budgetAt(week: SolvedGameweek): number {
  const held = [...week.starters, ...week.bench];
  return (
    held.reduce((total, player) => total + player.priceTenths, 0) +
    week.bankAfterTenths
  );
}

/**
 * The two rebuild chips, priced by actually rebuilding.
 *
 * A free hit is one week, so its gain is the one-week uplift of the best
 * fifteen the money buys. A wildcard keeps the squad, so it is priced on the
 * lookahead the rebuild is chosen for -- the run it opens, not the Saturday.
 */
function rebuildCalls(
  half: string,
  weeks: readonly SolvedGameweek[],
): ChipCall[] {
  const priced = weeks
    .map((week) => ({
      week,
      ...rebuildUplift(
        week.event,
        [...week.starters, ...week.bench],
        budgetAt(week),
      ),
    }))
    .filter((entry) => entry.rebuilt !== null && entry.gain > 0)
    .sort((left, right) => right.gain - left.gain);

  const freeHit = priced[0];
  // Never the same week twice: one squad cannot be both handed back and kept.
  const wildcard = priced.find(
    (entry) => entry.week.event !== freeHit?.week.event,
  );

  return [
    freeHit
      ? {
          event: freeHit.week.event,
          chip: "Free Hit",
          half,
          gain: Math.round(freeHit.gain * 100) / 100,
          note:
            `the best fifteen this budget buys is worth ${freeHit.gain.toFixed(1)} more ` +
            `than yours in gameweek ${String(freeHit.week.event)}, and you get yours back after`,
        }
      : {
          event: null,
          chip: "Free Hit",
          half,
          gain: 0,
          note: "no week in this half where a rebuilt fifteen beats yours",
        },
    wildcard
      ? {
          event: wildcard.week.event,
          chip: "Wildcard",
          half,
          gain: Math.round(wildcard.gain * 100) / 100,
          note:
            `rebuilding in gameweek ${String(wildcard.week.event)} is worth ${wildcard.gain.toFixed(1)} ` +
            `on the five gameweeks it opens, and the squad stays`,
        }
      : {
          event: null,
          chip: "Wildcard",
          half,
          gain: 0,
          note: "no week in this half worth a rebuild",
        },
  ];
}

/**
 * Chip calls for a solved season, all four of them.
 *
 * Bench Boost and Triple Captain read straight off the solved weeks. Wildcard
 * and Free Hit rebuild the fifteen from the pool, because a beam search capped
 * at five transfers a week cannot express "throw it away and start again".
 */
export function chipCallsFor(
  gameweeks: readonly SolvedGameweek[],
  published: readonly ChipCall[],
): ChipCall[] {
  if (gameweeks.length === 0) return [...published];

  const calls: ChipCall[] = [];
  for (const { half, from, to } of HALVES) {
    const weeks = gameweeks.filter(
      (week) => week.event >= from && week.event <= to,
    );
    if (weeks.length === 0) continue;

    calls.push(
      ...rebuildCalls(half, weeks),
      callFor(
        "Bench Boost",
        half,
        weeks,
        benchPoints,
        (gain, week) =>
          `your bench is worth ${gain.toFixed(1)} in gameweek ${String(week.event)}, the best of this half`,
      ),
      callFor(
        "Triple Captain",
        half,
        weeks,
        tripleCaptainPoints,
        (gain, week) =>
          `a third copy of ${week.captain.name} is worth ${gain.toFixed(1)} in gameweek ${String(week.event)}`,
      ),
    );
  }

  return calls;
}
