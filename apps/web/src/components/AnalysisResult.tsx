import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";

import { readDeclaredSquad } from "../state/declared-squad";
import { nextDeadlineAt } from "../state/season-deadlines";
import type { TeamAnalysisState } from "../state/team-analysis";
import {
  staleReason,
  terminalStateMessage,
} from "../state/team-analysis-messages";
import { currentPlanningEvent } from "../state/use-team-start";
import { DeclaredSquadBuilder } from "./DeclaredSquadBuilder";
import { ManagerHistory } from "./ManagerHistory";
import { OpeningSquad } from "./OpeningSquad";
import { SnapshotDossier } from "./SnapshotDossier";
import { TransferPlanPanel } from "./TransferPlanPanel";

/**
 * One switch over the analysis state, and the panel each case renders.
 *
 * Every branch here is a decision about what may be shown
 * when the evidence is incomplete, which is the thing this project is most
 * careful about -- and it was buried two hundred lines into the application
 * root.
 */

interface AnalysisResultProps {
  analysis: TeamAnalysisState;
  entryId: number;
  onRetry: () => void;
  /** Bumped whenever the declared squad changes, so this re-reads it. */
  declaredAt?: number;
  onDeclared?: () => void;
}

export function AnalysisResult({
  analysis,
  entryId,
  onRetry,
  declaredAt = 0,
  onDeclared = () => undefined,
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
  const currentEvent = currentPlanningEvent();
  const canDeclare =
    analysis.status === "unavailable" &&
    analysis.reason === "no_processed_event";
  // The season has not started, so there is nothing a retry could reach. A
  // button that cannot work is worse than no button.
  const retryable = !canDeclare;
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
        {retryable ? (
          <button className="secondary-command" onClick={onRetry} type="button">
            <RefreshCw aria-hidden="true" size={17} /> Retry analysis
          </button>
        ) : null}
      </section>
      {canDeclare ? <ManagerHistory entryId={entryId} /> : null}
      {canDeclare ? (
        <>
          <section
            className="outage-squad"
            aria-labelledby="outage-squad-title"
          >
            <h2 className="visually-hidden" id="outage-squad-title">
              Continue without FPL
            </h2>
            <DeclaredSquadBuilder
              entryId={entryId}
              event={currentEvent}
              onDeclared={onDeclared}
            />
            <p className="plan-team-note">
              <strong>Model opening plan, not your team.</strong> This is a
              reference while no verified or manager-provided fifteen is
              available.
            </p>
            <OpeningSquad {...(currentEvent === 1 ? { entryId } : {})} />
          </section>
          {/* Only while there is nothing to plan from. Once a fifteen is
              locked in the season below IS the transfer plan, and a panel
              saying "not yet" beside it contradicts the page. */}
          {hasDeclaredSquad(entryId, currentEvent, declaredAt) ? null : (
            <TransferPlanPanel
              firstDeadline={nextDeadlineAt()?.deadline ?? null}
            />
          )}
        </>
      ) : null}
    </>
  );
}

/**
 * `declaredAt` is unused inside, and deliberately so: it is the render key
 * that makes this storage read happen again after a lock-in.
 */
function hasDeclaredSquad(
  entryId: number,
  event: number,
  declaredAt: number,
): boolean {
  void declaredAt;
  return readDeclaredSquad(window.localStorage, entryId, event) !== null;
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
