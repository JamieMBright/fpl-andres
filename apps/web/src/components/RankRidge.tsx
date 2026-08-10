/**
 * Where the cohort finishes, season by season, on one shared axis.
 *
 * A table of counts per bin is unreadable and a stacked bar hides the shape.
 * What the eye wants from five seasons of the same distribution is five lines
 * it can lay over each other, so this draws them as a ridge: one smoothed area
 * per season, same x, same y, stacked with a shallow offset.
 *
 * The x axis is log-spaced because that is where the structure is. The gap
 * between a thousandth and ten thousandth is the whole subject; the gap
 * between a million and two is noise. A tick sits on the boundary between two
 * bins rather than on a bin, because that is what the number names.
 */

export interface Ridge {
  label: string;
  /** Counts per bin, one longer than the edges: the last is everything above. */
  counts: readonly number[];
  /** Drawn apart from the shared axis, for a season still being played. */
  separate?: boolean;
}

const WIDTH = 560;
const ROW = 46;
const PAD_LEFT = 62;
const PAD_RIGHT = 12;
const PAD_TOP = 8;
const AXIS = 26;

function short(edge: number): string {
  if (edge >= 1_000_000) return `${edge / 1_000_000}m`;
  if (edge >= 1_000) return `${edge / 1_000}k`;
  return String(edge);
}

/** A Catmull-Rom pass, so the ridge reads as a distribution not a histogram. */
function smooth(points: readonly [number, number][]): string {
  if (points.length < 2) return "";
  const [first, ...rest] = points;
  let path = `M ${first![0]} ${first![1]}`;
  for (let i = 0; i < rest.length; i += 1) {
    const previous = points[i]!;
    const current = rest[i]!;
    const midX = (previous[0] + current[0]) / 2;
    path += ` C ${midX} ${previous[1]}, ${midX} ${current[1]}, ${current[0]} ${current[1]}`;
  }
  return path;
}

export function RankRidge({
  edges,
  ridges,
  caption,
}: {
  edges: readonly number[];
  ridges: readonly Ridge[];
  caption: string;
}) {
  const bins = edges.length + 1;
  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const step = plotWidth / (bins - 1);
  const height = PAD_TOP + ridges.length * ROW + AXIS;
  const peak = Math.max(
    ...ridges.flatMap((ridge) => ridge.counts.map((count) => count)),
    1,
  );

  return (
    <figure className="ridge-chart">
      <figcaption>{caption}</figcaption>
      <svg
        aria-hidden="true"
        role="img"
        viewBox={`0 0 ${WIDTH} ${height}`}
        width="100%"
      >
        {edges.map((edge, index) => (
          <line
            className="ridge-grid"
            key={edge}
            x1={PAD_LEFT + (index + 0.5) * step}
            x2={PAD_LEFT + (index + 0.5) * step}
            y1={PAD_TOP}
            y2={PAD_TOP + ridges.length * ROW}
          />
        ))}
        {ridges.map((ridge, row) => {
          const base = PAD_TOP + (row + 1) * ROW;
          const points = ridge.counts.map(
            (count, index) =>
              [PAD_LEFT + index * step, base - (count / peak) * (ROW - 8)] as [
                number,
                number,
              ],
          );
          const line = smooth(points);
          return (
            <g
              className={ridge.separate ? "ridge-row separate" : "ridge-row"}
              key={ridge.label}
            >
              <path
                className="ridge-area"
                d={`${line} L ${PAD_LEFT + plotWidth} ${base} L ${PAD_LEFT} ${base} Z`}
              />
              <path className="ridge-line" d={line} />
              <text className="ridge-label" x={PAD_LEFT - 8} y={base - 2}>
                {ridge.label}
              </text>
            </g>
          );
        })}
        <line
          className="ridge-axis"
          x1={PAD_LEFT}
          x2={PAD_LEFT + plotWidth}
          y1={PAD_TOP + ridges.length * ROW}
          y2={PAD_TOP + ridges.length * ROW}
        />
        {edges.map((edge, index) => (
          <text
            className="ridge-tick"
            key={edge}
            x={PAD_LEFT + (index + 0.5) * step}
            y={PAD_TOP + ridges.length * ROW + 16}
          >
            {short(edge)}
          </text>
        ))}
      </svg>
    </figure>
  );
}
