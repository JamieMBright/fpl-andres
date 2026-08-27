import projections from "../data/projections.json";

/**
 * Where a number sits against everyone else who plays that position.
 *
 * A figure on its own is not evidence: four points a match is excellent for a
 * defender and ordinary for a forward. These bands are the published pool's own
 * quartiles, recomputed per position, so "good" means "better than most of the
 * people you would pick instead".
 */
export type Band = "poor" | "ordinary" | "useful" | "strong";

interface Row {
  position: string;
  expectedPoints: number;
  expectedMinutes: number;
  probabilityAppear: number;
  probabilityStart: number;
  probabilityStartModel: number;
  appearances: number;
  floor: number | null;
  median: number | null;
  ceiling: number | null;
  returnRate: number | null;
  blankRate: number | null;
  yellowCards: number;
  suspensionMultiplier: number;
}

/** Numbers where a bigger value is worse, so the bands run the other way. */
const LOWER_IS_BETTER = new Set(["blankRate", "yellowCards"]);

const ROWS = (projections as { players: Row[] }).players;

function quartiles(values: number[]): [number, number, number] {
  const sorted = [...values].sort((a, b) => a - b);
  const at = (fraction: number) =>
    sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * fraction))] ??
    0;
  return [at(0.25), at(0.5), at(0.75)];
}

/**
 * Cut points per position per field, built once from the published pool.
 *
 * Only players with a real record are used. Including the blanks would drag
 * every quartile toward zero and make an ordinary player look strong.
 */
const CUTS = new Map<string, [number, number, number]>();

function cutsFor(position: string, field: keyof Row): [number, number, number] {
  const key = `${position}:${field}`;
  const cached = CUTS.get(key);
  if (cached) return cached;

  const values = ROWS.filter(
    (row) => row.position === position && row.appearances > 0,
  )
    .map((row) => row[field])
    .filter((value): value is number => typeof value === "number");
  const built = values.length >= 8 ? quartiles(values) : ([0, 0, 0] as const);
  CUTS.set(key, built as [number, number, number]);
  return built as [number, number, number];
}

/**
 * The band this value falls in, or null where the position has too few
 * measured players to say anything. Null renders uncoloured rather than grey,
 * because "no opinion" and "below average" are different claims.
 */
export function bandFor(
  position: string,
  field: keyof Row,
  value: number | null,
): Band | null {
  if (value === null) return null;
  const [low, middle, high] = cutsFor(position, field);
  if (low === middle && middle === high) return null;

  const rank =
    value >= high ? 3 : value >= middle ? 2 : value >= low ? 1 : (0 as const);
  const inverted = LOWER_IS_BETTER.has(field) ? 3 - rank : rank;
  return (["poor", "ordinary", "useful", "strong"] as const)[inverted] ?? null;
}
