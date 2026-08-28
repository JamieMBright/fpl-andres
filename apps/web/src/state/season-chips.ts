import type { ChipCall } from "./season-plan";
import {
  MINIMUM_FREE_HIT_CHANGES,
  MINIMUM_WILDCARD_CHANGES,
  WILDCARD_HORIZONS,
  WILDCARD_REBUILD_HORIZON,
} from "./chip-rules";
import {
  EVENT_INDEX,
  SEASON_TRANSFER_RULES,
  bestElevenPoints,
  type SolvedGameweek,
  type SolverPlayer,
} from "./season-solver";
import { rebuildUplift } from "./squad-rebuild";

/**
 * Which week to play a chip, for the squad actually being solved.
 *
 * The published chip calls belong to the published opening fifteen. Handing
 * them to a manager who locked in his own squad names weeks that suit somebody
 * else's bench, which is worse than saying nothing.
 *
 * All eight half-season copies are solved here. Bench Boost and Triple Captain fall out of the
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

export function chipCallsByEvent(
  calls: readonly ChipCall[],
  weeks: readonly { event: number; chip?: string | undefined }[],
  committed: { chip: string; event: number } | null = null,
): Map<number, ChipCall> {
  const solvedByEvent = new Map(weeks.map((week) => [week.event, week]));
  const byEvent = new Map<number, ChipCall>();
  for (const call of calls) {
    if (call.event === null) continue;
    if (
      (call.chip === "Free Hit" || call.chip === "Wildcard") &&
      solvedByEvent.get(call.event)?.chip !== call.chip &&
      (committed?.event !== call.event || committed.chip !== call.chip)
    ) {
      continue;
    }
    byEvent.set(call.event, call);
  }
  return byEvent;
}

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

export function freeHitSegmentGain(
  weekIndex: number,
  allWeeks: readonly SolvedGameweek[],
  entering: readonly SolverPlayer[],
  oneWeekGain: number,
): number {
  let gain = oneWeekGain;
  let restored = [...entering];
  let freeTransfers = SEASON_TRANSFER_RULES.weeklyFreeTransfers;
  for (let ahead = 1; ahead < WILDCARD_REBUILD_HORIZON; ahead += 1) {
    const planned = allWeeks[weekIndex + ahead];
    if (!planned) break;
    const held = new Map(restored.map((player) => [player.id, player]));
    let changes = 0;
    for (let index = 0; index < planned.transfersIn.length; index += 1) {
      const outgoing = planned.transfersOut[index];
      const incoming = planned.transfersIn[index];
      if (
        !outgoing ||
        !incoming ||
        !held.has(outgoing.id) ||
        held.has(incoming.id)
      ) {
        continue;
      }
      held.delete(outgoing.id);
      held.set(incoming.id, incoming);
      changes += 1;
    }
    restored = [...held.values()];
    const eventIndex = EVENT_INDEX.get(planned.event);
    if (eventIndex === undefined || restored.length !== 15) continue;
    const paidTransfers = Math.max(0, changes - freeTransfers);
    const restoredPoints =
      bestElevenPoints(restored, eventIndex) -
      paidTransfers * SEASON_TRANSFER_RULES.transferCostPoints;
    gain += restoredPoints - planned.netExpectedPoints;
    freeTransfers = Math.min(
      SEASON_TRANSFER_RULES.maximumFreeTransfers,
      Math.max(0, freeTransfers - changes) +
        SEASON_TRANSFER_RULES.weeklyFreeTransfers,
    );
  }
  return gain;
}

export function wildcardRunGain(
  rebuilt: readonly SolverPlayer[],
  weekIndex: number,
  allWeeks: readonly SolvedGameweek[],
  horizon: number,
): number {
  let gain = 0;
  for (let ahead = 0; ahead < horizon; ahead += 1) {
    const planned = allWeeks[weekIndex + ahead];
    if (!planned) break;
    const eventIndex = EVENT_INDEX.get(planned.event);
    if (eventIndex === undefined) continue;
    gain += bestElevenPoints(rebuilt, eventIndex) - planned.netExpectedPoints;
  }
  return gain;
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
  candidateWeeks: readonly SolvedGameweek[],
  allWeeks: readonly SolvedGameweek[],
): ChipCall[] {
  const allWeekIndex = new Map(
    allWeeks.map((week, index) => [week.event, index]),
  );
  const priced = candidateWeeks
    .map((week) => {
      const weekIndex = allWeekIndex.get(week.event);
      if (weekIndex === undefined) return null;
      const held = [...week.starters, ...week.bench];
      const transferredIn = new Set(
        week.transfersIn.map((player) => player.id),
      );
      const entering = [
        ...held.filter((player) => !transferredIn.has(player.id)),
        ...week.transfersOut,
      ];
      const enteringIds = new Set(entering.map((player) => player.id));
      const budget = budgetAt(week);
      const remaining = allWeeks.length - weekIndex;
      const availableHorizons = WILDCARD_HORIZONS.filter(
        (horizon) => horizon <= remaining,
      );
      const wildcard = availableHorizons.map((horizon) => ({
        horizon,
        result: (() => {
          const raw = rebuildUplift(week.event, held, budget, horizon);
          if (!raw.rebuilt) return raw;
          return {
            ...raw,
            gain: wildcardRunGain(
              raw.rebuilt.squad,
              weekIndex,
              allWeeks,
              horizon,
            ),
            changes: raw.rebuilt.squad.filter(
              (player) => !enteringIds.has(player.id),
            ).length,
          };
        })(),
      }));
      const cliffs = wildcard.slice(1).map((later, index) => {
        const earlier = wildcard[index];
        if (!earlier?.result.rebuilt || !later.result.rebuilt) {
          return {
            changes: 0,
            from: earlier?.horizon ?? 3,
            to: later.horizon,
            measured: false,
          };
        }
        const earlierIds = new Set(
          earlier.result.rebuilt.squad.map((player) => player.id),
        );
        return {
          changes: later.result.rebuilt.squad.filter(
            (player) => !earlierIds.has(player.id),
          ).length,
          from: earlier.horizon,
          to: later.horizon,
          measured: true,
        };
      });
      const cliff = cliffs.sort(
        (left, right) => right.changes - left.changes,
      )[0] ?? { changes: 0, from: 3, to: 5, measured: false };
      const free = rebuildUplift(week.event, held, budget, 1);
      const freeHitHorizon = Math.min(
        WILDCARD_REBUILD_HORIZON,
        allWeeks.length - weekIndex,
      );
      const freeGain = free.rebuilt
        ? freeHitSegmentGain(weekIndex, allWeeks, entering, free.gain)
        : 0;
      return {
        week,
        entering,
        free: free.rebuilt
          ? {
              ...free,
              gain: freeGain,
              changes: free.rebuilt.squad.filter(
                (player) => !enteringIds.has(player.id),
              ).length,
            }
          : free,
        freeHitHorizon,
        kept: wildcard.at(-1)?.result ?? {
          gain: 0,
          changes: 0,
          rebuilt: null,
        },
        wildcardHorizon: availableHorizons.at(-1) ?? 0,
        cliff,
      };
    })
    .filter((entry) => entry !== null)
    .filter((entry) => entry.free.rebuilt !== null);

  const freeHit = priced
    .filter(
      (entry) =>
        entry.free.gain > 0 && entry.free.changes >= MINIMUM_FREE_HIT_CHANGES,
    )
    .sort((left, right) => right.free.gain - left.free.gain)[0];

  // A wildcard that moves one player is a wildcard thrown away, however well
  // that one swap scores: the chip is the right to rebuild, and a rebuild the
  // free transfer could have made costs nothing to make with the free transfer.
  const wildcard = priced
    .filter(
      (entry) =>
        entry.kept.gain > 0 &&
        entry.kept.changes >= MINIMUM_WILDCARD_CHANGES &&
        entry.cliff.measured &&
        // Never the same week twice: one squad cannot be both handed back and kept.
        entry.week.event !== freeHit?.week.event,
    )
    .sort((left, right) => right.kept.gain - left.kept.gain)[0];

  const changedPlayers = (
    held: readonly SolverPlayer[],
    rebuilt: NonNullable<(typeof priced)[number]["free"]["rebuilt"]>,
  ) => {
    const heldIds = new Set(held.map((player) => player.id));
    const rebuiltIds = new Set(rebuilt.squad.map((player) => player.id));
    return {
      incoming: rebuilt.squad
        .filter((player) => !heldIds.has(player.id))
        .map((player) => player.name),
      outgoing: held
        .filter((player) => !rebuiltIds.has(player.id))
        .map((player) => player.name),
    };
  };
  const freeHitPlayers = freeHit
    ? changedPlayers(freeHit.entering, freeHit.free.rebuilt!)
    : null;
  const wildcardPlayers = wildcard
    ? changedPlayers(wildcard.entering, wildcard.kept.rebuilt!)
    : null;

  return [
    freeHit
      ? {
          event: freeHit.week.event,
          chip: "Free Hit",
          half,
          gain: Math.round(freeHit.free.gain * 100) / 100,
          changes: freeHit.free.changes,
          incoming: freeHitPlayers!.incoming,
          outgoing: freeHitPlayers!.outgoing,
          note:
            `a ${String(freeHit.free.changes)}-change xPts1 rental in gameweek ${String(freeHit.week.event)} is worth ` +
            `${freeHit.free.gain.toFixed(1)} over the ${String(freeHit.freeHitHorizon)}-gameweek restored-squad replay after resetting to one free transfer; ` +
            `current list prices set the budget, so correct selling prices in step one before committing`,
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
          changes: wildcard.kept.changes,
          incoming: wildcardPlayers!.incoming,
          outgoing: wildcardPlayers!.outgoing,
          note:
            `rebuilding in gameweek ${String(wildcard.week.event)} moves ${String(wildcard.kept.changes)} of your fifteen ` +
            `and is worth ${wildcard.kept.gain.toFixed(1)} over the ${String(wildcard.wildcardHorizon)} gameweeks it opens; ` +
            `the legal squad changes ${String(wildcard.cliff.changes)} ${wildcard.cliff.changes === 1 ? "player" : "players"} between xPts${String(wildcard.cliff.from)} and xPts${String(wildcard.cliff.to)}, and the squad stays; ` +
            `current list prices set the budget, so correct selling prices in step one before committing`,
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

function singleChipPerGameweek(
  calls: readonly ChipCall[],
  committed: { chip: string; event: number } | null,
): ChipCall[] {
  const byEvent = new Map<number, ChipCall[]>();
  for (const call of calls) {
    if (call.event === null) continue;
    byEvent.set(call.event, [...(byEvent.get(call.event) ?? []), call]);
  }

  const blocked = new Map<string, string>();
  for (const [event, clashes] of byEvent) {
    if (clashes.length < 2) continue;
    const kept =
      clashes.find(
        (call) => committed?.event === event && committed.chip === call.chip,
      ) ?? [...clashes].sort((left, right) => right.gain - left.gain)[0];
    if (!kept) continue;
    for (const call of clashes) {
      if (call === kept) continue;
      blocked.set(
        `${call.chip}:${call.half}`,
        `${kept.chip} is already using gameweek ${String(event)}`,
      );
    }
  }

  return calls.map((call) => {
    const reason = blocked.get(`${call.chip}:${call.half}`);
    if (!reason) return call;
    const {
      changes: _changes,
      incoming: _incoming,
      outgoing: _outgoing,
      ...rest
    } = call;
    return {
      ...rest,
      event: null,
      gain: 0,
      note: `${reason}, so this chip is left unplayed`,
    };
  });
}

/**
 * Chip calls for a solved season, all eight half-season copies.
 *
 * Bench Boost and Triple Captain read straight off the solved weeks. Wildcard
 * and Free Hit rebuild the fifteen from the pool. Spent identifiers include
 * the half, so using a chip before gameweek 20 does not remove its second copy.
 */
