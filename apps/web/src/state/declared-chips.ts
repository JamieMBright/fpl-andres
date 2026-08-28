import { z } from "zod";

/**
 * Chips a manager has spent, and one he has committed to.
 *
 * FPL publishes `active_chip` for the gameweek just gone and nothing at all
 * about the ones before it or the one he intends next, so a plan that does not
 * ask will happily advise a wildcard he played in August. It will also plan
 * around a Triple Captain he has already decided on, which is worse: the whole
 * shape of the following weeks changes if the armband is trebled.
 *
 * Held in `localStorage` for the same reason as the declared transfers beside
 * it: a Team ID is public and enumerable, so anything a server handed back
 * could be forged by anybody who knew the number. In the browser it can only
 * be the manager's own claim about his own team.
 */

const STORAGE_PREFIX = "fpl-andres:chips";

/** FPL's own names, so a reader comparing to the game sees the same words. */
export const CHIPS = ["wildcard", "freehit", "bboost", "3xc"] as const;

export type Chip = (typeof CHIPS)[number];
export type ChipHalf = "first" | "second";
export interface SpentChip {
  chip: Chip;
  half: ChipHalf;
}

export const CHIP_NAMES: Record<Chip, string> = {
  wildcard: "Wildcard",
  freehit: "Free Hit",
  bboost: "Bench Boost",
  "3xc": "Triple Captain",
};

const chipSchema = z.enum(CHIPS);
const chipHalfSchema = z.enum(["first", "second"]);
const spentChipSchema = z.object({ chip: chipSchema, half: chipHalfSchema });

const declaredChipsSchema = z.object({
  /** Chips already played, so the plan must not offer them again. */
  spent: z
    .array(z.union([chipSchema, spentChipSchema]))
    .max(CHIPS.length * 2)
    .transform((spent) =>
      spent.map((entry): SpentChip =>
        typeof entry === "string" ? { chip: entry, half: "first" } : entry,
      ),
    ),
  /** One he has committed to, and the gameweek he will play it in. */
  committed: z
    .object({ chip: chipSchema, event: z.number().int().min(1).max(47) })
    .nullable()
    .default(null),
});

export type DeclaredChips = z.infer<typeof declaredChipsSchema>;

export const NO_CHIPS: DeclaredChips = { spent: [], committed: null };

export function halfForEvent(event: number): ChipHalf {
  return event <= 19 ? "first" : "second";
}

function key(entryId: number): string {
  return `${STORAGE_PREFIX}:${entryId}`;
}

export function readDeclaredChips(
  storage: Storage,
  entryId: number,
): DeclaredChips {
  const raw = storage.getItem(key(entryId));
  if (!raw) return NO_CHIPS;
  try {
    const parsed = declaredChipsSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) {
      storage.removeItem(key(entryId));
      return NO_CHIPS;
    }
    return parsed.data;
  } catch {
    storage.removeItem(key(entryId));
    return NO_CHIPS;
  }
}

export function saveDeclaredChips(
  storage: Storage,
  entryId: number,
  chips: DeclaredChips,
): DeclaredChips {
  // A chip cannot be both spent and committed: spending it is what ends the
  // commitment, and holding both would let the plan schedule one he has used.
  const spent = [
    ...new Map(
      chips.spent.map((entry) => [`${entry.chip}:${entry.half}`, entry]),
    ).values(),
  ];
  const committed =
    chips.committed &&
    !spent.some(
      (entry) =>
        entry.chip === chips.committed?.chip &&
        entry.half === halfForEvent(chips.committed.event),
    )
      ? chips.committed
      : null;
  const next: DeclaredChips = {
    spent: spent.sort((left, right) =>
      `${left.half}:${left.chip}`.localeCompare(`${right.half}:${right.chip}`),
    ),
    committed,
  };
  storage.setItem(key(entryId), JSON.stringify(next));
  return next;
}

/** Which chips the plan may still schedule. */
export function chipsRemaining(chips: DeclaredChips, half: ChipHalf): Chip[] {
  return CHIPS.filter(
    (chip) =>
      !chips.spent.some((entry) => entry.chip === chip && entry.half === half),
  );
}
