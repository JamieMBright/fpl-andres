import type { Metric } from "./analysis-metrics";
import type { PlottedPlayer, Selection } from "./scatter-select";
import { leastSquaresFit } from "./scatter-stats";
import type { ScatterView } from "./scatter-view";

/**
 * How to read the chart that is actually on screen.
 *
 * Not a fixed blurb. A scatter of two metrics the reader chose has no meaning
 * until someone says which corner is good and what the cloud is doing, and
 * expecting them to work that out from the axis titles is how a chart becomes
 * decoration. Everything here is derived from the plotted points, so it cannot
 * describe a chart other than the one being shown.
 */

export interface Reading {
  /** Which corner is the good one, in the words of the chosen metrics. */
  corner: string;
  /** What the cloud does, or null when there is no line to describe. */
  relationship: string | null;
  /** The clearest single player on these axes, or null when none stands out. */
  standout: string | null;
  /** What the third encoding is saying. */
  size: string | null;
}

function best(metric: Metric): "right" | "left" {
  return metric.higherIsBetter ? "right" : "left";
}

function vertical(metric: Metric): "top" | "bottom" {
  return metric.higherIsBetter ? "top" : "bottom";
}

/** Strength of a correlation, in words rather than a number nobody calibrates. */
function strength(r: number): string {
  const magnitude = Math.abs(r);
  if (magnitude < 0.15) return "almost nothing";
  if (magnitude < 0.35) return "a weak";
  if (magnitude < 0.6) return "a moderate";
  return "a strong";
}

/**
 * The player furthest into the good corner, measured on both axes at once.
 *
 * Ranked on the product of each axis position within its own range, so neither
 * metric's units decide the winner.
 */
function standoutOf(selection: Selection): PlottedPlayer | null {
  const { points, x, y } = selection;
  if (points.length < 4) return null;

  const spread = (values: number[]) => {
    const low = Math.min(...values);
    const high = Math.max(...values);
    return high === low ? null : { low, span: high - low };
  };
  const xs = spread(points.map((point) => point.x));
  const ys = spread(points.map((point) => point.y));
  if (!xs || !ys) return null;

  let leader: PlottedPlayer | null = null;
  let bestScore = -Infinity;
  for (const point of points) {
    if (!point.matched) continue;
    const px = (point.x - xs.low) / xs.span;
    const py = (point.y - ys.low) / ys.span;
    const score =
      (x.higherIsBetter ? px : 1 - px) * (y.higherIsBetter ? py : 1 - py);
    if (score > bestScore) {
      bestScore = score;
      leader = point;
    }
  }
  return leader;
}

export function readChart(selection: Selection, view: ScatterView): Reading {
  const { x, y, size, points } = selection;

  const corner =
    `The ${vertical(y)} ${best(x)} corner is the good one: ` +
    `${x.higherIsBetter ? "more" : "less"} ${x.label} and ` +
    `${y.higherIsBetter ? "more" : "less"} ${y.label}.`;

  // Fitted here rather than taken from the selection, which only fits a line
  // when the trend toggle is on. `r2` has no sign; the slope carries it.
  const fit = leastSquaresFit(points);
  const r = fit ? Math.sign(fit.slope) * Math.sqrt(fit.r2) : null;

  const relationship =
    r === null
      ? null
      : `Across these ${points.length.toString()} players there is ${strength(r)} ` +
        `${r >= 0 ? "positive" : "negative"} relationship between the two ` +
        `(r = ${r.toFixed(2)}). ` +
        (Math.abs(r) < 0.35
          ? "They are close to independent, so a player can be good at one without being good at the other — which is what makes the corners worth looking at."
          : r >= 0
            ? "They largely move together, so the interesting players are the ones sitting well above the line rather than the ones furthest along it."
            : "They pull against each other, so a player high on both is doing something the rest of the league is not.");

  const leader = standoutOf(selection);
  const standout = leader
    ? `${leader.player.name} (${leader.player.club}) sits furthest into it, at ` +
      `${x.format(leader.x)} and ${y.format(leader.y)}.`
    : null;

  const sizeNote = size
    ? `Each disc is sized by ${size.label.toLowerCase()}, by area. ` +
      `Only players owned by between ${String(view.ownedFrom)}% and ` +
      `${String(view.ownedTo)}% are drawn, and the ones ringed in green are in ` +
      `the good corner of both axes.`
    : `Only players owned by between ${String(view.ownedFrom)}% and ` +
      `${String(view.ownedTo)}% are drawn, and the ones ringed in green are in ` +
      `the good corner of both axes.`;

  return { corner, relationship, standout, size: sizeNote };
}
