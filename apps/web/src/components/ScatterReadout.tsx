import { useMemo } from "react";

import { METRICS, metric as metricById } from "../state/analysis-metrics";
import { DEFCON_THRESHOLD } from "../state/analysis-pool";
import type { PlottedPlayer, Selection } from "../state/scatter-select";

/**
 * The chart as a table.
 *
 * The scatter is an `<img>` to assistive technology, which is honest -- a
 * screen reader cannot use a cloud of five hundred marks -- but it means the
 * page owes a version of the same finding that can be read. This is it, and it
 * is the surface that actually gets used for the defensive-contribution work,
 * because "who clears the bar cheapest" is a ranking, not a shape.
 */

const ROWS = 20;

export interface ScatterReadoutProps {
  selection: Selection;
  pinned: readonly number[];
  onTogglePin: (code: number) => void;
  /** Empty follows the y-axis, so changing the chart moves the table with it. */
  rankBy: string;
  onRankBy: (id: string) => void;
}

export function ScatterReadout({
  selection,
  pinned,
  onTogglePin,
  rankBy,
  onRankBy,
}: ScatterReadoutProps) {
  const chosen = rankBy === "" ? null : metricById(rankBy);
  const rankMetric = chosen ?? selection.y;

  const rows = useMemo(() => {
    const sorted = [...selection.points].sort((left, right) => {
      const a = rankMetric.value(left.player);
      const b = rankMetric.value(right.player);
      // A player the statistic does not apply to goes last rather than to zero.
      if (a === null) return 1;
      if (b === null) return -1;
      return rankMetric.higherIsBetter ? b - a : a - b;
    });
    // Anything pinned stays visible even when it ranks nowhere, because the
    // table is also how a pinned player is compared.
    const top = sorted.slice(0, ROWS);
    const missing = sorted.filter(
      (point) =>
        pinned.includes(point.player.code) &&
        !top.some((entry) => entry.player.code === point.player.code),
    );
    return [...top, ...missing];
  }, [selection.points, rankMetric, pinned]);

  const metric = rankMetric;

  const defconAxis =
    selection.x.group === "Defence" || selection.y.group === "Defence";

  // The chart says so on its own axes, which is where a reader who has just
  // moved a slider is looking. Repeating it under an empty table said it twice
  // and in the wrong place.
  if (rows.length === 0) {
    return null;
  }

  return (
    <details className="scatter-controls scatter-readout">
      <summary className="scatter-controls-summary">
        <span>Top {Math.min(ROWS, rows.length)}</span>
      </summary>
      <div className="scatter-controls-body">
        <h2 id="scatter-readout-heading">
          Ranked by
          <select
            aria-label="Rank the table by"
            className="readout-rank"
            onChange={(event) => onRankBy(event.target.value)}
            value={chosen ? chosen.id : selection.y.id}
          >
            {METRICS.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.label}
              </option>
            ))}
          </select>
        </h2>
        <p className="readout-explains">{metric.explains}</p>

        <div
          aria-label="Scrollable table of the plotted players, ranked"
          className="squad-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
          tabIndex={0}
        >
          <table className="readout-table">
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">Club</th>
                <th scope="col">Pos</th>
                <th scope="col">Price</th>
                <th scope="col">Owned</th>
                <th scope="col">{selection.x.label}</th>
                <th scope="col">{selection.y.label}</th>
                {defconAxis ? <th scope="col">Bar</th> : null}
                <th scope="col">
                  <span className="visually-hidden">Pin</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((point) => (
                <ReadoutRow
                  key={point.player.code}
                  point={point}
                  selection={selection}
                  defconAxis={defconAxis}
                  pinned={pinned.includes(point.player.code)}
                  onTogglePin={onTogglePin}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </details>
  );
}

function ReadoutRow({
  point,
  selection,
  defconAxis,
  pinned,
  onTogglePin,
}: {
  point: PlottedPlayer;
  selection: Selection;
  defconAxis: boolean;
  pinned: boolean;
  onTogglePin: (code: number) => void;
}) {
  const { player } = point;
  const threshold = DEFCON_THRESHOLD[player.position];

  return (
    <tr className={point.overlooked ? "readout-overlooked" : undefined}>
      <th scope="row">
        {player.name}
        {point.overlooked ? (
          <span className="readout-flag" title="Strong quadrant, barely owned">
            {" "}
            overlooked
          </span>
        ) : null}
      </th>
      <td>{player.club}</td>
      <td>{player.position}</td>
      <td className="readout-number">
        &pound;{(player.priceTenths / 10).toFixed(1)}m
      </td>
      <td className="readout-number">
        {player.ownership === null
          ? "\u2014"
          : `${player.ownership.toFixed(1)}%`}
      </td>
      <td className="readout-number">{selection.x.format(point.x)}</td>
      <td className="readout-number">{selection.y.format(point.y)}</td>
      {defconAxis ? (
        <td className="readout-number">
          {threshold === undefined || player.defconBarRatio === null ? (
            <span title="A goalkeeper has no route to defensive contributions">
              n/a
            </span>
          ) : (
            <span
              className={
                player.defconBarRatio >= 1 ? "readout-over" : "readout-under"
              }
              title={`${(player.defensiveContributionPer90 ?? 0).toFixed(1)} per 90 against a bar of ${threshold}`}
            >
              {player.defconBarRatio.toFixed(2)}
            </span>
          )}
        </td>
      ) : null}
      <td>
        <button
          type="button"
          className="readout-pin"
          aria-pressed={pinned}
          onClick={() => onTogglePin(player.code)}
        >
          {pinned ? "Pinned" : "Pin"}
          <span className="visually-hidden"> {player.name}</span>
        </button>
      </td>
    </tr>
  );
}
