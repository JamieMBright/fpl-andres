import { z } from "zod";

/**
 * Transfers a manager has made that FPL has not published yet.
 *
 * A manager's picks for the coming gameweek are private until the deadline
 * passes, so the public squad is the one he finished the last gameweek with. A
 * plan built from it recommends a transfer already made.
 *
 * Held in `localStorage` rather than fetched, and that is the whole security
 * design: a Team ID is public and enumerable, so a declared transfer that came
 * back from a server could be forged by anyone who knew the number. Kept in the
 * browser it can only ever be the manager's own claim about his own squad.
 * The server copy is written and never read.
 */

const STORAGE_PREFIX = "fpl-andres:declared";

const declaredSchema = z.object({
  event: z.number().int().min(1).max(47),
  elementOut: z.number().int().positive(),
  elementIn: z.number().int().positive(),
  pointsCharged: z.number().int().min(0).max(60),
});

export type DeclaredTransfer = z.infer<typeof declaredSchema>;

const storedSchema = z.array(declaredSchema).max(15);

function key(entryId: number): string {
  return `${STORAGE_PREFIX}:${entryId}`;
}

export function readDeclaredTransfers(
  storage: Storage,
  entryId: number,
  event: number,
): DeclaredTransfer[] {
  const raw = storage.getItem(key(entryId));
  if (!raw) return [];
  try {
    const parsed = storedSchema.safeParse(JSON.parse(raw));
    // A declaration for a gameweek already published is spent, not wrong.
    return parsed.success
      ? parsed.data.filter((entry) => entry.event >= event)
      : [];
  } catch {
    return [];
  }
}

export function saveDeclaredTransfer(
  storage: Storage,
  entryId: number,
  transfer: DeclaredTransfer,
): DeclaredTransfer[] {
  const held = readDeclaredTransfers(storage, entryId, 1).filter(
    (entry) =>
      !(
        entry.event === transfer.event &&
        entry.elementOut === transfer.elementOut &&
        entry.elementIn === transfer.elementIn
      ),
  );
  const next = [...held, transfer].slice(-15);
  storage.setItem(key(entryId), JSON.stringify(next));
  return next;
}

export function forgetDeclaredTransfers(
  storage: Storage,
  entryId: number,
): void {
  storage.removeItem(key(entryId));
}

/**
 * Apply declarations on top of the published fifteen.
 *
 * A declaration naming a player the manager does not own is dropped rather than
 * applied: it would leave a fourteen-player squad, and the solver would fail on
 * it somewhere less obvious than here.
 */
export function squadAfterDeclared(
  published: readonly number[],
  declared: readonly DeclaredTransfer[],
): number[] {
  const squad = [...published];
  for (const transfer of declared) {
    const index = squad.indexOf(transfer.elementOut);
    if (index === -1 || squad.includes(transfer.elementIn)) continue;
    squad[index] = transfer.elementIn;
  }
  return squad;
}

/** Fire and forget: a plan is not worth withholding because a log write failed. */
export function recordAnalysisRequest(
  body: {
    season: string;
    entryId: number;
    event: number;
    transfer: DeclaredTransfer | null;
  },
  fetchApi: typeof fetch = fetch,
): void {
  void fetchApi("/api/analysis-request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      season: body.season,
      entryId: body.entryId,
      event: body.event,
      transfer: body.transfer
        ? {
            elementOut: body.transfer.elementOut,
            elementIn: body.transfer.elementIn,
            pointsCharged: body.transfer.pointsCharged,
          }
        : null,
    }),
  }).catch(() => {
    // Deliberately silent. The reader came for a plan, not for telemetry.
  });
}
