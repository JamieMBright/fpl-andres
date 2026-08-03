import { describe, expect, it } from "vitest";

import {
  centre,
  leastSquaresFit,
  quadrantOf,
  residualOf,
} from "./scatter-stats";

describe("centre", () => {
  it("takes the middle value of an odd count", () => {
    expect(centre([5, 1, 3], "median")).toBe(3);
  });

  it("averages the middle pair of an even count", () => {
    expect(centre([1, 2, 3, 4], "median")).toBe(2.5);
  });

  it("takes the mean when asked", () => {
    expect(centre([1, 2, 3, 10], "mean")).toBe(4);
  });

  /*
   * The reason median is the default. One Haaland drags the mean above most of
   * the pool, so a "high xGI" quadrant drawn on the mean would be nearly empty.
   */
  it("resists the outlier the mean follows", () => {
    const pool = [1, 1, 1, 1, 100];

    expect(centre(pool, "median")).toBe(1);
    expect(centre(pool, "mean")).toBe(20.8);
  });

  it("has no centre without values", () => {
    expect(centre([], "median")).toBeNull();
  });
});

describe("leastSquaresFit", () => {
  it("recovers a line it was given", () => {
    const fit = leastSquaresFit([
      { x: 0, y: 1 },
      { x: 1, y: 3 },
      { x: 2, y: 5 },
    ]);

    expect(fit?.slope).toBeCloseTo(2);
    expect(fit?.intercept).toBeCloseTo(1);
    expect(fit?.r2).toBeCloseTo(1);
  });

  it("reports a weak fit as weak rather than hiding it", () => {
    const fit = leastSquaresFit([
      { x: 0, y: 5 },
      { x: 1, y: 1 },
      { x: 2, y: 4 },
      { x: 3, y: 2 },
    ]);

    expect(fit).not.toBeNull();
    expect(fit!.r2).toBeLessThan(0.3);
  });

  it("refuses a single point, which fits every line", () => {
    expect(leastSquaresFit([{ x: 1, y: 1 }])).toBeNull();
  });

  /* A vertical stack has no slope, and returning zero would draw a flat line. */
  it("refuses points that share an x", () => {
    expect(
      leastSquaresFit([
        { x: 2, y: 1 },
        { x: 2, y: 9 },
      ]),
    ).toBeNull();
  });
});

describe("residualOf", () => {
  const fit = { slope: 2, intercept: 1, r2: 1 };

  it("is positive above the line", () => {
    expect(residualOf({ x: 1, y: 5 }, fit)).toBe(2);
  });

  it("is negative below the line", () => {
    expect(residualOf({ x: 1, y: 1 }, fit)).toBe(-2);
  });
});

describe("quadrantOf", () => {
  const centres = { x: 10, y: 5 };

  it("names the corner a point sits in", () => {
    expect(quadrantOf({ x: 12, y: 7 }, centres)).toBe("high-high");
    expect(quadrantOf({ x: 2, y: 7 }, centres)).toBe("low-high");
    expect(quadrantOf({ x: 12, y: 1 }, centres)).toBe("high-low");
    expect(quadrantOf({ x: 2, y: 1 }, centres)).toBe("low-low");
  });

  it("puts a point exactly on the line in the low half, not both", () => {
    expect(quadrantOf({ x: 10, y: 5 }, centres)).toBe("low-low");
  });
});
