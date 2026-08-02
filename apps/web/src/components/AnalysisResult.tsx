import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";

import { FIRST_DEADLINE_2026_27 } from "../public-ids";
import type { TeamAnalysisState } from "../state/team-analysis";
import {
  staleReason,
  terminalStateMessage,
} from "../state/team-analysis-messages";
import { ManagerHistory } from "./ManagerHistory";
import { OpeningSquad } from "./OpeningSquad";
import { SnapshotDossier } from "./SnapshotDossier";
import { TransferPlanPanel } from "./TransferPlanPanel";

/**
 * One switch over the analysis state, and the panel each case renders.
 *
 * Audit item #115. Every branch here is a decision about what may be shown
 * when the evidence is incomplete, which is the thing this project is most
 * careful about -- and it was buried two hundred lines into the application
 * root.
 */

interface AnalysisResultProps {
  analysis: TeamAnalysisState;
  entryId: number;
  onRetry: () => void;
}

export function AnalysisResult({
  analysis,
  entryId,
  onRetry,
}: AnalysisResultProps) {
  if (analysis.status === "idle" || analysis.status === "loading") {
    return (
      <div
        aria-label="Evidence status"
        className="evidence-banner evidence-banner-loading"
        role="status"
      >
        <RefreshCw aria-hidden="true" className="loading-mark" size={20} />
        <div>
          <strong>Loading public team state…</strong>
          <span>Checking exact FPL source snapshots and their timestamps.</span>
        </div>
      </div>
    );
  }

  if (analysis.status === "refreshing") {
    return (
      <>
        <div
          aria-label="Evidence status"
          className="evidence-banner evidence-banner-loading"
          role="status"
        >
          <RefreshCw aria-hidden="true" className="loading-mark" size={20} />
          <div>
            <strong>Refreshing a verified snapshot</strong>
            <span>
              The last contract-validated state remains visible while fresh
              source evidence is checked.
            </span>
          </div>
        </div>
        <SnapshotDossier state={analysis.state} />
      </>
    );
  }

  if (analysis.status === "ready" || analysis.status === "stale") {
    return (
      <>
        <EvidenceBanner analysis={analysis} />
        <SnapshotDossier state={analysis.state} />
      </>
    );
  }

  const message = terminalStateMessage(analysis);
  return (
    <>
      <div
        aria-label="Evidence status"
        className={`evidence-banner evidence-banner-${message.tone}`}
        role={analysis.status === "unavailable" ? "status" : "alert"}
      >
        <AlertTriangle aria-hidden="true" size={20} />
        <div>
          <strong>{message.title}</strong>
          <span>{message.detail}</span>
        </div>
      </div>
      <section
        className="terminal-state"
        aria-labelledby="terminal-state-title"
      >
        <h2 id="terminal-state-title">{message.heading}</h2>
        <p>{message.nextStep}</p>
        <button className="secondary-command" onClick={onRetry} type="button">
          <RefreshCw aria-hidden="true" size={17} /> Retry analysis
        </button>
      </section>
      {analysis.status === "unavailable" &&
      analysis.reason === "no_processed_event" ? (
        <>
          <ManagerHistory entryId={entryId} />
          <OpeningSquad />
          <TransferPlanPanel firstDeadline={FIRST_DEADLINE_2026_27} />
        </>
      ) : null}
    </>
  );
}

function EvidenceBanner({
  analysis,
}: {
  analysis: Extract<TeamAnalysisState, { status: "ready" | "stale" }>;
}) {
  const isStale = analysis.status === "stale";
  return (
    <div
      aria-label="Evidence status"
      className={`evidence-banner evidence-banner-${isStale ? "stale" : "ready"}`}
      role="status"
    >
      {isStale ? (
        <AlertTriangle aria-hidden="true" size={20} />
      ) : (
        <CheckCircle2 aria-hidden="true" size={20} />
      )}
      <div>
        <strong>
          {isStale
            ? "Showing a stale verified snapshot"
            : "Observed snapshot ready"}
        </strong>
        <span>
          {isStale
            ? staleReason(analysis.reason)
            : "The values below passed the public-state contract."}
        </span>
      </div>
    </div>
  );
}
