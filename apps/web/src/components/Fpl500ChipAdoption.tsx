import { CHIP_NAMES } from "../state/declared-chips";
import {
  chipAdoption,
  SECOND_HALF_START,
  type ChipAdoptionSeries,
  type PortfolioSeriesLike,
} from "../state/fpl500-chip-adoption";

/**
 * Cumulative chip adoption, one line per chip, gameweek by gameweek.
 *
 * A per-gameweek bar answers "who is spending it this week"; it cannot answer
 * "how much of this half is already gone". Turning the same counts into a
 * running total does: a healthy chip climbs toward 100% across a half, and a
 * line that stalls says a chip is being held rather than never owned. The
 * counter restarts at the second half's opening gameweek because that is the
 * same restart FPL gives the chip itself.
 */

const WIDTH = 560;
const HEIGHT = 220;
const PAD_LEFT = 40;
const PAD_RIGHT = 12;
const PAD_TOP = 10;
const PAD_BOTTOM = 26;

const CHIP_COLOR: Record<string, string> = {
  wildcard: "var(--field-green)",
  freehit: "var(--signal-blue)",
  bboost: "var(--amber)",
  "3xc": "var(--danger)",
};

function pathFor(
  series: ChipAdoptionSeries,
  eventToX: (event: number) => number,
  plotHeight: number,
): string {
  return series.points
    .map((point, index) => {
      const x = eventToX(point.event);
      const y = PAD_TOP + plotHeight * (1 - point.share);
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}

export function Fpl500ChipAdoption({
  series,
}: {
  series: PortfolioSeriesLike;
}) {
  const adoption = chipAdoption(series);
  const events = [...series.events].sort((left, right) => left - right);
  if (events.length < 2) return null;

  const firstEvent = events[0] ?? 1;
  const lastEvent = events[events.length - 1] ?? firstEvent;
  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const span = Math.max(1, lastEvent - firstEvent);
  const eventToX = (event: number) =>
    PAD_LEFT + ((event - firstEvent) / span) * plotWidth;
  const resetX =
    firstEvent < SECOND_HALF_START && lastEvent >= SECOND_HALF_START
      ? eventToX(SECOND_HALF_START)
      : null;

  return (
    <figure className="chip-adoption-chart">
      <figcaption>
        Cumulative chip adoption across the sampled cohort
      </figcaption>
      <svg
        aria-hidden="true"
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <line
            className="chip-adoption-grid"
            key={fraction}
            x1={PAD_LEFT}
            x2={WIDTH - PAD_RIGHT}
            y1={PAD_TOP + plotHeight * (1 - fraction)}
            y2={PAD_TOP + plotHeight * (1 - fraction)}
          />
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <text
            className="chip-adoption-axis"
            key={fraction}
            textAnchor="end"
            x={PAD_LEFT - 6}
            y={PAD_TOP + plotHeight * (1 - fraction) + 3}
          >
            {Math.round(fraction * 100)}%
          </text>
        ))}
        {resetX === null ? null : (
          <line
            className="chip-adoption-reset"
            x1={resetX}
            x2={resetX}
            y1={PAD_TOP}
            y2={PAD_TOP + plotHeight}
          />
        )}
        {adoption.map((series) => (
          <path
            className="chip-adoption-line"
            d={pathFor(series, eventToX, plotHeight)}
            fill="none"
            key={series.chip}
            stroke={CHIP_COLOR[series.chip]}
          />
        ))}
        <text className="chip-adoption-axis" x={PAD_LEFT} y={HEIGHT - 6}>
          GW{firstEvent}
        </text>
        <text
          className="chip-adoption-axis"
          textAnchor="end"
          x={WIDTH - PAD_RIGHT}
          y={HEIGHT - 6}
        >
          GW{lastEvent}
        </text>
      </svg>
      <ul className="chip-adoption-legend">
        {adoption.map((series) => (
          <li key={series.chip}>
            <span
              className="chip-adoption-swatch"
              style={{ background: CHIP_COLOR[series.chip] }}
            />
            {CHIP_NAMES[series.chip]}
          </li>
        ))}
      </ul>
    </figure>
  );
}
