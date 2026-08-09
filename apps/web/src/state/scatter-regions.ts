import type { Metric } from "./analysis-metrics";
import type { AnalysisPlayer } from "./analysis-pool";

/**
 * The overlays the chart can draw over the cloud.
 *
 * The two originals were shapes fitted to individual players, and both were
 * wrong for the same reason. The ring enclosed whoever was in the top fifth of
 * both axes, which on uncorrelated axes is nobody, so the checkbox did nothing.
 * The frontier joined the non-dominated set dot to dot, which by construction
 * passes through the single highest x and the single highest y — usually two
 * anomalies — and guarantees nobody can be above it.
 *
 * Neither was a statement about the distribution. What replaced them is
 * background shading read straight off the reference lines, and a curve fitted
 * to the spread inside x-slices rather than to whoever is furthest out.
 */

/**
 * A drawn overlay, or the reason there is not one.
 *
 * Returning `null` for four different situations and drawing nothing for all of
 * them is indistinguishable from a broken checkbox.
 */
export interface Overlay<T> {
  drawn: T | null;
  reason: string | null;
}

/** "1 player" but "12 players". A count in prose has to read like prose. */
function players(count: number): string {
  return count === 1 ? "1 player is" : `${String(count)} players are`;
}

/** Points on the curve, and who cleared it. */
export interface Frontier {
  /** The curve, sampled densely enough to draw as one stroke. */
  curve: { x: number; y: number }[];
  /** The slice centres the curve was fitted to. */
  bins: { x: number; y: number; members: number }[];
  /** Players beyond the curve, furthest first. */
  pioneers: { code: number; name: string; margin: number }[];
  /** How many standard deviations above the local mean the curve sits. */
  sigma: number;
}

/** Below this there is no distribution to describe. */
const MINIMUM_PLAYERS = 12;
/** Slices of the x-range the spread is measured inside. */
const BIN_COUNT = 10;
/** A mean and a standard deviation over fewer than this is a rumour. */
const MINIMUM_PER_BIN = 6;
/** Usable slices needed before a curve can be drawn through them. */
const MINIMUM_BINS = 3;
/** How far above the local mean the bar sits. Two is the conventional outlier. */
const SIGMA = 2;
/**
 * Share of the x-range inside one local fit. At 0.55 the curve chased each
 * slice and read as noise; a wider window is what makes it a description of
 * the pool rather than a join-the-dots of ten bins.
 */
const SPAN = 0.9;
/** Sampled positions along the curve. Enough that the polyline reads as smooth. */
const SAMPLES = 64;

/** Tricube, the standard LOESS weight: 1 at the centre, 0 at the bandwidth. */
function tricube(distance: number, bandwidth: number): number {
  if (bandwidth <= 0) return distance === 0 ? 1 : 0;
  const ratio = Math.abs(distance) / bandwidth;
  if (ratio >= 1) return 0;
  return (1 - ratio ** 3) ** 3;
}

/** Weighted least squares at one position, falling back to the weighted mean. */
function localFit(
  points: readonly { x: number; y: number }[],
  at: number,
  bandwidth: number,
): number {
  let sumW = 0;
  let sumWX = 0;
  let sumWY = 0;
  let sumWXX = 0;
  let sumWXY = 0;
  for (const point of points) {
    const weight = tricube(point.x - at, bandwidth);
    if (weight === 0) continue;
    sumW += weight;
    sumWX += weight * point.x;
    sumWY += weight * point.y;
    sumWXX += weight * point.x * point.x;
    sumWXY += weight * point.x * point.y;
  }
  if (sumW === 0) {
    // Outside every bandwidth: hold the nearest observation rather than invent.
    let nearest = points[0]!;
    for (const point of points) {
      if (Math.abs(point.x - at) < Math.abs(nearest.x - at)) nearest = point;
    }
    return nearest.y;
  }
  const meanX = sumWX / sumW;
  const meanY = sumWY / sumW;
  const variance = sumWXX / sumW - meanX * meanX;
  if (variance <= 1e-12) return meanY;
  const covariance = sumWXY / sumW - meanX * meanY;
  const slope = covariance / variance;
  return meanY + slope * (at - meanX);
}

/**
 * What "unusually good for his x" looks like, as a curve.
 *
 * The x-range is cut into equal slices and the mean and standard deviation of y
 * are measured inside each. The curve runs two standard deviations above the
 * mean in the good direction, so it describes the spread of the pool rather
 * than the position of its two furthest members. A slice holding too few
 * players is dropped rather than given a standard deviation it has not earned.
 *
 * Roughly one player in forty clears a two-sigma bar under a normal spread, and
 * these distributions have fatter tails than that, so the crossing set stays
 * small. Those are the pioneers: doing something at their price, minutes or
 * defensive load that the rest of the pool at the same x does not.
 */
