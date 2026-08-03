import { METRICS, metric, type Metric } from "./analysis-metrics";
import type { AnalysisPlayer } from "./analysis-pool";
import type { ScatterView } from "./scatter-view";

/**
 * Two to four players, put beside each other with the differences first.
 *
 * A comparison that lists twelve numbers in a fixed order buries the one that
 * matters. These rows are ordered by how far apart the chosen players actually
 * are on each measure, scored against the spread of the whole pool so that
 * "twice the expected involvement" outranks "forty more minutes".
 *
 * The order of the players is the order the chart already implies: whoever sits
 * furthest into the good corner of the two axes on screen goes first. That is a
 * claim the reader can check by looking at the chart, not a secret ranking.
 */

export interface CompareRow {
  id: string;
  label: string;
  explains: string;
  /** 0 to 1: how far apart the compared players are, against the pool's range. */
  impact: number;
  higherIsBetter: boolean;
  /** Aligned with `players`. Null where the player has no reading. */
  values: (number | null)[];
  formatted: string[];
  /** Index of the best value, or -1 when nobody leads. */
  leader: number;
}

export interface Comparison {
  players: AnalysisPlayer[];
  rows: CompareRow[];
}

// Always compared, on top of whatever the axes are set to. These are the
// questions a shortlist is settled on regardless of what is being plotted.
const ALWAYS = [
  "pointsPer90",
  "xGIPer90",
  "defconPer90",
  "minutes",
  "price",
  "ownership",
  "pointsPerMillion",
  "bonus",
];

function range(
  values: (number | null)[],
): { low: number; high: number } | null {
  const real = values.filter((value): value is number => value !== null);
  if (real.length === 0) return null;
  return { low: Math.min(...real), high: Math.max(...real) };
}

/** Where a player sits in the good corner of the two plotted axes, 0 to 1. */
function cornerScore(
  player: AnalysisPlayer,
  pool: readonly AnalysisPlayer[],
  x: Metric,
  y: Metric,
): number {
  const position = (chosen: Metric): number => {
    const value = chosen.value(player);
    if (value === null) return 0;
    const bounds = range(pool.map((entry) => chosen.value(entry)));
    if (!bounds || bounds.high === bounds.low) return 0.5;
    const ratio = (value - bounds.low) / (bounds.high - bounds.low);
    return chosen.higherIsBetter ? ratio : 1 - ratio;
  };
  return position(x) * position(y);
}

export function comparePinned(
  chosen: readonly AnalysisPlayer[],
  pool: readonly AnalysisPlayer[],
  view: ScatterView,
): Comparison {
  const x = metric(view.x);
  const y = metric(view.y);

  const players =
    x && y
      ? [...chosen].sort(
          (left, right) =>
            cornerScore(right, pool, x, y) - cornerScore(left, pool, x, y),
        )
      : [...chosen];

  const wanted = [
    ...new Set([view.x, view.y, ...(view.size ? [view.size] : []), ...ALWAYS]),
  ];

  const rows: CompareRow[] = [];
  for (const id of wanted) {
    const definition = METRICS.find((entry) => entry.id === id);
    if (!definition) continue;

    const values = players.map((player) => definition.value(player));
    const spread = range(values);
    const poolSpread = range(pool.map((player) => definition.value(player)));
    if (!spread || !poolSpread) continue;

    // Against the pool's own range, so a metric's units do not decide the
    // order. A measure nobody in the pool varies on cannot separate anybody.
    const impact =
      poolSpread.high === poolSpread.low
        ? 0
        : (spread.high - spread.low) / (poolSpread.high - poolSpread.low);

    const target = definition.higherIsBetter ? spread.high : spread.low;
    const leading = values.findIndex((value) => value === target);
    const tied = values.filter((value) => value === target).length > 1;

    rows.push({
      id,
      label: definition.label,
      explains: definition.explains,
      impact,
      higherIsBetter: definition.higherIsBetter,
      values,
      formatted: values.map((value) =>
        value === null ? "—" : definition.format(value),
      ),
      leader: tied ? -1 : leading,
    });
  }

  rows.sort((left, right) => right.impact - left.impact);
  return { players, rows };
}
