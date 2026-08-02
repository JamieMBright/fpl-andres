import type { PublicTeamState } from "@fpl-andres/contracts";
import { CheckCircle2, ChevronDown, Database } from "lucide-react";
import { lazy } from "react";

import {
  integer as integerFormatter,
  money as moneyFormatter,
  timestamp as timestampFormatter,
} from "../format";
import { FIRST_DEADLINE_2026_27 } from "../public-ids";
import { LazyRoute } from "./LazyRoute";
import { ManagerHistory } from "./ManagerHistory";
import { TeamStateCorrections } from "./TeamStateCorrections";
import { TransferPlanPanel } from "./TransferPlanPanel";

/**
 * The observed squad, its provenance, and the corrections form.
 *
 * Audit item #115. These two lazy imports read the 213 kB projection artifact,
 * so they carry it into whichever chunk they land in. Keeping them beside the
 * only component that renders them is what keeps that chunk off the first
 * paint of every other route.
 */
const PitchView = lazy(() =>
  import("./PitchView").then((module) => ({ default: module.PitchView })),
);
const SquadRecord = lazy(() =>
  import("./SquadRecord").then((module) => ({ default: module.SquadRecord })),
);

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
          This is what FPL recorded at the Gameweek {state.event} deadline. It
          does not reveal transfers, prices or chips changed since then.
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

      <section className="dossier-section" aria-labelledby="squad-title">
        <div className="dossier-heading dossier-heading-compact">
          <div>
            <p className="eyebrow">As it stood</p>
            <h2 id="squad-title">Your last-deadline squad</h2>
          </div>
          <span className="mono">{state.picks.length} picks</span>
        </div>
        <LazyRoute>
          <PitchView picks={state.picks} />
        </LazyRoute>
        <details className="squad-table-disclosure">
          <summary>Same squad as a table</summary>
          <div
            aria-label="Scrollable last-deadline squad"
            className="squad-table-wrap"
            role="region"
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
            tabIndex={0}
          >
            <table aria-label="Last-deadline squad">
              <thead>
                <tr>
                  <th scope="col">Slot</th>
                  <th scope="col">Player</th>
                  <th scope="col">Pos</th>
                  <th scope="col">Club</th>
                  <th scope="col">Price</th>
                  <th scope="col">Assignment</th>
                  <th scope="col">Multiplier</th>
                </tr>
              </thead>
              <tbody>
                {state.picks.map((pick) => (
                  <tr key={pick.squadPosition}>
                    <td className="mono">{pick.squadPosition}</td>
                    <th scope="row" translate="no">
                      {pick.identity
                        ? pick.identity.webName
                        : `FPL element ${pick.elementId}`}
                    </th>
                    <td className="mono">
                      {pick.identity ? pick.identity.positionCode : "—"}
                    </td>
                    <td className="mono" translate="no">
                      {pick.identity ? pick.identity.teamShortName : "—"}
                    </td>
                    <td className="mono">
                      {pick.identity
                        ? formatFplMoney(pick.identity.priceTenths)
                        : "—"}
                    </td>
                    <td>{pickAssignment(pick)}</td>
                    <td className="mono">{pick.multiplier}×</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>

      <LazyRoute>
        <SquadRecord picks={state.picks} />
      </LazyRoute>

      <ManagerHistory entryId={state.entryId} />

      <TransferPlanPanel firstDeadline={FIRST_DEADLINE_2026_27} />

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

function pickAssignment(pick: PublicTeamState["picks"][number]): string {
  if (pick.isCaptain) return "Captain";
  if (pick.isViceCaptain) return "Vice-captain";
  return pick.multiplier === 0 ? "Bench" : "Starting XI";
}
