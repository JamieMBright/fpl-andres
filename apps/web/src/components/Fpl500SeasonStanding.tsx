import { useMemo, useState } from "react";

import {
  sortedStanding,
  type SeasonStandingRow,
  type StandingMetric,
} from "../state/fpl500-season-standing";

/**
 * The cohort's live season, drawn as one curve.
 *
 * Every one of the five hundred is equal by construction, so the x axis is
 * only a sorted position, never a name or an id. Toggling the metric changes
 * what "best" means — the lowest overall rank, or the most points — and
 * re-sorts the same five hundred points around it.
 */

const WIDTH = 560;
const HEIGHT = 200;
const PAD_LEFT = 46;
const PAD_RIGHT = 12;
const PAD_TOP = 10;
const PAD_BOTTOM = 22;

export function Fpl500SeasonStanding({
  rows,
}: {
  rows: readonly SeasonStandingRow[];
}) {
  const [metric, setMetric] = useState<StandingMetric>("points");
  const sorted = useMemo(() => sortedStanding(rows, metric), [rows, metric]);

  if (sorted.length === 0) {
    return (
      <p className="mono fpl500-season-standing-empty">
        No season standing captured yet.
      </p>
    );
  }

  const values = sorted.map((row) =>
    metric === "points" ? row.totalPoints : (row.overallRank ?? 0),
  );
  const maximum = Math.max(1, ...values);
  const minimum = Math.min(...values);
  const span = Math.max(1, maximum - minimum);
  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const step = sorted.length > 1 ? plotWidth / (sorted.length - 1) : 0;
  // Points, higher is better, drawn rising left to right (best on the left).
  // Rank, lower is better: the same left-to-right order, but the axis reads
  // downward, so the line still opens best-to-worst without flipping x.
  const path = values
    .map((value, index) => {
      const x = PAD_LEFT + step * index;
      const fraction = (value - minimum) / span;
      const y =
        metric === "points"
          ? PAD_TOP + plotHeight * (1 - fraction)
          : PAD_TOP + plotHeight * fraction;
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  return (
    <div className="fpl500-season-standing">
      <fieldset className="fpl500-metric-choice">
        <legend>Sort by</legend>
        <label>
          <input
            checked={metric === "points"}
            name="fpl500-season-metric"
            onChange={() => setMetric("points")}
            type="radio"
          />
          <span>Total points</span>
        </label>
        <label>
          <input
            checked={metric === "rank"}
            name="fpl500-season-metric"
            onChange={() => setMetric("rank")}
            type="radio"
          />
          <span>Overall rank</span>
        </label>
      </fieldset>
      <svg
        aria-hidden="true"
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
      >
        <path className="fpl500-season-standing-line" d={path} fill="none" />
        <text
          className="fpl500-season-standing-axis"
          x={PAD_LEFT}
          y={HEIGHT - 4}
        >
          Best
        </text>
        <text
          className="fpl500-season-standing-axis"
          textAnchor="end"
          x={WIDTH - PAD_RIGHT}
          y={HEIGHT - 4}
        >
          Worst
        </text>
        <text
          className="fpl500-season-standing-axis"
          textAnchor="end"
          x={PAD_LEFT - 6}
          y={PAD_TOP + 8}
        >
          {metric === "points" ? Math.round(maximum) : Math.round(minimum)}
        </text>
        <text
          className="fpl500-season-standing-axis"
          textAnchor="end"
          x={PAD_LEFT - 6}
          y={PAD_TOP + plotHeight}
        >
          {metric === "points" ? Math.round(minimum) : Math.round(maximum)}
        </text>
      </svg>
      <p className="mono fpl500-note">
        {sorted.length} of the five hundred, all equal, sorted only to draw the
        curve.
      </p>
    </div>
  );
}
