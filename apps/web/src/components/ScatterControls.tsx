import { useId, useState } from "react";

import { METRICS, type MetricGroup } from "../state/analysis-metrics";
import { HighlightPicker } from "./HighlightPicker";
import { RangeSlider } from "./RangeSlider";
import type { AnalysisPool } from "../state/analysis-pool";
import type { ColourBy, ScatterView } from "../state/scatter-view";
import {
  ARCHIVED_SEASONS,
  FIRST_EVENT,
  LAST_EVENT,
  LIVE_SEASON,
  MAX_BINS,
  MIN_BINS,
  NO_SIZE,
  OWNERSHIP_CAP,
  PRICE_CAP_TENTHS,
} from "../state/scatter-view";

/**
 * Everything that changes what the chart shows, in one panel.
 *
 * The axis pickers are grouped by what the number describes rather than listed
 * alphabetically, because the useful pairings are nearly always across groups:
 * something he did against what he costs, or attack against defence.
 */

const GROUP_ORDER: MetricGroup[] = [
  "Points",
  "Attack",
  "Shot quality",
  "Defence",
  "Market",
];

/**
 * What the live option is actually showing.
 *
 * Between seasons FPL keeps last season's totals under the same column names,
 * so "this season, as it stands" was a label for 2025/26 numbers. The option
 * names the vintage instead, and flips on its own when a gameweek is scored.
 */
function liveSeasonLabel(pool: AnalysisPool): string {
  const { vintage } = pool;
  if (vintage.state === "previous_season") {
    return `${vintage.season ?? "Last season"} record, prices as they are today`;
  }
  if (vintage.state === "live_season") {
    return `${vintage.season ?? "This season"}, ${String(vintage.completedGameweeks)} gameweeks in`;
  }
  return "Nothing measured yet";
}

export interface ScatterControlsProps {
  pool: AnalysisPool;
  view: ScatterView;
  onChange: (next: Partial<ScatterView>) => void;
  onReset: () => void;
  plotted: number;
}

