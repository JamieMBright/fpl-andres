import { useId } from "react";

/**
 * Small charts for the calibration page, drawn by hand in SVG.
 *
 * The page was five tables. A table is the right shape for looking a number up
 * and the wrong one for the question this page answers, which is always a
 * comparison: is this better than that, and by how much, and did it hold across
 * seasons. Nine captaincy policies across four seasons is thirty-six cells that
 * nobody reads and no one can rank by eye.
 *
 * No charting library, for the same two reasons as the scatter: the lazy-chunk
 * budget is 32 kB gzipped, and every mark here carries a label as well as a
 * length because DESIGN.md does not let position be the only encoding.
 */

const BAR_HEIGHT = 22;
const BAR_GAP = 6;
const LABEL_WIDTH = 150;
const VALUE_WIDTH = 54;
const TRACK_WIDTH = 220;

export interface BarDatum {
  label: string;
  value: number | null;
  /** Printed at the end of the bar. Falls back to the value at two places. */
  display?: string;
  /** Drawn as a separate rule across the track: the bar nobody reached. */
  reference?: number;
  /** Marks the row as this project's own, so the eye finds it first. */
  mine?: boolean;
}

export interface BarChartProps {
  title: string;
  /** What one unit of length means, said in words rather than implied. */
  caption: string;
  data: readonly BarDatum[];
  /** Higher is better unless this says otherwise. */
  higherIsBetter?: boolean;
  referenceLabel?: string;
}

/**
 * A ranked bar chart, sorted by the thing it is measuring.
 *
 * Sorted rather than alphabetical: the reader's question is "which is best",
 * and an alphabetical list makes them do the sort themselves.
 */
