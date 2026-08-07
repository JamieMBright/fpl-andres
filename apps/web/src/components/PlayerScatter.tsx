import {
  memo,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import { CeefaxShirt } from "./CeefaxShirt";
import { clubMarker } from "../kit/club-markers";
import { kitForShortName } from "../kit/team-kits";
import { defconThresholdFor, metric } from "../state/analysis-metrics";
import type { AnalysisPlayer } from "../state/analysis-pool";
import { BIN_RAMP, binOf, binsFor, frontier } from "../state/scatter-regions";
import {
  quadrantCaption,
  type PlottedPlayer,
  type Selection,
} from "../state/scatter-select";
import type { ScatterView } from "../state/scatter-view";

/**
 * The scatter, drawn by hand in SVG.
 *
 * No charting library. Two reasons, and the second is the one that decided it.
 * The bundle budget in `scripts/size-budget.mjs` caps a lazy chunk at 32 kB
 * gzipped and Recharts is roughly three times that on its own. And the marks
 * here carry two encodings at once -- a shape per position as well as a colour,
 * because DESIGN.md does not let colour be the only signal -- which is a fight
 * with a library's own renderer rather than a feature of it.
 *
 * Every point is one `<path>`. At the full pool that is around 500 nodes, which
 * is fewer than the pitch view already draws, and the render-cost test beside
 * this file keeps it that way.
 */

const WIDTH = 720;
const HEIGHT = 520;
const MARGIN = { top: 28, right: 22, bottom: 56, left: 68 };
const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom;

// Kept clear at the foot of the plot so the watermark never lands on a mark.
// Small: it costs a little vertical resolution and buys a legible mark on
// every screenshot, including the dense bottom-left of a price chart.
const WATERMARK_GUTTER = 26;

// A wide spread, because the point of the third encoding is to be seen. The
// largest disc is about fourteen times the area of the smallest.
// Big enough to hit with a mouse and to see against the grid; the old floor of
// 2.6 disappeared on a dense chart.
const MIN_RADIUS = 5;
const MAX_RADIUS = 18;
const TICKS = 5;

export interface PlayerScatterProps {
  selection: Selection;
  view: ScatterView;
  pinned: readonly number[];
  onTogglePin: (code: number) => void;
  /** Told what the overlays could or could not draw, so the page can say it. */
  onOverlays?: (notes: OverlayNotes) => void;
}

/** What the two optional overlays managed, in the words the page prints. */
export interface OverlayNotes {
  ring: string | null;
  frontier: string | null;
}

/**
 * Printed into the chart itself, bottom left.
 *
 * The export already carries it, but an export is not how a chart travels --
 * somebody screenshots the page. Bottom left is the corner a crop keeps,
 * because the eye and the mouse both start top left.
 */
const WATERMARK = "FPL ANDRES  \u00b7  @fpl_andres";

/** Muted enough to sit under five hundred marks without competing with them. */
const SHADE_GOOD = "#00e676";
const SHADE_BAD = "#ff5252";
// Two gradients overlay, so the corner alpha is roughly double the stop alpha.
// Green needs the larger share: at equal alpha it disappears into the surface
// while the red still reads, which had the good corner looking unshaded.
const SHADE_ALPHA_GOOD = 0.26;
const SHADE_ALPHA_BAD = 0.18;

const GOOD_END = { colour: SHADE_GOOD, alpha: SHADE_ALPHA_GOOD };
const BAD_END = { colour: SHADE_BAD, alpha: SHADE_ALPHA_BAD };

interface Scale {
  (value: number): number;
  domain: [number, number];
  ticks: number[];
}

function makeScale(
  values: number[],
  range: [number, number],
  log: boolean,
): Scale {
  let low = Math.min(...values);
  let high = Math.max(...values);
  if (!Number.isFinite(low) || !Number.isFinite(high)) {
    low = 0;
    high = 1;
  }
  if (low === high) {
    // A single distinct value would divide by zero. Give it room either side so
    // the point lands in the middle instead of on an edge.
    low -= 1;
    high += 1;
  }

  const transform = log ? Math.log10 : (value: number) => value;
  const lowT = transform(log ? Math.max(low, Number.MIN_VALUE) : low);
  const highT = transform(log ? Math.max(high, Number.MIN_VALUE) : high);

  const scale = ((value: number) => {
    const ratio = (transform(value) - lowT) / (highT - lowT);
    return range[0] + ratio * (range[1] - range[0]);
  }) as Scale;

  scale.domain = [low, high];
  scale.ticks = Array.from({ length: TICKS }, (_, index) => {
    const ratio = index / (TICKS - 1);
    return log
      ? 10 ** (lowT + ratio * (highT - lowT))
      : low + ratio * (high - low);
  });
  return scale;
}

/**
 * A mark per position: circle, square, diamond, triangle.
 *
 * The shape is what carries the position for anyone who cannot separate the
 * colours, which DESIGN.md requires and no test can check.
 */
function markPath(position: string, cx: number, cy: number, r: number): string {
  if (position === "DEF") {
    return `M${cx - r} ${cy - r}h${r * 2}v${r * 2}h${-r * 2}Z`;
  }
  if (position === "MID") {
    return `M${cx} ${cy - r}L${cx + r} ${cy}L${cx} ${cy + r}L${cx - r} ${cy}Z`;
  }
  if (position === "FWD") {
    return `M${cx} ${cy - r}L${cx + r} ${cy + r * 0.8}L${cx - r} ${cy + r * 0.8}Z`;
  }
  // GKP, and anything unexpected, stays a circle.
  return `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${r * 2} 0a${r} ${r} 0 1 0 ${-r * 2} 0Z`;
}

function tickLabel(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1000) return `${Math.round(value / 100) / 10}k`;
  if (magnitude >= 10) return String(Math.round(value));
  if (magnitude >= 1) return value.toFixed(1);
  return value.toFixed(2);
}