export function ScatterControls({
  pool,
  view,
  onChange,
  onReset,
  plotted,
}: ScatterControlsProps) {
  const ids = useId();
  // A `details` rather than state: the platform gives the disclosure, the
  // keyboard behaviour and the closed-by-default in one attribute.
  //
  // Open where it is a sidebar, closed where it is a block sitting on top of
  // the chart. Read once at mount rather than watched: this decides an initial
  // state, and reopening a panel somebody has just closed because they turned
  // their phone is worse than being a breakpoint behind.
  const [asSidebar] = useState(
    () => window.matchMedia?.("(min-width: 1101px)").matches ?? false,
  );
  return (
    <details className="scatter-controls analysis-controls" open={asSidebar}>
      <summary className="scatter-controls-summary">
        <span>Plot configuration</span>
        <span className="scatter-controls-count mono">{plotted} plotted</span>
      </summary>
      <div className="scatter-controls-body">
        <fieldset className="scatter-fieldset">
          <legend>Season</legend>
          <div className="scatter-control-row">
            <label htmlFor={`${ids}-season`}>Which season</label>
            <select
              id={`${ids}-season`}
              value={view.season}
              onChange={(event) => onChange({ season: event.target.value })}
            >
              <option value={LIVE_SEASON}>{liveSeasonLabel(pool)}</option>
              {[...ARCHIVED_SEASONS].reverse().map((season) => (
                <option key={season} value={season}>
                  {season}
                </option>
              ))}
            </select>
          </div>
          {view.season === LIVE_SEASON ? (
            <p className="scatter-hint">
              {pool.vintage.state === "previous_season"
                ? `2026/27 has not kicked off, so FPL's season totals are still ${pool.vintage.season ?? "last season"}'s. That is what is plotted. Ownership and price are today's.`
                : "Live figures from FPL, including ownership and shot quality. A past season is downloaded on request and carries neither."}
            </p>
          ) : (
            <>
              <RangeSlider
                format={(value) => `GW${value.toFixed(0)}`}
                from={view.fromEvent}
                label="Gameweek window"
                max={LAST_EVENT}
                min={FIRST_EVENT}
                onChange={({ from, to }) =>
                  onChange({ fromEvent: from, toEvent: to })
                }
                step={1}
                to={view.toEvent}
              />
              <p className="scatter-hint">
                Points, minutes and price are re-totalled over the window, and
                the price is what he closed it at. Expected goals and defensive
                contributions are published as season totals, so those stay
                whole however narrow the window is.
              </p>
            </>
          )}
        </fieldset>

        <div className="scatter-control-row">
          <AxisPicker
            id={`${ids}-x`}
            label="x-axis (along the bottom)"
            value={view.x}
            onChange={(x) => onChange({ x })}
          />
          <LogToggle
            id={`${ids}-logx`}
            metricId={view.x}
            checked={view.logX}
            onChange={(logX) => onChange({ logX })}
          />
          <label className="scatter-check">
            <input
              checked={view.invertX}
              onChange={() => onChange({ invertX: !view.invertX })}
              type="checkbox"
            />
            Invert
          </label>
        </div>

        <div className="scatter-control-row">
          <AxisPicker
            id={`${ids}-y`}
            label="y-axis (up the side)"
            value={view.y}
            onChange={(y) => onChange({ y })}
          />
          <LogToggle
            id={`${ids}-logy`}
            metricId={view.y}
            checked={view.logY}
            onChange={(logY) => onChange({ logY })}
          />
          <label className="scatter-check">
            <input
              checked={view.invertY}
              onChange={() => onChange({ invertY: !view.invertY })}
              type="checkbox"
            />
            Invert
          </label>
        </div>

        <div className="scatter-control-row">
          <AxisPicker
            allowNone
            id={`${ids}-size`}
            label="Bubble size"
            value={view.size}
            onChange={(size) => onChange({ size })}
          />
        </div>

        <fieldset className="scatter-fieldset">
          <legend>Colour by</legend>
          {(["club", "position", "metric"] as ColourBy[]).map((mode) => (
            <label key={mode} className="scatter-radio">
              <input
                type="radio"
                name={`${ids}-colour`}
                checked={view.colourBy === mode}
                onChange={() => onChange({ colourBy: mode })}
              />
              {mode === "position"
                ? "Position"
                : mode === "club"
                  ? "Club"
                  : "A statistic"}
            </label>
          ))}
        </fieldset>

        {view.colourBy === "metric" ? (
          <div className="scatter-control-row">
            <AxisPicker
              id={`${ids}-cmetric`}
              label="Colour statistic"
              value={view.colourMetric}
              onChange={(colourMetric) => onChange({ colourMetric })}
            />
            <label className="scatter-number" htmlFor={`${ids}-bins`}>
              Bins
              <input
                id={`${ids}-bins`}
                max={MAX_BINS}
                min={MIN_BINS}
                onChange={(event) =>
                  onChange({ bins: Number(event.target.value) })
                }
                type="number"
                value={view.bins}
              />
            </label>
          </div>
        ) : null}

        <fieldset className="scatter-fieldset">
          <legend>Positions</legend>
          {pool.positions.map((code) => (
            <label key={code} className="scatter-check">
              <input
                type="checkbox"
                checked={
                  view.positions.length === 0 || view.positions.includes(code)
                }
                onChange={() =>
                  onChange({
                    positions: togglePosition(
                      view.positions,
                      code,
                      pool.positions,
                    ),
                  })
                }
              />
              {code}
            </label>
          ))}
          <p className="scatter-hint">
            {view.positions.length === 0 ? "All positions" : null}
          </p>
        </fieldset>

        <div className="scatter-control-row">
          <label htmlFor={`${ids}-club`}>Club</label>
          <select
            id={`${ids}-club`}
            multiple
            size={5}
            value={view.clubs}
            onChange={(event) =>
              onChange({
                clubs: [...event.target.selectedOptions].map(
                  (option) => option.value,
                ),
              })
            }
          >
            {pool.clubs.map((club) => (
              <option key={club} value={club}>
                {club}
              </option>
            ))}
          </select>
        </div>

        <div className="scatter-control-row">
          <label htmlFor={`${ids}-mins`}>
            Minimum minutes
            <span className="scatter-value">{view.minMinutes}</span>
          </label>
          <input
            id={`${ids}-mins`}
            type="range"
            min={0}
            max={3000}
            step={90}
            value={view.minMinutes}
            onChange={(event) =>
              onChange({ minMinutes: Number(event.target.value) })
            }
          />
          <p className="scatter-hint">
            Below this a per-90 rate is a rumour. Five matches is the default.
          </p>
        </div>

        <div className="scatter-control-row">
          <HighlightPicker
            highlights={view.highlights}
            onChange={(highlights) => onChange({ highlights })}
            players={pool.players}
          />
        </div>

        <fieldset className="scatter-fieldset">
          <legend>Reference lines</legend>
          {(["median", "mean"] as const).map((mode) => (
            <label key={mode} className="scatter-radio">
              <input
                type="radio"
                name={`${ids}-centre`}
                checked={view.centreMode === mode}
                onChange={() => onChange({ centreMode: mode })}
              />
              {mode === "median" ? "Median" : "Mean"}
            </label>
          ))}
          <label className="scatter-check">
            <input
              type="checkbox"
              checked={view.trend}
              onChange={() => onChange({ trend: !view.trend })}
            />
            Trend line
          </label>
          <label className="scatter-check">
            <input
              type="checkbox"
              checked={view.sweetSpot}
              onChange={() => onChange({ sweetSpot: !view.sweetSpot })}
            />
            Shade the good corner
          </label>
          <label className="scatter-check">
            <input
              type="checkbox"
              checked={view.frontier}
              onChange={() => onChange({ frontier: !view.frontier })}
            />
            Two-sigma curve
          </label>
          <label className="scatter-check">
            <input
              type="checkbox"
              checked={view.labels}
              onChange={() => onChange({ labels: !view.labels })}
            />
            Name every point
          </label>
        </fieldset>

        <fieldset className="scatter-fieldset">
          <legend>Ownership band</legend>
          <p className="scatter-hint">
            Only players owned inside this range are drawn. Narrow it to hunt a
            differential; widen it to see the whole market.
          </p>
          <RangeSlider
            format={(value) => `${value.toFixed(1)}%`}
            from={view.ownedFrom}
            label="Ownership"
            max={OWNERSHIP_CAP}
            min={0}
            onChange={({ from, to }) =>
              onChange({ ownedFrom: from, ownedTo: to })
            }
            step={0.1}
            to={view.ownedTo}
          />
        </fieldset>

        <fieldset className="scatter-fieldset">
          <legend>Price bracket</legend>
          <p className="scatter-hint">
            Only players costing inside this range are drawn. A replacement has
            to be affordable to be a replacement, so narrowing here compares
            players you could actually swap between.
          </p>
          <RangeSlider
            format={(value) => `\u00a3${(value / 10).toFixed(1)}m`}
            from={view.priceFromTenths}
            label="Price"
            max={PRICE_CAP_TENTHS}
            min={0}
            onChange={({ from, to }) =>
              onChange({ priceFromTenths: from, priceToTenths: to })
            }
            step={1}
            to={view.priceToTenths}
          />
        </fieldset>

        <p className="scatter-plotted" aria-live="polite">
          {plotted} players plotted.
        </p>
        <button type="button" className="scatter-reset" onClick={onReset}>
          Reset the view
        </button>
      </div>
    </details>
  );
}

