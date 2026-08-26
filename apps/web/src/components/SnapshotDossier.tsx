import type { PublicTeamState } from "@fpl-andres/contracts";
import { CheckCircle2, ChevronDown, Database } from "lucide-react";

import {
  integer as integerFormatter,
  money as moneyFormatter,
  timestamp as timestampFormatter,
} from "../format";
import { ManagerHistory } from "./ManagerHistory";
import { TeamStateCorrections } from "./TeamStateCorrections";

export function SnapshotDossier({ state }: { state: PublicTeamState }) {
  return (
    <div className="dossier">
      <section className="dossier-section" aria-labelledby="snapshot-title">
        <div className="dossier-heading">
          <div>
            <p className="eyebrow">Decision input · observed</p>
            <h2 id="snapshot-title">Last-Deadline State</h2>
          </div>
          <span className="evidence-chip">
            <CheckCircle2 aria-hidden="true" size={15} /> Observed
          </span>
        </div>
        <p className="dossier-qualification">
          What FPL recorded at the Gameweek {state.event} deadline. Transfers,
          prices and chips changed since are not in here.
        </p>
        <dl className="dossier-metrics">
          <div>
            <dt>Bank</dt>
            <dd>{formatFplMoney(state.bankTenths)}</dd>
          </div>
          <div>
            <dt>Squad value</dt>
            <dd>{formatFplMoney(state.squadValueTenths)}</dd>
          </div>
          <div>
            <dt>GW transfers</dt>
            <dd>{integerFormatter.format(state.eventTransfers)}</dd>
          </div>
          <div>
            <dt>GW transfer cost</dt>
            <dd>
              {integerFormatter.format(state.eventTransferCostPoints)} pts
            </dd>
          </div>
        </dl>
        <dl className="evidence-metadata">
          <div>
            <dt>State as of</dt>
            <dd>{timestampFormatter.format(new Date(state.stateAsOf))}</dd>
          </div>
          <div>
            <dt>Evidence available</dt>
            <dd>
              {timestampFormatter.format(new Date(state.dataAvailableAt))}
            </dd>
          </div>
          <div>
            <dt>Active chip</dt>
            <dd>{state.activeChip ?? "None recorded"}</dd>
          </div>
        </dl>
      </section>

      <ManagerHistory entryId={state.entryId} />

      <details className="source-trail">
        <summary>
          <span>
            <Database aria-hidden="true" size={18} /> Check my working (
            {state.sourceHashes.length} sources)
          </span>
          <ChevronDown
            aria-hidden="true"
            className="disclosure-mark"
            size={18}
          />
        </summary>
        <div className="source-trail-body">
          <p>
            These are the exact bytes I read for your entry, your picks and the
            deadline. Same hashes, same answer — every time.
          </p>
          <ol>
            {state.sourceHashes.map((hash) => (
              <li key={hash}>
                <code translate="no">{hash}</code>
              </li>
            ))}
          </ol>
        </div>
      </details>
      <TeamStateCorrections state={state} />
    </div>
  );
}

function formatFplMoney(valueTenths: number): string {
  return `${moneyFormatter.format(valueTenths / 10)}m`;
}
