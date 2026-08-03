import { useMemo } from "react";

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
  /** Rank by this axis rather than the vertical one. */
  rankBy: "x" | "y";
}

export function ScatterReadout({
  selection,
  pinned,
  onTogglePin,
  rankBy,
}: ScatterReadoutProps) {
  const metric = rankBy === "x" ? selection.x : selection.y;

  const rows = useMemo(() => {
    const sorted = [...selection.points].sort((left, right) => {
      const a = rankBy === "x" ? left.x : left.y;
      const b = rankBy === "x" ? right.x : right.y;
      return metric.higherIsBetter ? b - a : a - b;
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
  }, [selection.points, rankBy, metric.higherIsBetter, pinned]);

  const defconAxis =
    selection.x.group === "Defence" || selection.y.group === "Defence";

  if (rows.length === 0) {
    return (
      <p className="readout-empty">
        Nothing survives these filters. Drop the minutes threshold or widen the
        positions.
      </p>
    );
  }

  return (
    <section
      className="scatter-readout"
      aria-labelledby="scatter-readout-heading"
    >
      <h2 id="scatter-readout-heading">
        Top {Math.min(ROWS, rows.length)} by {metric.label}
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
    </section>
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
      <td className="readout-number">{player.ownership.toFixed(1)}%</td>
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
              title={`${player.defensiveContributionPer90.toFixed(1)} per 90 against a bar of ${threshold}`}
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
