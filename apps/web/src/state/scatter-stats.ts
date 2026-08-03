/**
 * The arithmetic behind the reference lines and the trend line.
 *
 * Kept out of the component so the numbers can be checked without rendering
 * anything, and so a quadrant claim on the page is a claim about a function
 * with tests rather than about a piece of JSX.
 */

export type CentreMode = "median" | "mean";

export interface Point {
  x: number;
  y: number;
}

export interface Fit {
  slope: number;
  intercept: number;
  /** Share of the variance the line explains. Shown, never hidden. */
  r2: number;
}

export type Quadrant = "high-high" | "high-low" | "low-high" | "low-low";

/**
 * The middle of a set of values.
 *
 * Median by default because a handful of elite attackers pull the mean above
 * most of the pool, and a quadrant boundary drawn there would put almost
 * everyone in the same corner.
 */
export function centre(
  values: readonly number[],
  mode: CentreMode,
): number | null {
  if (values.length === 0) return null;
  if (mode === "mean") {
    return values.reduce((total, value) => total + value, 0) / values.length;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[middle]!
    : (sorted[middle - 1]! + sorted[middle]!) / 2;
}

/**
 * Ordinary least squares through the plotted points.
 *
 * This is a description of the pack, not a model of anything. A player above
 * the line returned more than players at his x usually do; that is all it says,
 * and `r2` is published beside it so a line through noise can be seen for what
 * it is.
 */
export function leastSquaresFit(points: readonly Point[]): Fit | null {
  if (points.length < 2) return null;

  const count = points.length;
  let sumX = 0;
  let sumY = 0;
  for (const point of points) {
    sumX += point.x;
    sumY += point.y;
  }
  const meanX = sumX / count;
  const meanY = sumY / count;

  let covariance = 0;
  let varianceX = 0;
  for (const point of points) {
    const dx = point.x - meanX;
    covariance += dx * (point.y - meanY);
    varianceX += dx * dx;
  }
  // Every point on the same x: there is no slope to report, and zero would draw
  // a horizontal line through a vertical stack.
  if (varianceX === 0) return null;

  const slope = covariance / varianceX;
  const intercept = meanY - slope * meanX;

  let residualSquares = 0;
  let totalSquares = 0;
  for (const point of points) {
    residualSquares += (point.y - (slope * point.x + intercept)) ** 2;
    totalSquares += (point.y - meanY) ** 2;
  }

  return {
    slope,
    intercept,
    r2: totalSquares === 0 ? 1 : 1 - residualSquares / totalSquares,
  };
}

/** How far above the pack a point sits. Negative is below. */
export function residualOf(point: Point, fit: Fit): number {
  return point.y - (fit.slope * point.x + fit.intercept);
}

/** Strictly greater, so a point on the line lands in exactly one quadrant. */
export function quadrantOf(point: Point, centres: Point): Quadrant {
  const high = point.x > centres.x;
  const tall = point.y > centres.y;
  if (high && tall) return "high-high";
  if (high) return "high-low";
  if (tall) return "low-high";
  return "low-low";
}
