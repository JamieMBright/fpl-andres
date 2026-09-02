/**
 * All five hundred, sorted by whichever measure the reader picked.
 *
 * No entry is more "first" than another here: the 500 are equal by
 * construction (the catalogue's own bar, not a competition among
 * themselves). Sorting exists only to draw a readable curve, not to crown
 * anyone.
 */

export type StandingMetric = "points" | "rank";

export interface SeasonStandingRow {
  overallRank: number | null;
  totalPoints: number;
}

/** Sorted best-to-worst by the chosen metric. Missing a rank sorts last. */
export function sortedStanding(
  rows: readonly SeasonStandingRow[],
  metric: StandingMetric,
): SeasonStandingRow[] {
  if (metric === "points") {
    return [...rows].sort(
      (left, right) => right.totalPoints - left.totalPoints,
    );
  }
  return [...rows].sort(
    (left, right) =>
      (left.overallRank ?? Number.POSITIVE_INFINITY) -
      (right.overallRank ?? Number.POSITIVE_INFINITY),
  );
}