export const PlayerScatter = memo(function PlayerScatter({
  selection,
  view,
  pinned,
  onTogglePin,
  onOverlays,
}: PlayerScatterProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const gradientId = useId();
  const [hovered, setHovered] = useState<PlottedPlayer | null>(null);
  const {
    points,
    centres,
    fit,
    x: xMetric,
    y: yMetric,
    size: sizeMetric,
  } = selection;

  const xScale = useMemo(
    () =>
      makeScale(
        points.map((point) => point.x),
        view.invertX ? [PLOT_WIDTH, 0] : [0, PLOT_WIDTH],
        view.logX,
      ),
    [points, view.logX, view.invertX],
  );
  const yScale = useMemo(
    () =>
      makeScale(
        points.map((point) => point.y),
        view.invertY
          ? [0, PLOT_HEIGHT - WATERMARK_GUTTER]
          : [PLOT_HEIGHT - WATERMARK_GUTTER, 0],
        view.logY,
      ),
    [points, view.logY, view.invertY],
  );

  const sizeBounds = useMemo(() => {
    const sizes = points
      .map((point) => point.size)
      .filter((value): value is number => value !== null);
    return sizes.length === 0
      ? null
      : { low: Math.min(...sizes), high: Math.max(...sizes) };
  }, [points]);

  const radius = (value: number | null): number => {
    // No size metric, or nothing to separate: one readable disc for everyone.
    if (!sizeBounds || value === null || sizeBounds.high === sizeBounds.low) {
      return MIN_RADIUS * 1.6;
    }
    // Area, not radius, tracks the value: a disc twice the radius reads as four
    // times the quantity, which is not what the number said.
    const ratio = (value - sizeBounds.low) / (sizeBounds.high - sizeBounds.low);
    return Math.sqrt(
      MIN_RADIUS ** 2 + ratio * (MAX_RADIUS ** 2 - MIN_RADIUS ** 2),
    );
  };

  const pinnedSet = useMemo(() => new Set(pinned), [pinned]);

  // Equal-width bins across the observed range, so a step of colour means the
  // same amount everywhere along the ramp.
  const colourMetric = metric(view.colourMetric);
  const bins = useMemo(
    () =>
      view.colourBy === "metric" && colourMetric
        ? binsFor(
            points.map((point) => point.player),
            colourMetric,
            view.bins,
          )
        : [],
    [view.colourBy, view.bins, colourMetric, points],
  );

  const binMarker = (player: AnalysisPlayer) => {
    if (!colourMetric || bins.length === 0) return null;
    const index = binOf(player, colourMetric, bins);
    if (index === null) return null;
    return {
      fill: BIN_RAMP[index] ?? BIN_RAMP.at(-1) ?? "#888",
      stroke: "#111",
      dash: undefined as string | undefined,
    };
  };

  // Where the good players are, from each metric's own declared direction.
  // Two overlaid gradients rather than a shape: one along each axis, each
  // fading to nothing at that axis's reference line, so the good corner ends
  // up green, the bad corner red and the two mixed corners cancel to neutral.
  const shading = useMemo(() => {
    if (!view.sweetSpot) return null;
    const centreX = centres ? xScale(centres.x) : PLOT_WIDTH / 2;
    const centreY = centres ? yScale(centres.y) : PLOT_HEIGHT / 2;
    const goodRight =
      xScale(xMetric.higherIsBetter ? xScale.domain[1] : xScale.domain[0]) >
      centreX;
    const goodUp =
      yScale(yMetric.higherIsBetter ? yScale.domain[1] : yScale.domain[0]) <
      centreY;
    const clamp = (value: number, span: number) =>
      Math.min(0.98, Math.max(0.02, value / span));
    return {
      x: {
        stop: clamp(centreX, PLOT_WIDTH),
        from: goodRight ? BAD_END : GOOD_END,
        to: goodRight ? GOOD_END : BAD_END,
      },
      y: {
        stop: clamp(centreY, PLOT_HEIGHT),
        from: goodUp ? GOOD_END : BAD_END,
        to: goodUp ? BAD_END : GOOD_END,
      },
    };
  }, [view.sweetSpot, centres, xScale, yScale, xMetric, yMetric]);

  const edge = useMemo(
    () =>
      view.frontier
        ? frontier(
            points.map((point) => point.player),
            xMetric,
            yMetric,
          )
        : null,
    [points, xMetric, yMetric, view.frontier],
  );

  // The page prints whichever overlay could not be drawn and why. Reported
  // rather than returned, because the chart is the thing that knows.
  useEffect(() => {
    onOverlays?.({ ring: null, frontier: edge?.reason ?? null });
  }, [onOverlays, edge]);

  const pioneers = useMemo(
    () => new Set(edge?.drawn?.pioneers.map((entry) => entry.code) ?? []),
    [edge],
  );

  const handleEnter = useCallback((point: PlottedPlayer) => {
    setHovered(point);
  }, []);

  // Only when a single position is selected: DEF clear ten and everyone else
  // twelve, so a bar drawn across a mixed pool would be the wrong bar for half
  // the marks.
  const solePosition =
    view.positions.length === 1 ? (view.positions[0] ?? "") : "";
  const defconLine = defconThresholdFor(xMetric.id, solePosition);
  const defconLineY = defconThresholdFor(yMetric.id, solePosition);

  const summary =
    `Scatter of ${points.length} players. ` +
    `Horizontal axis ${xMetric.label}, vertical axis ${yMetric.label}. ` +
    (centres
      ? `Reference lines at the ${view.centreMode} of each.`
      : "No reference lines: nothing is plotted.");
  return (
    <div className="scatter-frame">
      <svg
        ref={svgRef}
        className="scatter-svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={summary}
        data-testid="player-scatter"
        onMouseLeave={() => setHovered(null)}
      >
        {shading ? (
          <defs>
            <linearGradient id={`${gradientId}-x`} x1="0" x2="1" y1="0" y2="0">
              <stop
                offset="0"
                stopColor={shading.x.from.colour}
                stopOpacity={shading.x.from.alpha}
              />
              <stop
                offset={shading.x.stop}
                stopColor={shading.x.from.colour}
                stopOpacity={0}
              />
              <stop
                offset={shading.x.stop}
                stopColor={shading.x.to.colour}
                stopOpacity={0}
              />
              <stop
                offset="1"
                stopColor={shading.x.to.colour}
                stopOpacity={shading.x.to.alpha}
              />
            </linearGradient>
            <linearGradient id={`${gradientId}-y`} x1="0" x2="0" y1="0" y2="1">
              <stop
                offset="0"
                stopColor={shading.y.from.colour}
                stopOpacity={shading.y.from.alpha}
              />
              <stop
                offset={shading.y.stop}
                stopColor={shading.y.from.colour}
                stopOpacity={0}
              />
              <stop
                offset={shading.y.stop}
                stopColor={shading.y.to.colour}
                stopOpacity={0}
              />
              <stop
                offset="1"
                stopColor={shading.y.to.colour}
                stopOpacity={shading.y.to.alpha}
              />
            </linearGradient>
          </defs>
        ) : null}
        <rect
          className="scatter-plot-bg"
          x={MARGIN.left}
          y={MARGIN.top}
          width={PLOT_WIDTH}
          height={PLOT_HEIGHT}
        />

        <g transform={`translate(${MARGIN.left} ${MARGIN.top})`}>
          {shading ? (
            <>
              <rect
                className="scatter-shade"
                x={0}
                y={0}
                width={PLOT_WIDTH}
                height={PLOT_HEIGHT}
                fill={`url(#${gradientId}-x)`}
              >
                <title>
                  Green is the good end of {xMetric.label.toLowerCase()} and of{" "}
                  {yMetric.label.toLowerCase()}, fading to nothing at the{" "}
                  {view.centreMode}. Both shades are on at once, so the corner
                  that is good on both reads greenest and the mixed corners
                  cancel out.
                </title>
              </rect>
              <rect
                className="scatter-shade"
                x={0}
                y={0}
                width={PLOT_WIDTH}
                height={PLOT_HEIGHT}
                fill={`url(#${gradientId}-y)`}
              />
            </>
          ) : null}

          {xScale.ticks.map((tick) => (
            <line
              key={`gx-${tick}`}
              className="scatter-grid"
              x1={xScale(tick)}
              y1={0}
              x2={xScale(tick)}
              y2={PLOT_HEIGHT}
            />
          ))}
          {yScale.ticks.map((tick) => (
            <line
              key={`gy-${tick}`}
              className="scatter-grid"
              x1={0}
              y1={yScale(tick)}
              x2={PLOT_WIDTH}
              y2={yScale(tick)}
            />
          ))}

          {centres ? (
            <>
              <line
                className="scatter-centre"
                x1={xScale(centres.x)}
                y1={0}
                x2={xScale(centres.x)}
                y2={PLOT_HEIGHT}
              />
              <line
                className="scatter-centre"
                x1={0}
                y1={yScale(centres.y)}
                x2={PLOT_WIDTH}
                y2={yScale(centres.y)}
              />
            </>
          ) : null}

          {/* The bar a DefCon axis actually has to clear, when one position is
              selected and so there is a single threshold to draw. */}
          {defconLine !== null ? (
            <line
              className="scatter-threshold"
              x1={xScale(defconLine)}
              y1={0}
              x2={xScale(defconLine)}
              y2={PLOT_HEIGHT}
            />
          ) : null}
          {defconLineY !== null ? (
            <line
              className="scatter-threshold"
              x1={0}
              y1={yScale(defconLineY)}
              x2={PLOT_WIDTH}
              y2={yScale(defconLineY)}
            />
          ) : null}

          {fit ? (
            <line
              className="scatter-trend"
              x1={xScale(xScale.domain[0])}
              y1={yScale(fit.slope * xScale.domain[0] + fit.intercept)}
              x2={xScale(xScale.domain[1])}
              y2={yScale(fit.slope * xScale.domain[1] + fit.intercept)}
            />
          ) : null}

          {edge?.drawn ? (
            <polyline
              className="scatter-frontier"
              points={edge.drawn.curve
                .map(
                  (point) =>
                    `${String(xScale(point.x))},${String(yScale(point.y))}`,
                )
                .join(" ")}
            >
              <title>
                {edge.drawn.sigma} standard deviations above the average{" "}
                {yMetric.label.toLowerCase()} of the players around the same{" "}
                {xMetric.label.toLowerCase()}, measured in{" "}
                {edge.drawn.bins.length} slices of the x-axis.{" "}
                {edge.drawn.pioneers.length === 0
                  ? "Nobody clears it."
                  : `${String(edge.drawn.pioneers.length)} players clear it.`}
              </title>
            </polyline>
          ) : null}

          <g className="scatter-marks">
            {points.map((point) => {
              const isPinned = pinnedSet.has(point.player.code);
              // Colouring by club or by a binned statistic overrides the
              // position palette. The shape still carries the position, so
              // nothing is lost by it.
              const mark =
                view.colourBy === "club"
                  ? clubMarker(point.player.club)
                  : view.colourBy === "metric"
                    ? binMarker(point.player)
                    : null;
              const classes = [
                "scatter-mark",
                `scatter-mark-${point.player.position.toLowerCase()}`,
                mark ? "scatter-mark-club" : "",
                point.matched ? "" : "scatter-mark-dimmed",
                point.overlooked ? "scatter-mark-overlooked" : "",
                pioneers.has(point.player.code) ? "scatter-mark-pioneer" : "",
                isPinned ? "scatter-mark-pinned" : "",
              ]
                .filter(Boolean)
                .join(" ");
              return (
                <path
                  key={point.player.code}
                  className={classes}
                  d={markPath(
                    point.player.position,
                    xScale(point.x),
                    yScale(point.y),
                    radius(point.size),
                  )}
                  {...(mark
                    ? {
                        // Inline style, not a presentation attribute: the
                        // position palette is a stylesheet rule and would win.
                        style: {
                          fill: mark.fill,
                          stroke: mark.stroke,
                          ...(mark.dash ? { strokeDasharray: mark.dash } : {}),
                        },
                      }
                    : {})}
                  onMouseEnter={() => handleEnter(point)}
                  onClick={() => onTogglePin(point.player.code)}
                />
              );
            })}
          </g>

          {view.labels ? (
            <g className="scatter-labels" aria-hidden="true">
              {points.map((point) => {
                const px = xScale(point.x);
                const py = yScale(point.y);
                const r = radius(point.size);
                // Leader goes up-left near the right edge and down near the
                // top, so a name never runs outside the plotting area.
                const flip = px > PLOT_WIDTH * 0.78;
                const below = py < 14;
                const tipX = px + (flip ? -(r + 6) : r + 6);
                const tipY = py + (below ? r + 6 : -(r + 6));
                return (
                  <g key={point.player.code}>
                    <line
                      className="scatter-label-whisker"
                      x1={px + (flip ? -r : r) * 0.7}
                      x2={tipX}
                      y1={py + (below ? r : -r) * 0.7}
                      y2={tipY}
                    />
                    <text
                      className="scatter-label"
                      textAnchor={flip ? "end" : "start"}
                      x={tipX + (flip ? -1 : 1)}
                      y={tipY + (below ? 6 : -1)}
                    >
                      {point.player.name}
                    </text>
                  </g>
                );
              })}
            </g>
          ) : null}

          {/* Said on the axes, because a reader who has just moved a slider is
              looking at the chart and not at a table underneath it. */}
          {points.length === 0 ? (
            <>
              <text
                className="scatter-empty-title"
                x={PLOT_WIDTH / 2}
                y={PLOT_HEIGHT / 2 - 8}
                textAnchor="middle"
              >
                Nothing survives these filters
              </text>
              <text
                className="scatter-empty-hint"
                x={PLOT_WIDTH / 2}
                y={PLOT_HEIGHT / 2 + 18}
                textAnchor="middle"
              >
                Drop the minutes threshold, widen the ownership band, or put a
                position back.
              </text>
            </>
          ) : null}
        </g>

        <g className="scatter-axis">
          {xScale.ticks.map((tick) => (
            <text
              key={`tx-${tick}`}
              x={MARGIN.left + xScale(tick)}
              y={HEIGHT - MARGIN.bottom + 20}
              textAnchor="middle"
            >
              {tickLabel(tick)}
            </text>
          ))}
          {yScale.ticks.map((tick) => (
            <text
              key={`ty-${tick}`}
              x={MARGIN.left - 10}
              y={MARGIN.top + yScale(tick) + 4}
              textAnchor="end"
            >
              {tickLabel(tick)}
            </text>
          ))}
        </g>

        <text
          className="scatter-axis-title"
          x={MARGIN.left + PLOT_WIDTH / 2}
          y={HEIGHT - 8}
          textAnchor="middle"
        >
          {xMetric.label}
        </text>
        <text
          className="scatter-axis-title"
          transform={`translate(16 ${MARGIN.top + PLOT_HEIGHT / 2}) rotate(-90)`}
          textAnchor="middle"
        >
          {yMetric.label}
        </text>
        {/* Inside the plot, not under it. A screenshot is how a chart
            actually travels, and the crop that keeps the data keeps this. */}
        <text
          className="scatter-watermark"
          x={MARGIN.left + 10}
          y={MARGIN.top + PLOT_HEIGHT - 10}
        >
          {WATERMARK}
        </text>
      </svg>

      {hovered ? (
        <ScatterTooltip
          point={hovered}
          xLabel={xMetric.label}
          yLabel={yMetric.label}
          xText={xMetric.format(hovered.x)}
          yText={yMetric.format(hovered.y)}
          sizeLabel={sizeMetric?.label ?? null}
          sizeText={
            sizeMetric && hovered.size !== null
              ? sizeMetric.format(hovered.size)
              : null
          }
          left={MARGIN.left + xScale(hovered.x)}
          top={MARGIN.top + yScale(hovered.y)}
        />
      ) : null}

      {centres ? (
        <p className="scatter-quadrant-note">
          Top right: {quadrantCaption("high-high", xMetric, yMetric)}. Bottom
          left: {quadrantCaption("low-low", xMetric, yMetric)}.
        </p>
      ) : null}
    </div>
  );
});

