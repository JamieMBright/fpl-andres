import { useMemo, useState } from "react";

import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import {
  recordAnalysisRequest,
  saveDeclaredTransfer,
  type DeclaredTransfer,
} from "../state/declared-transfers";

/**
 * Tell me a transfer FPL has not published yet.
 *
 * A manager's picks for the coming gameweek are private until the deadline
 * passes, so the squad this site can read is the one he finished the last
 * gameweek with. Without this, the plan opens by recommending a transfer he
 * made on Tuesday.
 *
 * Stored in his own browser. The server gets a copy it never reads back, so a
 * forged row cannot change anybody's plan — which matters because a Team ID is
 * public and anyone could guess someone else's.
 */

export interface DeclaredTransferFormProps {
  entryId: number;
  event: number;
  season: string;
  onDeclared: () => void;
}

export function DeclaredTransferForm({
  entryId,
  event,
  season,
  onDeclared,
}: DeclaredTransferFormProps) {
  const [out, setOut] = useState("");
  const [incoming, setIncoming] = useState("");
  const [charged, setCharged] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  const players = useMemo(
    () =>
      [...PLAYERS_BY_ELEMENT_ID.values()].sort((left, right) =>
        left.name.localeCompare(right.name),
      ),
    [],
  );

  const submit = (submitted: React.FormEvent) => {
    submitted.preventDefault();
    const elementOut = Number(out);
    const elementIn = Number(incoming);
    if (!elementOut || !elementIn || elementOut === elementIn) return;

    const transfer: DeclaredTransfer = {
      event,
      elementOut,
      elementIn,
      pointsCharged: charged ? 4 : 0,
    };
    saveDeclaredTransfer(window.localStorage, entryId, transfer);
    recordAnalysisRequest({ season, entryId, event, transfer });
    setSaved(
      `${PLAYERS_BY_ELEMENT_ID.get(elementOut)?.name ?? "out"} out, ` +
        `${PLAYERS_BY_ELEMENT_ID.get(elementIn)?.name ?? "in"} in.`,
    );
    setOut("");
    setIncoming("");
    onDeclared();
  };

  return (
    <details className="scatter-controls plan-declared">
      <summary className="scatter-controls-summary">
        <span>Transfer made since the last deadline</span>
        <span className="scatter-controls-count mono">GW{event}</span>
      </summary>
      <div className="scatter-controls-body">
        <p className="scatter-hint">
          The public squad is one deadline behind. Add a completed move here so
          the solve starts from what you own now. It stays in this browser.
        </p>
        <form className="plan-declared-form" onSubmit={submit}>
          <label htmlFor="declared-out">Out</label>
          <select
            id="declared-out"
            value={out}
            onChange={(changed) => setOut(changed.target.value)}
          >
            <option value="">Pick a player</option>
            {players.map((player) => (
              <option key={player.id} value={player.id}>
                {player.name} ({player.club})
              </option>
            ))}
          </select>

          <label htmlFor="declared-in">In</label>
          <select
            id="declared-in"
            value={incoming}
            onChange={(changed) => setIncoming(changed.target.value)}
          >
            <option value="">Pick a player</option>
            {players.map((player) => (
              <option key={player.id} value={player.id}>
                {player.name} ({player.club})
              </option>
            ))}
          </select>

          <label className="scatter-check">
            <input
              type="checkbox"
              checked={charged}
              onChange={(changed) => setCharged(changed.target.checked)}
            />
            It cost me four points
          </label>

          <button type="submit">Apply it</button>
        </form>
        {saved ? (
          <p className="scatter-hint" role="status">
            {saved} The plan below starts from that squad.
          </p>
        ) : null}
      </div>
    </details>
  );
}
