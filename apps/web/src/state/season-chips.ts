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

/**
 * How many of the fifteen a wildcard has to move before it is worth playing.
 *
 * Anything a free transfer or two could have made is not a wildcard, it is a
 * transfer you happened to make in the week you burned a chip.
 */
const MINIMUM_WILDCARD_CHANGES = 5;

/** The run a kept squad is priced over. A free hit is one afternoon. */
const WILDCARD_HORIZON = 5;

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
 * A free hit is one week, so it is priced on that afternoon alone. A wildcard
 * keeps the squad, so it is priced across the run it opens -- the note used to
 * claim five gameweeks while the number underneath measured one.
 */
function rebuildCalls(
  half: string,
  weeks: readonly SolvedGameweek[],
): ChipCall[] {
  const priced = weeks
    .map((week) => ({
      week,
      free: rebuildUplift(
        week.event,
        [...week.starters, ...week.bench],
        budgetAt(week),
      ),
      kept: rebuildUplift(
        week.event,
        [...week.starters, ...week.bench],
        budgetAt(week),
        WILDCARD_HORIZON,
      ),
    }))
    .filter((entry) => entry.free.rebuilt !== null);

  const freeHit = priced
    .filter((entry) => entry.free.gain > 0)
    .sort((left, right) => right.free.gain - left.free.gain)[0];

  // A wildcard that moves one player is a wildcard thrown away, however well
  // that one swap scores: the chip is the right to rebuild, and a rebuild the
  // free transfer could have made costs nothing to make with the free transfer.
  const wildcard = priced
    .filter(
      (entry) =>
        entry.kept.gain > 0 &&
        entry.kept.changes >= MINIMUM_WILDCARD_CHANGES &&
        // Never the same week twice: one squad cannot be both handed back and kept.
        entry.week.event !== freeHit?.week.event,
    )
    .sort((left, right) => right.kept.gain - left.kept.gain)[0];

  return [
    freeHit
      ? {
          event: freeHit.week.event,
          chip: "Free Hit",
          half,
          gain: Math.round(freeHit.free.gain * 100) / 100,
          note:
            `the best fifteen this budget buys is worth ${freeHit.free.gain.toFixed(1)} more ` +
            `than yours in gameweek ${String(freeHit.week.event)}, on ${String(freeHit.free.changes)} changes, ` +
            `and you get yours back after`,
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
          gain: Math.round(wildcard.kept.gain * 100) / 100,
          note:
            `rebuilding in gameweek ${String(wildcard.week.event)} moves ${String(wildcard.kept.changes)} of your fifteen ` +
            `and is worth ${wildcard.kept.gain.toFixed(1)} over the ${String(WILDCARD_HORIZON)} gameweeks it opens, and the squad stays`,
        }
      : {
          event: null,
          chip: "Wildcard",
          half,
          gain: 0,
          note: `no week in this half where a rebuild moves ${String(MINIMUM_WILDCARD_CHANGES)} or more of your fifteen for a gain`,
        },
  ];
}

/**
 * A chip the reader has already decided on, priced where he says he will play
 * it rather than where the plan would.
 *
 * Arguing with a decision already made is how a plan stops being read. So the
 * call becomes his week, and the note says what the plan would have chosen and
 * what the difference is worth. He can then change his mind on the number, or
 * not, which is the whole point of showing it.
 */
function pinned(
  committed: { chip: string; event: number },
  solved: ChipCall | undefined,
  weeks: readonly SolvedGameweek[],
  half: string,
): ChipCall {
  const week = weeks.find((entry) => entry.event === committed.event);
  const score =
    committed.chip === "Bench Boost"
      ? benchPoints
      : committed.chip === "Triple Captain"
        ? tripleCaptainPoints
        : null;
  // Wildcard and Free Hit are priced by rebuilding, which needs the pool and
  // is not worth a second pass here. The week is still his; the gain is not
  // claimed.
  const gain = week && score ? Math.round(score(week) * 100) / 100 : 0;
  const better =
    solved?.event != null && solved.event !== committed.event
      ? `; the plan would have said gameweek ${String(solved.event)}, worth ${solved.gain.toFixed(1)}`
      : "";
  return {
    event: committed.event,
    chip: committed.chip,
    half,
    gain,
    note:
      week && score
        ? `you have committed to gameweek ${String(committed.event)}, worth ${gain.toFixed(1)}${better}`
        : `you have committed to gameweek ${String(committed.event)}${better}`,
  };
}

/**
 * Chip calls for a solved season, all four of them.
 *
 * Bench Boost and Triple Captain read straight off the solved weeks. Wildcard
 * and Free Hit rebuild the fifteen from the pool, because a beam search capped
 * at five transfers a week cannot express "throw it away and start again".
 *
 * A chip already played is dropped rather than re-offered. FPL publishes only
 * the one used last gameweek, so this depends on the manager saying so, and a
 * plan that keeps advising a wildcard spent in August is worse than one that
 * says nothing: every transfer around it is planned against a move he cannot
 * make.
 */
export function chipCallsFor(
  gameweeks: readonly SolvedGameweek[],
  published: readonly ChipCall[],
  spent: readonly string[] = [],
  committed: { chip: string; event: number } | null = null,
): ChipCall[] {
  const gone = new Set(spent);
  const keep = (calls: ChipCall[]): ChipCall[] =>
    calls.filter((call) => !gone.has(call.chip));
  const claimed = committed && !gone.has(committed.chip) ? committed : null;
  if (gameweeks.length === 0) {
    const carried = keep([...published]);
    if (!claimed) return carried;
    const half = claimed.event <= 19 ? "first" : "second";
    return carried.map((call) =>
      call.chip === claimed.chip && call.half === half
        ? pinned(claimed, call, [], half)
        : call,
    );
  }

  const calls: ChipCall[] = [];
  for (const { half, from, to } of HALVES) {
    const weeks = gameweeks.filter(
      (week) => week.event >= from && week.event <= to,
    );
    if (weeks.length === 0) continue;

    const halfCalls = [
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
    ];

    calls.push(
      ...(claimed && claimed.event >= from && claimed.event <= to
        ? halfCalls.map((call) =>
            call.chip === claimed.chip
              ? pinned(claimed, call, weeks, half)
              : call,
          )
        : halfCalls),
    );
  }

  return keep(calls);
}