interface TooltipProps {
  point: PlottedPlayer;
  xLabel: string;
  yLabel: string;
  xText: string;
  yText: string;
  sizeLabel: string | null;
  sizeText: string | null;
  left: number;
  top: number;
}

function ScatterTooltip({
  point,
  xLabel,
  yLabel,
  xText,
  yText,
  sizeLabel,
  sizeText,
  left,
  top,
}: TooltipProps) {
  const { player } = point;
  const kit = kitForShortName(player.club);
  // Open toward whichever side has room. Fixed to the right, a point in the
  // last third of the chart pushed the box off the edge of the frame.
  const across =
    left > WIDTH * 0.62 ? "translateX(calc(-100% - 12px))" : "translateX(12px)";
  const down =
    top < HEIGHT * 0.22
      ? "translateY(0)"
      : top > HEIGHT * 0.78
        ? "translateY(-100%)"
        : "translateY(-50%)";
  return (
    <div
      className="scatter-tooltip"
      style={{
        left: `${(left / WIDTH) * 100}%`,
        top: `${(top / HEIGHT) * 100}%`,
        transform: `${across} ${down}`,
      }}
      aria-hidden="true"
    >
      <span className="scatter-tooltip-head">
        {kit ? (
          <CeefaxShirt
            className="scatter-tooltip-shirt"
            kit={kit}
            label={null}
          />
        ) : null}
        <span>
          <strong translate="no">{player.name}</strong>
          <span className="scatter-tooltip-club" translate="no">
            {player.position} · {player.club} · &pound;
            {(player.priceTenths / 10).toFixed(1)}m
          </span>
        </span>
      </span>

      <dl className="scatter-tooltip-stats">
        <div>
          <dt>{xLabel}</dt>
          <dd>{xText}</dd>
        </div>
        <div>
          <dt>{yLabel}</dt>
          <dd>{yText}</dd>
        </div>
        {sizeLabel && sizeText ? (
          <div>
            <dt>{sizeLabel}</dt>
            <dd>{sizeText}</dd>
          </div>
        ) : null}
        <div>
          <dt>Minutes</dt>
          <dd>{player.minutes.toLocaleString("en-GB")}</dd>
        </div>
        {sizeLabel === "Ownership" || player.ownership === null ? null : (
          <div>
            <dt>Owned</dt>
            <dd>{player.ownership.toFixed(1)}%</dd>
          </div>
        )}
      </dl>

      <span className="scatter-tooltip-hint">Click to pin for comparison</span>
    </div>
  );
}
