import { describe, expect, it } from "vitest";

import { pointsDistribution } from "./rank-distribution";

describe("points distribution", () => {
  it("returns nothing for an empty field", () => {
    expect(pointsDistribution([])).toEqual([]);
  });

  it("puts everyone in one bucket when every total is tied", () => {
    expect(
      pointsDistribution([{ total: 100 }, { total: 100 }, { total: 100 }]),
    ).toEqual([{ label: "100", count: 3 }]);
  });

  it("spreads totals across the requested number of buckets", () => {
    const managers = Array.from({ length: 10 }, (_, index) => ({
      total: index * 10,
    }));

    const buckets = pointsDistribution(managers, 3);

    expect(buckets).toHaveLength(3);
    expect(buckets.reduce((sum, bucket) => sum + bucket.count, 0)).toBe(10);
  });

  it("puts the maximum total in the last bucket, not one past it", () => {
    const managers = [{ total: 0 }, { total: 50 }, { total: 100 }];

    const buckets = pointsDistribution(managers, 2);

    expect(buckets.reduce((sum, bucket) => sum + bucket.count, 0)).toBe(3);
    expect(buckets[1]?.count).toBeGreaterThan(0);
  });
});