function AxisPicker({
  allowNone = false,
  id,
  label,
  value,
  onChange,
}: {
  allowNone?: boolean;
  id: string;
  label: string;
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <>
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {allowNone ? <option value={NO_SIZE}>None, all the same</option> : null}
        {GROUP_ORDER.map((group) => (
          <optgroup key={group} label={group}>
            {METRICS.filter((entry) => entry.group === group).map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </>
  );
}

/** Only offered where the spread is multiplicative; hidden rather than disabled. */
function LogToggle({
  id,
  metricId,
  checked,
  onChange,
}: {
  id: string;
  metricId: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  const allowed = METRICS.find((entry) => entry.id === metricId)?.allowLog;
  if (!allowed) return null;
  return (
    <label className="scatter-check" htmlFor={id}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      Log scale
    </label>
  );
}

function toggle(values: string[], entry: string): string[] {
  return values.includes(entry)
    ? values.filter((value) => value !== entry)
    : [...values, entry];
}

/**
 * Empty means every position, and the boxes render checked to say so. Unticking
 * one from that state has to start from all of them, or the first click would
 * select a position rather than remove it.
 */
function togglePosition(
  selected: string[],
  code: string,
  all: readonly string[],
): string[] {
  const from = selected.length === 0 ? [...all] : selected;
  const next = toggle(from, code);
  return next.length === all.length ? [] : next;
}
