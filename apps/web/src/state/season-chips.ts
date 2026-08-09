import type { ChipCall } from "./season-plan";
import type { SolvedGameweek } from "./season-solver";

/**
 * Which week to play a chip, for the squad actually being solved.
 *
 * The published chip calls belong to the published opening fifteen. Handing
 * them to a manager who locked in his own squad names weeks that suit somebody
 * else's bench, which is worse than saying nothing.
 *
 * Bench Boost and Triple Captain need no extra solving: they pay what this
 * plan's bench and captain already score, so their week falls straight out of
 * the gameweeks on screen. Wildcard and Free Hit do not, and are not guessed
 * at here -- see `UNSOLVED_CHIPS`.
 */

const HALVES = [
  { half: "first", from: 1, to: 19 },
  { half: "second", from: 20, to: 38 },
] as const;

/**
 * The two the browser cannot answer.
 *
 * Both rebuild the fifteen, and `solveQuickPlan` is a beam search capped at
 * five transfers a week. Sizing them needs a fresh fifteen-man selection the
 * browser has no solver for, so their weeks are left to the published plan and
 * the page says which is which.
 */
export const UNSOLVED_CHIPS = ["Wildcard", "Free Hit"] as const;

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
 * Chip calls for a solved season, plus whichever published ones still stand.
 *
 * Published Wildcard and Free Hit calls are carried through unchanged and
 * flagged by `UNSOLVED_CHIPS`, so a half never silently loses two of its four.
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

    for (const chip of UNSOLVED_CHIPS) {
      const carried = published.find(
        (call) => call.chip === chip && call.half === half,
      );
      if (carried) calls.push(carried);
    }

    if (weeks.length === 0) continue;

    calls.push(
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
