import { useId, useMemo, useState } from "react";

import { integer } from "../format";
import {
  transferFlow,
  transferFlowTransitionCount,
  type TransferFlowPlayer,
  type TransferFlowSeriesLike,
} from "../state/transfer-flow";

/**
 * Sentiment, not speculation: who the cohort is actually buying and selling.
 *
 * Players sorted top to bottom by net movement, most bought at the top, most
 * sold at the bottom, each drawn as a bar either side of a zero line. Two
 * sliders decide what is worth showing: how many recent gameweeks to fold
 * together, and how much movement a player needs before he is worth a row at
 * all — a name one manager dropped is not the cohort turning against him.
 */

function magnitude(row: TransferFlowPlayer): number {
  return Math.max(row.transfersIn, row.transfersOut);
}

export function Fpl500TransferFlow({
  series,
}: {
  series: TransferFlowSeriesLike;
}) {
  const ids = useId();
  const transitions = transferFlowTransitionCount(series);
  const [gwWindow, setGwWindow] = useState(1);
  const [minimum, setMinimum] = useState(5);

  const clampedWindow = Math.max(
    1,
    Math.min(gwWindow, Math.max(1, transitions)),
  );
  const all = useMemo(
    () => transferFlow(series, clampedWindow),
    [series, clampedWindow],
  );
  const filtered = all.filter((row) => magnitude(row) >= minimum);
  const shown = [...filtered].sort(
    (left, right) =>
      right.net - left.net || left.name.localeCompare(right.name),
  );
  const extent = Math.max(1, ...filtered.map((row) => magnitude(row)));

  if (transitions === 0) {
    return (
      <p className="mono fpl500-transfer-empty">
        One gameweek captured. Net movement needs a second to compare it to.
      </p>
    );
  }

  return (
    <div className="fpl500-transfer-flow">
      {transitions === 1 ? (
        <div className="scatter-control-row">
          <p>
            Gameweeks <span className="scatter-value">Last GW</span>
          </p>
        </div>
      ) : (
        <div className="scatter-control-row">
          <label htmlFor={`${ids}-window`}>
            Gameweeks
            <span className="scatter-value">
              {clampedWindow === 1
                ? "Last GW"
                : `Last ${String(clampedWindow)} GWs`}
            </span>
          </label>
          <input
            id={`${ids}-window`}
            max={transitions}
            min={1}
            onChange={(event) => setGwWindow(Number(event.target.value))}
            step={1}
            type="range"
            value={clampedWindow}
          />
          <p className="scatter-hint">
            One is the most recent gameweek alone; the maximum folds together
            every transition captured so far.
          </p>
        </div>
      )}

      <div className="scatter-control-row">
        <label htmlFor={`${ids}-minimum`}>
          Minimum transfers
          <span className="scatter-value">{minimum}</span>
        </label>
        <input
          id={`${ids}-minimum`}
          max={20}
          min={0}
          onChange={(event) => setMinimum(Number(event.target.value))}
          step={1}
          type="range"
          value={minimum}
        />
        <p className="scatter-hint">
          Below this a handful of managers reads as a trend. Raise it to keep
          only names the cohort is actually moving on.
        </p>
      </div>

      {shown.length === 0 ? (
        <p className="mono fpl500-transfer-empty">
          Nothing cleared the minimum. Lower it, or widen the gameweek window.
        </p>
      ) : (
        <div
          aria-label="Scrollable transfer flow"
          className="squad-table-wrap fpl500-transfer-flow-scroll"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll the complete transfer list.
          tabIndex={0}
        >
          <ol className="fpl500-transfer-rows">
            {shown.map((row) => {
              const inPct = (row.transfersIn / extent) * 100;
              const outPct = (row.transfersOut / extent) * 100;
              return (
                <li className="fpl500-transfer-row" key={row.elementId}>
                  <span className="fpl500-transfer-name" translate="no">
                    {row.name}
                  </span>
                  <span className="fpl500-transfer-track">
                    <span className="fpl500-transfer-out-side">
                      {row.transfersOut > 0 ? (
                        <span
                          className="fpl500-transfer-bar is-out"
                          style={{ width: `${String(outPct)}%` }}
                        />
                      ) : null}
                    </span>
                    <span aria-hidden="true" className="fpl500-transfer-zero" />
                    <span className="fpl500-transfer-in-side">
                      {row.transfersIn > 0 ? (
                        <span
                          className="fpl500-transfer-bar is-in"
                          style={{ width: `${String(inPct)}%` }}
                        />
                      ) : null}
                    </span>
                  </span>
                  <strong className="mono fpl500-transfer-net">
                    {row.net > 0 ? "+" : ""}
                    {integer.format(row.net)}
                  </strong>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}
