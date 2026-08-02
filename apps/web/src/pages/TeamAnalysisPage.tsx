import { useEffect, useReducer, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AnalysisResult } from "../components/AnalysisResult";
import { RouteHeading } from "../components/RouteHeading";
import { parseTeamId } from "../public-ids";
import {
  initialTeamAnalysisState,
  loadCachedPublicTeamState,
  reduceTeamAnalysis,
  refreshTeamAnalysis,
} from "../state/team-analysis";
import { analysisAnnouncement } from "../state/team-analysis-messages";
import { useDocumentTitle } from "../state/use-document-title";

/**
 * Audit item #115.
 *
 * `TeamAnalysisRoute` exists only to key the page by team ID. Without it,
 * navigating from one team to another reuses the component instance and its
 * reducer, so the previous team's squad stays on screen while the new one
 * loads. The key is the fix, and it has to be outside the component that holds
 * the state.
 */

export default function TeamAnalysisRoute() {
  const { teamId } = useParams();
  return <TeamAnalysisPage key={teamId ?? "no-team"} />;
}

function TeamAnalysisPage() {
  const { teamId } = useParams();
  const entryId = parseTeamId(teamId);
  useDocumentTitle(
    entryId === null ? "Unknown team" : `Team ${entryId}`,
    "Your last-deadline squad, your record, and what the evidence supports next.",
  );
  const [analysis, dispatch] = useReducer(
    reduceTeamAnalysis,
    initialTeamAnalysisState,
  );
  const [refreshAttempt, setRefreshAttempt] = useState(0);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (entryId === null) return;

    let active = true;
    const controller = new AbortController();
    const cached = loadCachedPublicTeamState(localStorage, entryId);
    dispatch({ type: "load", state: cached });

    void refreshTeamAnalysis(entryId, cached, {
      storage: localStorage,
      signal: controller.signal,
    }).then((state) => {
      if (active) dispatch({ type: "resolved", state });
    });

    return () => {
      active = false;
      controller.abort();
    };
  }, [entryId, refreshAttempt]);

  if (entryId === null) {
    return (
      <section className="analysis-page">
        <RouteHeading>Team ID unavailable</RouteHeading>
        <p className="analysis-note">
          Return home and enter a numeric FPL team ID.
        </p>
      </section>
    );
  }

  return (
    <section className="analysis-page">
      <div className="section-index" aria-hidden="true">
        02 / ANALYSE
      </div>
      <p className="eyebrow">Public team snapshot</p>
      <RouteHeading translate="no">Analysis for team {entryId}</RouteHeading>
      <div
        aria-label="Analysis result"
        className="analysis-result"
        ref={resultRef}
        role="region"
        tabIndex={-1}
      >
        <AnalysisResult
          analysis={analysis}
          entryId={entryId}
          onRetry={() => {
            resultRef.current?.focus();
            setRefreshAttempt((attempt) => attempt + 1);
          }}
        />
      </div>
      {/* Announces the transition only. Marking the result region live would
          re-read the whole squad every time the state changed. */}
      <p aria-live="polite" className="visually-hidden" role="status">
        {analysisAnnouncement(analysis, entryId)}
      </p>
      <nav aria-label="Analysis actions" className="analysis-actions">
        <Link className="text-command" to="/">
          Analyse another team
        </Link>
      </nav>
    </section>
  );
}
