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

export function sweetSpot(
  players: readonly AnalysisPlayer[],
  x: Metric,
  y: Metric,
): SweetSpot | null {
  const points = players
    .map((player) => ({
      player,
      x: x.value(player),
      y: y.value(player),
    }))
    .filter(
      (point): point is { player: AnalysisPlayer; x: number; y: number } =>
        point.x !== null && point.y !== null,
    );
  if (points.length < MINIMUM_PLAYERS) return null;

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
  if (inside.length < 3) return null;

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
    centreX,
    centreY,
    radiusX: radiusX || Math.abs(centreX) * 0.05 || 1,
    radiusY: radiusY || Math.abs(centreY) * 0.05 || 1,
    codes: inside.map((point) => point.player.code),
    caption:
      `${String(inside.length)} players in the top fifth of both axes: ` +
      `${better(x)} ${x.label.toLowerCase()} and ${better(y)} ${y.label.toLowerCase()} ` +
      `are both the good direction, so this corner is where the value is.`,
  };
}

/**
 * The best-available curve: nobody sits beyond it on both axes at once.
 *
 * Every point on it is a player no other player beats outright. Anyone below
 * the line is dominated — there is someone at least as good on both counts —
 * and choosing them means paying for something the chart is not showing.
 */
export function frontier(
  players: readonly AnalysisPlayer[],
  x: Metric,
  y: Metric,
): { x: number; y: number }[] {
  const points = players
    .map((player) => ({ x: x.value(player), y: y.value(player) }))
    .filter(
      (point): point is { x: number; y: number } =>
        point.x !== null && point.y !== null,
    );
  if (points.length < 4) return [];

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
      kept.push(point);
    }
  }
  return kept.reverse();
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
