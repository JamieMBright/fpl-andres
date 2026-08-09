import { memo, useMemo } from "react";

import { clubMarkers } from "../kit/club-markers";
import type { Metric } from "../state/analysis-metrics";
import type { Bin } from "../state/scatter-regions";
import { BIN_RAMP } from "../state/scatter-regions";
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

/**
 * One key, and the control that isolates it.
 *
 * Isolating dims the rest rather than dropping them: the reader asked which of
 * these is which, and an answer that deletes the comparison is not an answer.
 */
function Swatch({
  children,
  isolated,
  label,
  onToggle,
}: {
  readonly children: React.ReactNode;
  readonly isolated: boolean;
  readonly label: string;
  readonly onToggle: () => void;
}) {
  return (
    <button
      aria-pressed={isolated}
      className="scatter-legend-key"
      onClick={onToggle}
      type="button"
    >
      <svg
        aria-hidden="true"
        height={SWATCH}
        viewBox={`0 0 ${SWATCH} ${SWATCH}`}
        width={SWATCH}
      >
        {children}
      </svg>
      <span translate="no">{label}</span>
    </button>
  );
}

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
  colourMetric,
  bins,
  onToggle,
}: {
  sizeMetric: Metric | null;
  /** Smallest and largest plotted value, so the swatches quote real numbers. */
  sizeRange: { low: number; high: number } | null;
  view: ScatterView;
  clubsInPlay: readonly string[];
  /** The statistic the colour bins, when colouring by one. */
  colourMetric: Metric | null;
  bins: readonly Bin[];
  /** Adds or removes one highlight key. The legend is the control. */
  onToggle: (key: string) => void;
}) {
  const byClub = view.colourBy === "club";
  const held = useMemo(() => new Set(view.highlights), [view.highlights]);
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
              <Swatch
                isolated={held.has(`@${code}`)}
                label={label}
                onToggle={() => {
                  onToggle(`@${code}`);
                }}
              >
                {/* Grey, like the size key: this row is about shape, and
                    colouring it would claim a second encoding it does not
                    carry. */}
                <path className="scatter-legend-shape" d={markPath(code, 7)} />
              </Swatch>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>
          {byClub
            ? "Colour is the club kit"
            : view.colourBy === "metric" && colourMetric
              ? `Colour is ${colourMetric.label.toLowerCase()}`
              : "Colour is the position"}
        </h3>
        {byClub ? (
          <ul className="scatter-legend-clubs">
            {shown.map((mark) => (
              <li key={mark.shortName}>
                <Swatch
                  isolated={held.has(mark.shortName)}
                  label={mark.shortName}
                  onToggle={() => {
                    onToggle(mark.shortName);
                  }}
                >
                  <path
                    d={markPath("GKP", 7)}
                    fill={mark.fill}
                    stroke={mark.stroke}
                    strokeWidth={2.5}
                    {...(mark.dash ? { strokeDasharray: mark.dash } : {})}
                  />
                </Swatch>
              </li>
            ))}
          </ul>
        ) : view.colourBy === "metric" && colourMetric ? (
          <ul className="scatter-legend-bins">
            {bins.map((bin, index) => (
              <li key={bin.label}>
                <span
                  aria-hidden="true"
                  className="scatter-legend-swatch"
                  style={{ background: BIN_RAMP[index] ?? "#888" }}
                />
                {bin.label}
              </li>
            ))}
          </ul>
        ) : (
          <ul className="scatter-legend-clubs">
            {POSITIONS.map(({ code, label }) => (
              <li key={code}>
                <Swatch
                  isolated={held.has(`@${code}`)}
                  label={label}
                  onToggle={() => {
                    onToggle(`@${code}`);
                  }}
                >
                  <path
                    className={`scatter-mark scatter-mark-${code.toLowerCase()}`}
                    d={markPath(code, 7)}
                  />
                </Swatch>
              </li>
            ))}
          </ul>
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
