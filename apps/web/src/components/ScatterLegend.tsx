import { memo, useMemo } from "react";

import { clubMarkers } from "../kit/club-markers";
import type { Metric } from "../state/analysis-metrics";
import type { ScatterView } from "../state/scatter-view";

/**
 * What the marks mean.
 *
 * The chart carries three encodings at once and none of them is guessable. A
 * chart you have to be told how to read, without being told, is decoration.
 */

const POSITIONS = [
  { code: "GKP", label: "Goalkeeper" },
  { code: "DEF", label: "Defender" },
  { code: "MID", label: "Midfielder" },
  { code: "FWD", label: "Forward" },
];

const SWATCH = 22;

/** The same geometry the scatter draws, at legend size. */
function markPath(position: string, r: number): string {
  const c = SWATCH / 2;
  if (position === "DEF")
    return `M${c - r} ${c - r}h${r * 2}v${r * 2}h${-r * 2}Z`;
  if (position === "MID")
    return `M${c} ${c - r}L${c + r} ${c}L${c} ${c + r}L${c - r} ${c}Z`;
  if (position === "FWD")
    return `M${c} ${c - r}L${c + r} ${c + r * 0.8}L${c - r} ${c + r * 0.8}Z`;
  return `M${c - r} ${c}a${r} ${r} 0 1 0 ${r * 2} 0a${r} ${r} 0 1 0 ${-r * 2} 0Z`;
}

export function ScatterLegend({
  sizeMetric,
  sizeRange,
  view,
  clubsInPlay,
}: {
  sizeMetric: Metric | null;
  /** Smallest and largest plotted value, so the swatches quote real numbers. */
  sizeRange: { low: number; high: number } | null;
  view: ScatterView;
  clubsInPlay: readonly string[];
}) {
  const byClub = view.colourBy === "club";
  const shown = useMemo(() => {
    if (!byClub) return [];
    const wanted = new Set(clubsInPlay);
    return clubMarkers().filter((mark) => wanted.has(mark.shortName));
  }, [byClub, clubsInPlay]);

  return (
    <div className="scatter-legend">
      <section>
        <h3>Shape is the position</h3>
        <ul>
          {POSITIONS.map(({ code, label }) => (
            <li key={code}>
              <svg
                aria-hidden="true"
                height={SWATCH}
                viewBox={`0 0 ${SWATCH} ${SWATCH}`}
                width={SWATCH}
              >
                <path
                  className={`scatter-mark scatter-mark-${code.toLowerCase()}`}
                  d={markPath(code, 7)}
                />
              </svg>
              {label}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>{byClub ? "Colour is the club kit" : "Colour is the position"}</h3>
        {byClub ? (
          <>
            <ul className="scatter-legend-clubs">
              {shown.map((mark) => (
                <li key={mark.shortName}>
                  <svg
                    aria-hidden="true"
                    height={SWATCH}
                    viewBox={`0 0 ${SWATCH} ${SWATCH}`}
                    width={SWATCH}
                  >
                    <path
                      d={markPath("GKP", 7)}
                      fill={mark.fill}
                      stroke={mark.stroke}
                      strokeWidth={2.5}
                      {...(mark.dash ? { strokeDasharray: mark.dash } : {})}
                    />
                  </svg>
                  <span translate="no">{mark.shortName}</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p>
            One colour per position, matched to the shape beside it, so neither
            is doing the work alone.
          </p>
        )}
      </section>

      {sizeMetric && sizeRange ? (
        <section>
          <h3>Size is {sizeMetric.label.toLowerCase()}</h3>
          <ul className="scatter-legend-size">
            {[0, 0.5, 1].map((ratio) => {
              const value =
                sizeRange.low + ratio * (sizeRange.high - sizeRange.low);
              // Area tracks the value, so the radius is its square root.
              const r = Math.sqrt(5 ** 2 + ratio * (18 ** 2 - 5 ** 2));
              return (
                <li key={ratio}>
                  <svg
                    aria-hidden="true"
                    height={38}
                    viewBox="0 0 38 38"
                    width={38}
                  >
                    <circle
                      className="scatter-legend-disc"
                      cx={19}
                      cy={19}
                      r={r}
                    />
                  </svg>
                  {sizeMetric.format(value)}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export default memo(ScatterLegend);