export function frontier(
  pool: readonly AnalysisPlayer[],
  x: Metric,
  y: Metric,
): Overlay<Frontier> {
  const points = pool
    .map((player) => ({
      player,
      x: x.value(player),
      y: y.value(player),
    }))
    .filter(
      (point): point is { player: AnalysisPlayer; x: number; y: number } =>
        point.x !== null && point.y !== null,
    );
  if (points.length < MINIMUM_PLAYERS) {
    return {
      drawn: null,
      reason:
        `Only ${players(points.length)} on these axes, which is too few to measure ` +
        "a spread inside.",
    };
  }

  const lowX = Math.min(...points.map((point) => point.x));
  const highX = Math.max(...points.map((point) => point.x));
  if (highX <= lowX) {
    return {
      drawn: null,
      reason:
        "Every player reads the same on this x-axis, so there are no slices to " +
        "compare across.",
    };
  }

  const width = (highX - lowX) / BIN_COUNT;
  const buckets: number[][] = Array.from({ length: BIN_COUNT }, () => []);
  for (const point of points) {
    const index = Math.min(BIN_COUNT - 1, Math.floor((point.x - lowX) / width));
    buckets[index]?.push(point.y);
  }

  const bins: { x: number; y: number; members: number }[] = [];
  for (const [index, values] of buckets.entries()) {
    if (values.length < MINIMUM_PER_BIN) continue;
    const mean =
      values.reduce((total, value) => total + value, 0) / values.length;
    const deviation = Math.sqrt(
      values.reduce((total, value) => total + (value - mean) ** 2, 0) /
        values.length,
    );
    bins.push({
      x: lowX + width * (index + 0.5),
      y: y.higherIsBetter ? mean + SIGMA * deviation : mean - SIGMA * deviation,
      members: values.length,
    });
  }

  if (bins.length < MINIMUM_BINS) {
    return {
      drawn: null,
      reason:
        `Only ${String(bins.length)} of ${String(BIN_COUNT)} slices of this x-axis hold ` +
        `${String(MINIMUM_PER_BIN)} players or more, so there is no spread to measure ` +
        "across it. Widen the ownership band or drop the minutes floor.",
    };
  }

  const firstBin = bins[0]!;
  const lastBin = bins.at(-1)!;
  // Drawn across every x that has a player on it, not just between the first
  // and last usable bin centre. Stopping at the centres left the line hanging
  // in mid-air with dots either side of both ends.
  const bandwidth = Math.max(
    (lastBin.x - firstBin.x) * SPAN,
    (highX - lowX) * SPAN,
  );
  const curve = Array.from({ length: SAMPLES }, (_, index) => {
    const at = lowX + ((highX - lowX) * index) / (SAMPLES - 1);
    return { x: at, y: localFit(bins, at, bandwidth) };
  });

  const above = (value: number, reference: number) =>
    y.higherIsBetter ? value - reference : reference - value;

  const pioneers = points
    .map((point) => ({
      code: point.player.code,
      name: point.player.name,
      margin: above(point.y, interpolate(curve, point.x)),
    }))
    .filter((entry) => entry.margin > 0)
    .sort((left, right) => right.margin - left.margin);

  return { drawn: { curve, bins, pioneers, sigma: SIGMA }, reason: null };
}

/** The curve's y at an arbitrary x, clamped to its ends. */
function interpolate(
  curve: readonly { x: number; y: number }[],
  at: number,
): number {
  const first = curve[0]!;
  const last = curve.at(-1)!;
  if (at <= first.x) return first.y;
  if (at >= last.x) return last.y;
  for (let index = 1; index < curve.length; index += 1) {
    const right = curve[index]!;
    if (right.x < at) continue;
    const left = curve[index - 1]!;
    const width = right.x - left.x;
    if (width <= 0) return right.y;
    return left.y + ((at - left.x) / width) * (right.y - left.y);
  }
  return last.y;
}

export interface Bin {
  /** Inclusive lower edge in data units. */
  from: number;
  /** Exclusive upper edge, except the last which is inclusive. */
  to: number;
  label: string;
}

/**
 * Teletext's own ramp, dark to bright, so a higher bin reads as a hotter mark.
 * Shared with the legend, because a key that disagrees with the chart is worse
 * than no key at all.
 */
export const BIN_RAMP = [
  "#0a1a4d",
  "#0d3b8c",
  "#1f7ac2",
  "#22a6a6",
  "#2fb84a",
  "#c8d400",
  "#ff8c1a",
  "#ff3b3b",
];

/**
 * Equal-width bins across the observed range.
 *
 * Equal width rather than equal count, because the reader is being shown a
 * colour ramp and expects the steps to mean the same thing all the way along.
 */
export function binsFor(
  pool: readonly AnalysisPlayer[],
  metric: Metric,
  count: number,
): Bin[] {
  const values = pool
    .map((player) => metric.value(player))
    .filter((value): value is number => value !== null);
  if (values.length === 0) return [];

  const low = Math.min(...values);
  const high = Math.max(...values);
  if (high === low) return [];

  const width = (high - low) / count;
  return Array.from({ length: count }, (_, index) => {
    const from = low + width * index;
    const to = index === count - 1 ? high : from + width;
    return {
      from,
      to,
      label: `${metric.format(from)}\u2013${metric.format(to)}`,
    };
  });
}

/** Which bin a player falls in, or null where the metric does not apply. */
export function binOf(
  player: AnalysisPlayer,
  metric: Metric,
  bins: readonly Bin[],
): number | null {
  const value = metric.value(player);
  if (value === null || bins.length === 0) return null;
  const found = bins.findIndex((bin) => value >= bin.from && value <= bin.to);
  return found === -1 ? null : found;
}
