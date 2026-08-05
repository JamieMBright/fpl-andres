import type { Metric } from "./analysis-metrics";
import type { AnalysisPlayer } from "./analysis-pool";

/**
 * Where the good players are, drawn as a ring.
 *
 * Every metric declares which end of it is the good one, so the chart already
 * knows which corner is desirable without anyone naming it. This finds the
 * players who are in the top slice of *both* axes and rings them, so the eye
 * goes to the corner that matters rather than to whichever dot is biggest.
 */

export interface SweetSpot {
  /** Centre and radii in data units, before any scale is applied. */
  centreX: number;
  centreY: number;
  radiusX: number;
  radiusY: number;
  /** Player codes inside the ring, so the table can agree with the picture. */
  codes: number[];
  /** What the ring is claiming, in one line. */
  caption: string;
}

/**
 * A drawn overlay, or the reason there is not one.
 *
 * The ring used to return `null` for four different situations and the chart
 * drew nothing for all of them, so a reader who ticked the box saw the box tick
 * and the chart not move. An overlay that cannot be drawn has to say so.
 */
export interface Overlay<T> {
  drawn: T | null;
  reason: string | null;
}

/** The slice of each axis counted as "the good end". */
const STANDOUT_QUANTILE = 0.8;
/** Below this there is no distribution to speak of and a ring would be noise. */
const MINIMUM_PLAYERS = 12;
/** Padding so the ring encloses its members rather than clipping them. */
const MARGIN = 1.18;

function quantile(sorted: number[], fraction: number): number {
  if (sorted.length === 0) return 0;
  const index = Math.min(
    sorted.length - 1,
    Math.max(0, Math.round((sorted.length - 1) * fraction)),
  );
  return sorted[index] ?? 0;
}

/** True where the value is in the desirable tail of its own metric. */
function standsOut(
  value: number,
  cut: number,
  higherIsBetter: boolean,
): boolean {
  return higherIsBetter ? value >= cut : value <= cut;
}

/** "1 player" but "12 players". A count in prose has to read like prose. */
function players(count: number): string {
  return count === 1 ? "1 player is" : `${String(count)} players are`;
}

export function sweetSpot(
  players_: readonly AnalysisPlayer[],
  x: Metric,
  y: Metric,
): Overlay<SweetSpot> {
  const points = players_
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
        `Only ${players(points.length)} on these axes. ` +
        `A top fifth of fewer than ${String(MINIMUM_PLAYERS)} is not a corner, it is a handful of dots. ` +
        "Widen the ownership band or drop the minutes floor.",
    };
  }

  const xs = points.map((point) => point.x).sort((a, b) => a - b);
  const ys = points.map((point) => point.y).sort((a, b) => a - b);
  const xCut = quantile(
    xs,
    x.higherIsBetter ? STANDOUT_QUANTILE : 1 - STANDOUT_QUANTILE,
  );
  const yCut = quantile(
    ys,
    y.higherIsBetter ? STANDOUT_QUANTILE : 1 - STANDOUT_QUANTILE,
  );

  const inside = points.filter(
    (point) =>
      standsOut(point.x, xCut, x.higherIsBetter) &&
      standsOut(point.y, yCut, y.higherIsBetter),
  );
  // One player is a dot, not a region, and two is a line.
  if (inside.length < 3) {
    return {
      drawn: null,
      reason:
        `Only ${players(inside.length)} in the top fifth of both ` +
        `${x.label.toLowerCase()} and ${y.label.toLowerCase()} at once, so there is no corner to ring. ` +
        "The two axes disagree about who is good, which is itself the finding.",
    };
  }

  const centreX =
    inside.reduce((total, point) => total + point.x, 0) / inside.length;
  const centreY =
    inside.reduce((total, point) => total + point.y, 0) / inside.length;
  const radiusX =
    Math.max(...inside.map((point) => Math.abs(point.x - centreX))) * MARGIN;
  const radiusY =
    Math.max(...inside.map((point) => Math.abs(point.y - centreY))) * MARGIN;

  const better = (metric: Metric) => (metric.higherIsBetter ? "more" : "less");

  return {
    drawn: {
      centreX,
      centreY,
      radiusX: radiusX || Math.abs(centreX) * 0.05 || 1,
      radiusY: radiusY || Math.abs(centreY) * 0.05 || 1,
      codes: inside.map((point) => point.player.code),
      caption:
        `${String(inside.length)} players in the top fifth of both axes: ` +
        `${better(x)} ${x.label.toLowerCase()} and ${better(y)} ${y.label.toLowerCase()} ` +
        `are both the good direction, so this corner is where the value is.`,
    },
    reason: null,
  };
}

