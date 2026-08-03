import { useId } from "react";

import { METRICS, type MetricGroup } from "../state/analysis-metrics";
import type { AnalysisPool } from "../state/analysis-pool";
import type { ColourBy, ScatterView } from "../state/scatter-view";

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
  // keyboard behaviour and the open-by-default in one attribute.
  return (
    <details className="scatter-controls" open>
      <summary className="scatter-controls-summary">
        <span>Configuration</span>
        <span className="scatter-controls-count mono">{plotted} plotted</span>
      </summary>
      <div className="scatter-controls-body">
        <div className="scatter-control-row">
          <AxisPicker
            id={`${ids}-x`}
            label="Across"
            value={view.x}
            onChange={(x) => onChange({ x })}
          />
          <LogToggle
            id={`${ids}-logx`}
            metricId={view.x}
            checked={view.logX}
            onChange={(logX) => onChange({ logX })}
          />
        </div>

        <div className="scatter-control-row">
          <AxisPicker
            id={`${ids}-y`}
            label="Up"
            value={view.y}
            onChange={(y) => onChange({ y })}
          />
          <LogToggle
            id={`${ids}-logy`}
            metricId={view.y}
            checked={view.logY}
            onChange={(logY) => onChange({ logY })}
          />
        </div>

        <div className="scatter-control-row">
          <AxisPicker
            id={`${ids}-size`}
            label="Bubble size"
            value={view.size}
            onChange={(size) => onChange({ size })}
          />
        </div>

        <fieldset className="scatter-fieldset">
          <legend>Colour by</legend>
          {(["position", "club"] as ColourBy[]).map((mode) => (
            <label key={mode} className="scatter-radio">
              <input
                type="radio"
                name={`${ids}-colour`}
                checked={view.colourBy === mode}
                onChange={() => onChange({ colourBy: mode })}
              />
              {mode === "position" ? "Position" : "Club"}
            </label>
          ))}
        </fieldset>

        <fieldset className="scatter-fieldset">
          <legend>Positions</legend>
          {pool.positions.map((code) => (
            <label key={code} className="scatter-check">
              <input
                type="checkbox"
                checked={view.positions.includes(code)}
                onChange={() =>
                  onChange({ positions: toggle(view.positions, code) })
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
          <label htmlFor={`${ids}-search`}>Find a player</label>
          <input
            id={`${ids}-search`}
            type="search"
            value={view.search}
            placeholder="Name or club"
            onChange={(event) => onChange({ search: event.target.value })}
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
        </fieldset>

        <fieldset className="scatter-fieldset">
          <legend>Overlooked</legend>
          <label className="scatter-check">
            <input
              type="checkbox"
              checked={view.overlooked}
              onChange={() => onChange({ overlooked: !view.overlooked })}
            />
            Ring the strong quadrant nobody owns
          </label>
          <label htmlFor={`${ids}-owned`}>
            Owned by under
            <span className="scatter-value">{view.overlookedCeiling}%</span>
          </label>
          <input
            id={`${ids}-owned`}
            type="range"
            min={1}
            max={50}
            step={1}
            value={view.overlookedCeiling}
            onChange={(event) =>
              onChange({ overlookedCeiling: Number(event.target.value) })
            }
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
  id,
  label,
  value,
  onChange,
}: {
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
