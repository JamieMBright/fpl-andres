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

export interface StandingHistogramBin {
  start: number;
  end: number;
  count: number;
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

/** Fixed-width metric bins, including empty intervals so the x axis stays honest. */
export function standingHistogram(
  rows: readonly SeasonStandingRow[],
  metric: StandingMetric,
  binSize: number,
): StandingHistogramBin[] {
  if (!Number.isFinite(binSize) || binSize <= 0) {
    throw new RangeError("standing histogram bin size must be positive");
  }
  const values = rows.flatMap((row) => {
    const value = metric === "points" ? row.totalPoints : row.overallRank;
    return value === null ? [] : [value];
  });
  if (values.length === 0) return [];
  const first = Math.floor(Math.min(...values) / binSize) * binSize;
  const last = Math.floor(Math.max(...values) / binSize) * binSize;
  const bins = Array.from(
    { length: Math.floor((last - first) / binSize) + 1 },
    (_, index) => ({
      start: first + index * binSize,
      end: first + (index + 1) * binSize - 1,
      count: 0,
    }),
  );
  for (const value of values) {
    const index = Math.floor((value - first) / binSize);
    const bin = bins[index];
    if (bin) bin.count += 1;
  }
  return bins;
}
