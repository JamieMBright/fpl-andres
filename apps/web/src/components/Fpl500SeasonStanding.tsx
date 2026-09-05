import { useMemo, useState } from "react";

import {
  standingHistogram,
  type SeasonStandingRow,
  type StandingMetric,
} from "../state/fpl500-season-standing";
import { integer } from "../format";

/**
 * The cohort's live season, drawn as a distribution.
 *
 * Every one of the five hundred is equal by construction, so the x axis is
 * points or overall rank, never a name or an id. Bars count managers in each
 * interval; bin width is adjustable because points and ranks use very
 * different scales.
 */

const WIDTH = 560;
const HEIGHT = 200;
const PAD_LEFT = 46;
const PAD_RIGHT = 12;
const PAD_TOP = 10;
const PAD_BOTTOM = 22;
const POINT_BIN_DEFAULT = 5;
const RANK_BIN_DEFAULT = 1_000;

export function Fpl500SeasonStanding({
  rows,
}: {
  rows: readonly SeasonStandingRow[];
}) {
  const [metric, setMetric] = useState<StandingMetric>("points");
  const [pointsBinSize, setPointsBinSize] = useState(POINT_BIN_DEFAULT);
  const [rankBinSize, setRankBinSize] = useState(RANK_BIN_DEFAULT);
  const binSize = metric === "points" ? pointsBinSize : rankBinSize;
  const bins = useMemo(
    () => standingHistogram(rows, metric, binSize),
    [rows, metric, binSize],
  );
  const drawn = bins.reduce((total, bin) => total + bin.count, 0);

  if (bins.length === 0) {
    return (
      <p className="mono fpl500-season-standing-empty">
        No season standing captured yet.
      </p>
    );
  }

  const maximumCount = Math.max(1, ...bins.map((bin) => bin.count));
  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const columnWidth = plotWidth / bins.length;
  const barWidth = Math.max(1, columnWidth - Math.min(2, columnWidth * 0.15));
  const formatRange = (start: number, end: number) =>
    metric === "points"
      ? `${integer.format(start)}–${integer.format(end)} pts`
      : `${integer.format(start)}–${integer.format(end)}`;

  return (
    <div className="fpl500-season-standing">
      <fieldset className="fpl500-metric-choice">
        <legend>Measure</legend>
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
      <label className="fpl500-standing-bin-control">
        <span>
          Bin size
          <output>
            {integer.format(binSize)} {metric === "points" ? "points" : "ranks"}
          </output>
        </span>
        <input
          aria-label="Bin size"
          max={metric === "points" ? 20 : 2_000_000}
          min={metric === "points" ? 1 : 1_000}
          onChange={(event) => {
            const value = Number(event.target.value);
            if (metric === "points") setPointsBinSize(value);
            else setRankBinSize(value);
          }}
          step={metric === "points" ? 1 : 1_000}
          type="range"
          value={binSize}
        />
      </label>
      <svg
        aria-label={`${metric === "points" ? "Total points" : "Overall rank"} histogram, managers per bin`}
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
      >
        <line
          className="fpl500-season-standing-axis-line"
          x1={PAD_LEFT}
          x2={WIDTH - PAD_RIGHT}
          y1={PAD_TOP + plotHeight}
          y2={PAD_TOP + plotHeight}
        />
        <line
          className="fpl500-season-standing-axis-line"
          x1={PAD_LEFT}
          x2={PAD_LEFT}
          y1={PAD_TOP}
          y2={PAD_TOP + plotHeight}
        />
        {bins.map((bin, index) => {
          const height = (bin.count / maximumCount) * plotHeight;
          return (
            <rect
              className="fpl500-standing-bin"
              data-count={bin.count}
              height={height}
              key={bin.start}
              width={barWidth}
              x={PAD_LEFT + index * columnWidth}
              y={PAD_TOP + plotHeight - height}
            >
              <title>
                {formatRange(bin.start, bin.end)}: {integer.format(bin.count)}{" "}
                managers
              </title>
            </rect>
          );
        })}
        <text
          className="fpl500-season-standing-axis"
          x={PAD_LEFT}
          y={HEIGHT - 4}
        >
          {formatRange(bins[0]!.start, bins[0]!.end)}
        </text>
        <text
          className="fpl500-season-standing-axis"
          textAnchor="end"
          x={WIDTH - PAD_RIGHT}
          y={HEIGHT - 4}
        >
          {formatRange(bins.at(-1)!.start, bins.at(-1)!.end)}
        </text>
        <text
          className="fpl500-season-standing-axis"
          textAnchor="end"
          x={PAD_LEFT - 6}
          y={PAD_TOP + 8}
        >
          {integer.format(maximumCount)}
        </text>
        <text
          className="fpl500-season-standing-axis"
          textAnchor="end"
          x={PAD_LEFT - 6}
          y={PAD_TOP + plotHeight}
        >
          0
        </text>
      </svg>
      <p className="fpl500-standing-axis-title">Managers per bin</p>
      {metric === "rank" ? (
        <p className="mono fpl500-note">The first bin is the top 1k.</p>
      ) : null}
      <p className="mono fpl500-note">
        {drawn} of the five hundred, all equal. Each bar is the number of
        managers inside that {metric === "points" ? "points" : "rank"} interval.
      </p>
    </div>
  );
}