/** Points on the smoothed curve, and who cleared it. */
export interface Frontier {
  /** The non-dominated set, in plotting order. Kept for the tooltip. */
  hull: { x: number; y: number }[];
  /** The smoothed curve, sampled densely enough to draw as one stroke. */
  curve: { x: number; y: number }[];
  /** Players strictly beyond the smoothed curve, best first. */
  pioneers: { code: number; name: string; margin: number }[];
}

/** Fewer than this and a local regression is fitting noise to noise. */
const MINIMUM_HULL = 4;
/** Share of the frontier's x-range inside one local fit. */
const SPAN = 0.55;
/** Sampled positions along the curve. Enough that the polyline reads as smooth. */
const SAMPLES = 48;

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
 * The best-available curve, smoothed, so somebody can be above it.
 *
 * The non-dominated set is a staircase: it passes through every extreme point
 * by construction, so nobody is ever beyond it and the line says only "these
 * players exist". Joining those points dot to dot draws that staircase and
 * calls it a frontier.
 *
 * A local regression through the same points is a curve the pool as a whole
 * supports, and the players who clear it are the ones doing something the rest
 * of the distribution does not explain. Those are the pioneers, and they are
 * what a reader is actually looking for.
 */
export function frontier(
  players_: readonly AnalysisPlayer[],
  x: Metric,
  y: Metric,
): Overlay<Frontier> {
  const points = players_
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
        `Only ${players(points.length)} on these axes, which is too few to say ` +
        "what the best available looks like.",
    };
  }

  // Walk along the x-axis in the good direction, keeping anyone who improves on
  // the best y seen so far. What survives is the non-dominated set.
  const along = [...points].sort((left, right) =>
    x.higherIsBetter ? left.x - right.x : right.x - left.x,
  );
  const kept: { x: number; y: number }[] = [];
  let best = y.higherIsBetter ? -Infinity : Infinity;
  // Backwards, because the best x is at the end of a run sorted the good way.
  for (let index = along.length - 1; index >= 0; index -= 1) {
    const point = along[index];
    if (!point) continue;
    const better = y.higherIsBetter ? point.y > best : point.y < best;
    if (better) {
      best = point.y;
      kept.push({ x: point.x, y: point.y });
    }
  }
  const hull = kept.reverse();
  if (hull.length < MINIMUM_HULL) {
    return {
      drawn: null,
      reason:
        `Only ${players(hull.length)} unbeaten on both axes, so there is nothing to ` +
        "smooth. One or two dominant players is a fact about them, not a curve.",
    };
  }

  const lowX = Math.min(...hull.map((point) => point.x));
  const highX = Math.max(...hull.map((point) => point.x));
  const bandwidth = (highX - lowX) * SPAN;
  const curve = Array.from({ length: SAMPLES }, (_, index) => {
    const at = lowX + ((highX - lowX) * index) / (SAMPLES - 1);
    return { x: at, y: localFit(hull, at, bandwidth) };
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

  return { drawn: { hull, curve, pioneers }, reason: null };
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
  players: readonly AnalysisPlayer[],
  metric: Metric,
  count: number,
): Bin[] {
  const values = players
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
