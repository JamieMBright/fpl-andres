import { z } from "zod";

/**
 * What I said, and what you did.
 *
 * A recommendation nobody checks is an opinion. Once a gameweek is scored, the
 * squad FPL publishes says exactly what the manager actually did, and the call
 * recorded before the deadline says exactly what was advised. Holding the two
 * next to each other is the only way either of us finds out whether the advice
 * was worth taking.
 *
 * Recorded before the deadline and never rewritten afterwards. A call that can
 * be edited once the result is in is not a call, and a scorecard built from one
 * would only ever agree with itself.
 *
 * In this browser, like every other statement about a manager's own team: a
 * Team ID is public and enumerable, so a record that came back from a server
 * could have been written by anybody who guessed the number.
 *
 * Agreement only, not points. Scoring "my captain against yours" needs each
 * player's points for the gameweek, and no endpoint this app is allowed to
 * call publishes them. Counting agreement is a smaller claim that is true.
 */

const STORAGE_PREFIX = "fpl-andres:scorecard:v1";

/** A season of calls is thirty-eight; the cap is a bound, not a policy. */
const MAX_CALLS = 60;

const callSchema = z.object({
  event: z.number().int().min(1).max(47),
  /** The fifteen the advice was given from, so the manager's move can be seen. */
  squadBefore: z.array(z.number().int().positive()).length(15),
  /** Null where the advice was to roll the transfer rather than spend it. */
  elementOut: z.number().int().positive().nullable(),
  elementIn: z.number().int().positive().nullable(),
  captain: z.number().int().positive(),
  recordedAt: z.iso.datetime(),
  /** Filled once FPL publishes the gameweek. Null while it is still ahead. */
  settled: z
    .object({
      elementOut: z.number().int().positive().nullable(),
      elementIn: z.number().int().positive().nullable(),
      captain: z.number().int().positive(),
      settledAt: z.iso.datetime(),
    })
    .nullable()
    .default(null),
});

export type ScoredCall = z.infer<typeof callSchema>;

const scorecardSchema = z.array(callSchema);

export function scorecardStorageKey(entryId: number): string {
  if (!Number.isInteger(entryId) || entryId < 1) {
    throw new TypeError("Team ID is outside the supported range");
  }
  return `${STORAGE_PREFIX}:${String(entryId)}`;
}

/** Every call held for this manager, oldest gameweek first. A bad store is dropped. */
export function readScorecard(storage: Storage, entryId: number): ScoredCall[] {
  const key = scorecardStorageKey(entryId);
  const serialized = storage.getItem(key);
  if (serialized === null) return [];
  try {
    const parsed = scorecardSchema.safeParse(JSON.parse(serialized));
    if (!parsed.success) {
      storage.removeItem(key);
      return [];
    }
    return [...parsed.data].sort((left, right) => left.event - right.event);
  } catch {
    storage.removeItem(key);
    return [];
  }
}

function write(storage: Storage, entryId: number, calls: ScoredCall[]): void {
  storage.setItem(
    scorecardStorageKey(entryId),
    JSON.stringify(calls.slice(-MAX_CALLS)),
  );
}

/**
 * Record the advice for a gameweek that has not been played.
 *
 * Refuses to overwrite an existing call for the same gameweek. The plan is
 * re-solved on every visit and the numbers move as prices and news do; taking
 * the last version before the deadline would score whichever answer happened to
 * be on screen when he stopped looking.
 */
export function recordCall(
  storage: Storage,
  entryId: number,
  call: Omit<ScoredCall, "recordedAt" | "settled">,
  now: () => Date = () => new Date(),
): ScoredCall[] {
  const held = readScorecard(storage, entryId);
  if (held.some((entry) => entry.event === call.event)) return held;
  const parsed = callSchema.safeParse({
    ...call,
    recordedAt: now().toISOString(),
    settled: null,
  });
  if (!parsed.success) return held;
  const next = [...held, parsed.data].sort(
    (left, right) => left.event - right.event,
  );
  write(storage, entryId, next);
  return next;
}

/**
 * Close a call against the squad FPL has now published for that gameweek.
 *
 * The transfer is read as the difference between the fifteen the advice was
 * given from and the fifteen he actually fielded, because that is what a
 * transfer is. More than one change means he took a hit or played a chip, and
 * both are reported as they happened rather than reduced to one swap.
 */
export function settleCall(
  storage: Storage,
  entryId: number,
  event: number,
  playedSquad: readonly number[],
  captain: number,
  now: () => Date = () => new Date(),
): ScoredCall[] {
  const held = readScorecard(storage, entryId);
  const call = held.find((entry) => entry.event === event);
  if (!call || call.settled) return held;

  const before = new Set(call.squadBefore);
  const after = new Set(playedSquad);
  const out = call.squadBefore.filter((id) => !after.has(id));
  const introduced = [...after].filter((id) => !before.has(id));
  // A single swap is the case worth naming. Anything else is a hit or a chip,
  // and calling one of four changes "the transfer" would be picking a winner.
  const single = out.length === 1 && introduced.length === 1;

  const settled = {
    ...call,
    settled: {
      elementOut: single ? (out[0] ?? null) : null,
      elementIn: single ? (introduced[0] ?? null) : null,
      captain,
      settledAt: now().toISOString(),
    },
  };
  const next = held.map((entry) => (entry.event === event ? settled : entry));
  write(storage, entryId, next);
  return next;
}

export interface ScoreTally {
  settled: number;
  captainAgreed: number;
  transferAgreed: number;
}

/** How often the manager and the model reached the same call. Settled weeks only. */
export function tally(calls: readonly ScoredCall[]): ScoreTally {
  const settled = calls.filter((call) => call.settled !== null);
  return {
    settled: settled.length,
    captainAgreed: settled.filter(
      (call) => call.settled?.captain === call.captain,
    ).length,
    transferAgreed: settled.filter(
      (call) =>
        call.settled?.elementIn === call.elementIn &&
        call.settled.elementOut === call.elementOut,
    ).length,
  };
}
