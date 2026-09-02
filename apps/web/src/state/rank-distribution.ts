/**
 * The shape of the live Overall league, not just its edges.
 *
 * A raw top-N table says who is first; it says nothing about how bunched the
 * field is. Bucketing the same totals into equal-width point ranges answers
 * the question a manager actually has mid-season: how many points separate
 * me from a small step up, and is the run-in for a given rank tight or open.
 */

export interface PointsBucket {
  /** "180–199" style label for the bucket's point range. */
  label: string;
  count: number;
}

export function pointsDistribution(
  managers: readonly { total: number }[],
  bucketCount = 10,
): PointsBucket[] {
  if (managers.length === 0) return [];
  const totals = managers.map((manager) => manager.total);
  const minimum = Math.min(...totals);
  const maximum = Math.max(...totals);
  if (minimum === maximum) {
    return [{ label: `${String(minimum)}`, count: managers.length }];
  }

  const span = maximum - minimum;
  const buckets = Array.from({ length: bucketCount }, () => 0);
  for (const total of totals) {
    // The maximum total belongs in the last bucket, not one past the end.
    const index = Math.min(
      bucketCount - 1,
      Math.floor(((total - minimum) / span) * bucketCount),
    );
    buckets[index] = (buckets[index] ?? 0) + 1;
  }

  return buckets.map((count, index) => {
    const low = Math.round(minimum + (span / bucketCount) * index);
    const high = Math.round(minimum + (span / bucketCount) * (index + 1));
    return { label: `${String(low)}–${String(high)}`, count };
  });
}