export function chipCallsFor(
  gameweeks: readonly SolvedGameweek[],
  published: readonly ChipCall[],
  spent: readonly string[] = [],
  committed: { chip: string; event: number } | null = null,
): ChipCall[] {
  const gone = new Set(spent);
  const keep = (calls: ChipCall[]): ChipCall[] =>
    calls.filter((call) => !gone.has(`${call.chip}:${call.half}`));
  const claimed =
    committed &&
    !gone.has(`${committed.chip}:${committed.event <= 19 ? "first" : "second"}`)
      ? committed
      : null;

  if (gameweeks.length === 0) {
    const carried = keep([...published]);
    if (!claimed) return singleChipPerGameweek(carried, null);
    const half = claimed.event <= 19 ? "first" : "second";
    return singleChipPerGameweek(
      carried.map((call) =>
        call.chip === claimed.chip && call.half === half
          ? pinned(claimed, call, [], half)
          : call,
      ),
      claimed,
    );
  }

  const calls: ChipCall[] = [];
  for (const { half, from, to } of HALVES) {
    const weeks = gameweeks.filter(
      (week) => week.event >= from && week.event <= to,
    );
    if (weeks.length === 0) continue;

    const halfCalls = [
      ...rebuildCalls(half, weeks, gameweeks),
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
          `${week.captain.name} projects ${gain.toFixed(1)}: ${(gain * 2).toFixed(1)} as captain, ${(gain * 3).toFixed(1)} with Triple Captain. The chip adds ${gain.toFixed(1)} in gameweek ${String(week.event)}`,
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

  return singleChipPerGameweek(keep(calls), claimed);
}