export function BarChart({
  title,
  caption,
  data,
  higherIsBetter = true,
  referenceLabel,
}: BarChartProps) {
  const titleId = useId();
  const measured = data.filter(
    (entry): entry is BarDatum & { value: number } => entry.value !== null,
  );
  if (measured.length === 0) {
    return (
      <figure className="calibration-chart">
        <figcaption>{title}</figcaption>
        <p className="calibration-empty">Not measured yet.</p>
      </figure>
    );
  }

  const references = data
    .map((entry) => entry.reference)
    .filter((value): value is number => value !== undefined);
  const ceiling = Math.max(
    ...measured.map((entry) => Math.abs(entry.value)),
    ...references,
  );
  const ordered = [...measured].sort((left, right) =>
    higherIsBetter ? right.value - left.value : left.value - right.value,
  );

  const height = ordered.length * (BAR_HEIGHT + BAR_GAP);
  const width = LABEL_WIDTH + TRACK_WIDTH + VALUE_WIDTH;
  const scale = (value: number) =>
    ceiling === 0 ? 0 : (Math.abs(value) / ceiling) * TRACK_WIDTH;

  return (
    <figure className="calibration-chart">
      <figcaption id={titleId}>{title}</figcaption>
      <svg
        className="calibration-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby={titleId}
      >
        {ordered.map((entry, index) => {
          const y = index * (BAR_HEIGHT + BAR_GAP);
          const length = scale(entry.value);
          return (
            <g key={entry.label}>
              <text
                className="calibration-label"
                x={LABEL_WIDTH - 8}
                y={y + BAR_HEIGHT * 0.72}
                textAnchor="end"
              >
                {entry.label}
              </text>
              <rect
                className="calibration-track"
                x={LABEL_WIDTH}
                y={y}
                width={TRACK_WIDTH}
                height={BAR_HEIGHT}
              />
              <rect
                className={
                  entry.mine
                    ? "calibration-bar calibration-bar-mine"
                    : "calibration-bar"
                }
                x={LABEL_WIDTH}
                y={y}
                width={length}
                height={BAR_HEIGHT}
              />
              {entry.reference === undefined ? null : (
                <line
                  className="calibration-reference"
                  x1={LABEL_WIDTH + scale(entry.reference)}
                  y1={y - 1}
                  x2={LABEL_WIDTH + scale(entry.reference)}
                  y2={y + BAR_HEIGHT + 1}
                />
              )}
              <text
                className="calibration-value"
                x={LABEL_WIDTH + TRACK_WIDTH + 6}
                y={y + BAR_HEIGHT * 0.72}
              >
                {entry.display ?? entry.value.toFixed(2)}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="calibration-caption">
        {caption}
        {referenceLabel && references.length > 0 ? ` ${referenceLabel}` : ""}
      </p>
    </figure>
  );
}

export interface IntervalDatum {
  label: string;
  /** The paired mean difference against the incumbent. */
  improvement: number;
  lower: number;
  upper: number;
  /** True only when the whole interval sits above zero. */
  better: boolean;
}

export interface IntervalChartProps {
  title: string;
  caption: string;
  data: readonly IntervalDatum[];
}

const INTERVAL_ROW = 24;
const INTERVAL_TRACK = 260;
const INTERVAL_LABEL = 150;
const INTERVAL_VALUE = 88;

/**
 * Dot-and-whisker against zero: does this rule actually beat the incumbent?
 *
 * The bar chart above ranks ten means, and a rank always produces a winner
 * whether or not one exists. This is the chart that can say no: any whisker
 * crossing the zero rule is a policy the evidence does not separate from the
 * projection, however far up the table it sorted. A whisker wholly on either
 * side is a result, and both sides are marked -- a rule measurably worse than
 * the projection is as much a finding as one measurably better.
 */
export function IntervalChart({ title, caption, data }: IntervalChartProps) {
  const titleId = useId();
  if (data.length === 0) {
    return (
      <figure className="calibration-chart">
        <figcaption>{title}</figcaption>
        <p className="calibration-empty">Not measured yet.</p>
      </figure>
    );
  }

  const reach = Math.max(
    ...data.flatMap((entry) => [
      Math.abs(entry.lower),
      Math.abs(entry.upper),
      Math.abs(entry.improvement),
    ]),
    0.001,
  );
  const ordered = [...data].sort(
    (left, right) => right.improvement - left.improvement,
  );
  const height = ordered.length * INTERVAL_ROW + 18;
  const width = INTERVAL_LABEL + INTERVAL_TRACK + INTERVAL_VALUE;
  const zero = INTERVAL_LABEL + INTERVAL_TRACK / 2;
  const x = (value: number) => zero + (value / reach) * (INTERVAL_TRACK / 2);

  return (
    <figure className="calibration-chart">
      <figcaption id={titleId}>{title}</figcaption>
      <svg
        className="calibration-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby={titleId}
      >
        <line
          className="calibration-zero"
          x1={zero}
          y1={0}
          x2={zero}
          y2={ordered.length * INTERVAL_ROW}
        />
        {ordered.map((entry, index) => {
          const y = index * INTERVAL_ROW + INTERVAL_ROW / 2;
          // A whole interval below zero is a result, not an absence of one, and
          // rendering it like an inconclusive row hides the only findings this
          // chart has produced.
          const worse = entry.upper < 0;
          const state = entry.better
            ? "better"
            : worse
              ? "worse"
              : "unresolved";
          return (
            <g key={entry.label}>
              <text
                className="calibration-label"
                x={INTERVAL_LABEL - 8}
                y={y + 4}
                textAnchor="end"
              >
                {entry.label}
              </text>
              <line
                className={`calibration-whisker calibration-whisker-${state}`}
                x1={x(entry.lower)}
                y1={y}
                x2={x(entry.upper)}
                y2={y}
              />
              <circle
                className={`calibration-dot calibration-dot-${state}`}
                cx={x(entry.improvement)}
                cy={y}
                r={3.5}
              />
              <text
                className="calibration-value"
                x={INTERVAL_LABEL + INTERVAL_TRACK + 6}
                y={y + 4}
              >
                {entry.improvement > 0 ? "+" : ""}
                {entry.improvement.toFixed(2)}
                {entry.better ? " \u2713" : worse ? " \u2717" : ""}
              </text>
            </g>
          );
        })}
        <text
          className="calibration-axis"
          x={zero}
          y={ordered.length * INTERVAL_ROW + 12}
          textAnchor="middle"
        >
          no difference
        </text>
      </svg>
      <p className="calibration-caption">{caption}</p>
    </figure>
  );
}

export interface SeasonSeries {
  label: string;
  points: readonly (number | null)[];
  mine?: boolean;
}
export interface SeasonLinesProps {
  title: string;
  caption: string;
  seasons: readonly string[];
  series: readonly SeasonSeries[];
}

const LINE_WIDTH = 420;
const LINE_HEIGHT = 150;
const LINE_PAD = { top: 12, right: 96, bottom: 26, left: 40 };

/**
 * One line per method across the seasons, so a lead can be seen to hold or not.
 *
 * A season-by-season table answers "what was the number in 2023-24". Nobody
 * asks that. They ask whether the gap is stable, which is a shape.
 */
export function SeasonLines({
  title,
  caption,
  seasons,
  series,
}: SeasonLinesProps) {
  const titleId = useId();
  const values = series
    .flatMap((entry) => entry.points)
    .filter((value): value is number => value !== null);
  if (values.length === 0 || seasons.length < 2) {
    return (
      <figure className="calibration-chart">
        <figcaption>{title}</figcaption>
        <p className="calibration-empty">Not measured yet.</p>
      </figure>
    );
  }

  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const plotWidth = LINE_WIDTH - LINE_PAD.left - LINE_PAD.right;
  const plotHeight = LINE_HEIGHT - LINE_PAD.top - LINE_PAD.bottom;
  const x = (index: number) =>
    LINE_PAD.left + (index / (seasons.length - 1)) * plotWidth;
  const y = (value: number) =>
    LINE_PAD.top + plotHeight - ((value - low) / span) * plotHeight;

  return (
    <figure className="calibration-chart">
      <figcaption id={titleId}>{title}</figcaption>
      <svg
        className="calibration-svg"
        viewBox={`0 0 ${LINE_WIDTH} ${LINE_HEIGHT}`}
        role="img"
        aria-labelledby={titleId}
      >
        {series.map((entry) => {
          const drawn = entry.points
            .map((value, index) =>
              value === null ? null : `${String(x(index))},${String(y(value))}`,
            )
            .filter((point): point is string => point !== null);
          const last = entry.points.reduce<number | null>(
            (found, value) => (value === null ? found : value),
            null,
          );
          return (
            <g key={entry.label}>
              <polyline
                className={
                  entry.mine
                    ? "calibration-line calibration-line-mine"
                    : "calibration-line"
                }
                points={drawn.join(" ")}
              />
              {last === null ? null : (
                <text
                  className="calibration-series-label"
                  x={LINE_PAD.left + plotWidth + 6}
                  y={y(last) + 4}
                >
                  {entry.label}
                </text>
              )}
            </g>
          );
        })}
        {seasons.map((season, index) => (
          <text
            key={season}
            className="calibration-axis"
            x={x(index)}
            y={LINE_HEIGHT - 8}
            textAnchor="middle"
          >
            {season}
          </text>
        ))}
        <text className="calibration-axis" x={4} y={LINE_PAD.top + 4}>
          {high.toFixed(2)}
        </text>
        <text
          className="calibration-axis"
          x={4}
          y={LINE_PAD.top + plotHeight + 4}
        >
          {low.toFixed(2)}
        </text>
      </svg>
      <p className="calibration-caption">{caption}</p>
    </figure>
  );
}
