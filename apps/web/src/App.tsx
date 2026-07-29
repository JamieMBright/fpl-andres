import type { PublicTeamState } from "@fpl-andres/contracts";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Database,
  FileSearch,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import {
  useEffect,
  useReducer,
  useRef,
  useState,
  type FormEvent,
  type PropsWithChildren,
} from "react";
import {
  Link,
  Outlet,
  useLocation,
  useNavigate,
  useParams,
  type RouteObject,
} from "react-router-dom";

import { TeamStateCorrections } from "./components/TeamStateCorrections";
import {
  initialTeamAnalysisState,
  loadCachedPublicTeamState,
  reduceTeamAnalysis,
  refreshTeamAnalysis,
  type TeamAnalysisState,
} from "./state/team-analysis";

const MAX_PUBLIC_ID = 4_294_967_295;
const moneyFormatter = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const integerFormatter = new Intl.NumberFormat("en-GB");
const timestampFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/London",
  timeZoneName: "short",
});

function DossierMark() {
  return (
    <svg
      aria-hidden="true"
      className="brand-mark"
      viewBox="0 0 48 48"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M8 6h25l7 7v29H8z" fill="currentColor" />
      <path d="M33 6v8h7" fill="none" stroke="var(--paper)" strokeWidth="2" />
      <path
        d="M15 20h18M15 27h14M15 34h18"
        stroke="var(--paper)"
        strokeWidth="2"
      />
      <path d="M15 38h10" stroke="var(--signal-blue)" strokeWidth="3" />
    </svg>
  );
}

function RouteHeading({ children }: PropsWithChildren) {
  return <h1 tabIndex={-1}>{children}</h1>;
}

function ApplicationFrame() {
  const location = useLocation();
  const previousPath = useRef(location.pathname);

  useEffect(() => {
    if (previousPath.current === location.pathname) {
      return;
    }

    previousPath.current = location.pathname;
    document.querySelector<HTMLElement>("main h1")?.focus();
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="site-header">
        <Link aria-label="FPL Andres home" className="brand" to="/">
          <DossierMark />
          <span>
            <strong translate="no">FPL Andres</strong>
            <small>Decision desk</small>
          </span>
        </Link>
        <nav aria-label="Primary navigation">
          <Link to="/methodology">Method</Link>
          <Link to="/calibration">Calibration</Link>
        </nav>
      </header>
      <main id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="site-footer">
        <p>Independent analysis. Not affiliated with Fantasy Premier League.</p>
        <p className="mono">Observed state · local corrections</p>
      </footer>
    </div>
  );
}

function HomePage() {
  const navigate = useNavigate();
  const [teamId, setTeamId] = useState("");
  const [error, setError] = useState<string | null>(null);

  function analyseTeam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = teamId.trim();

    const parsedTeamId = Number(normalized);
    if (!/^[1-9]\d{0,9}$/.test(normalized) || parsedTeamId > MAX_PUBLIC_ID) {
      setError("Enter a numeric FPL team ID.");
      return;
    }

    setError(null);
    void navigate(`/team/${normalized}`);
  }

  return (
    <>
      <section className="deadline-strip" aria-label="Current capability">
        <span>
          <Clock3 aria-hidden="true" size={17} /> Public state review
        </span>
        <span className="mono">Last-deadline evidence · local corrections</span>
      </section>

      <section className="analysis-entry">
        <div className="section-index" aria-hidden="true">
          01 / IDENTIFY
        </div>
        <div className="entry-copy">
          <p className="eyebrow">Your squad at the last processed deadline</p>
          <RouteHeading>What did FPL last record for your squad?</RouteHeading>
          <p className="lede">
            Enter a public Team ID to inspect its validated squad, bank,
            transfers, freshness and exact source trail. Add local corrections
            for changes made since the deadline.
          </p>
        </div>

        <form className="team-form" noValidate onSubmit={analyseTeam}>
          <label htmlFor="team-id">FPL team ID</label>
          <div className="input-command">
            <input
              aria-describedby={
                error ? "team-id-hint team-id-error" : "team-id-hint"
              }
              aria-invalid={error !== null}
              autoComplete="off"
              id="team-id"
              inputMode="numeric"
              maxLength={10}
              onChange={(event) => setTeamId(event.target.value)}
              placeholder="e.g. 212279…"
              value={teamId}
            />
            <button type="submit">
              Analyse team <ArrowRight aria-hidden="true" size={19} />
            </button>
          </div>
          <p className="field-hint" id="team-id-hint">
            Find it in the URL on your FPL points page. No login or password.
          </p>
          {error ? (
            <p className="field-error" id="team-id-error" role="alert">
              {error}
            </p>
          ) : null}
        </form>
      </section>

      <section
        className="briefing-grid"
        aria-label="What the analysis provides"
      >
        <article>
          <div className="briefing-icon">
            <FileSearch aria-hidden="true" size={21} />
          </div>
          <p className="eyebrow">Public record</p>
          <h2>Observed state first</h2>
          <p>
            Squad, captaincy, bank and transfer history shown only after the
            source contract passes.
          </p>
        </article>
        <article>
          <div className="briefing-icon">
            <Clock3 aria-hidden="true" size={21} />
          </div>
          <p className="eyebrow">Since deadline</p>
          <h2>Deadline-bound updates</h2>
          <p>
            Manager-supplied bank, free transfers, queued moves and chips stay
            local and separate.
          </p>
        </article>
        <article>
          <div className="briefing-icon">
            <ShieldCheck aria-hidden="true" size={21} />
          </div>
          <p className="eyebrow">Evidence</p>
          <h2>Exact source trail</h2>
          <p>
            Timestamps and content hashes remain attached; unavailable data is
            never replaced by a guess.
          </p>
        </article>
      </section>
    </>
  );
}

function TeamAnalysisPage() {
  const { teamId } = useParams();
  const entryId = parseTeamId(teamId);
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
    dispatch({ type: "load" });
    const cached = loadCachedPublicTeamState(localStorage, entryId);

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
      <RouteHeading>Analysis for team {entryId}</RouteHeading>
      <div
        aria-label="Analysis result"
        className="analysis-result"
        ref={resultRef}
        role="region"
        tabIndex={-1}
      >
        <AnalysisResult
          analysis={analysis}
          onRetry={() => {
            resultRef.current?.focus();
            setRefreshAttempt((attempt) => attempt + 1);
          }}
        />
      </div>
      <nav aria-label="Analysis actions" className="analysis-actions">
        <Link className="text-command" to="/">
          Analyse another team
        </Link>
      </nav>
    </section>
  );
}

interface AnalysisResultProps {
  analysis: TeamAnalysisState;
  onRetry: () => void;
}

function AnalysisResult({ analysis, onRetry }: AnalysisResultProps) {
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

function SnapshotDossier({ state }: { state: PublicTeamState }) {
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
            <p className="eyebrow">Formation sheet</p>
            <h2 id="squad-title">Last-Deadline Squad</h2>
          </div>
          <span className="mono">{state.picks.length} public picks</span>
        </div>
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
                <th scope="col">Player reference</th>
                <th scope="col">Assignment</th>
                <th scope="col">Multiplier</th>
              </tr>
            </thead>
            <tbody>
              {state.picks.map((pick) => (
                <tr key={pick.squadPosition}>
                  <td className="mono">{pick.squadPosition}</td>
                  <th scope="row" translate="no">
                    FPL element {pick.elementId}
                  </th>
                  <td>{pickAssignment(pick)}</td>
                  <td className="mono">{pick.multiplier}×</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <details className="source-trail">
        <summary>
          <span>
            <Database aria-hidden="true" size={18} /> Inspect{" "}
            {state.sourceHashes.length} source hashes
          </span>
          <ChevronDown
            aria-hidden="true"
            className="disclosure-mark"
            size={18}
          />
        </summary>
        <div className="source-trail-body">
          <p>
            These hashes identify the exact entry, picks and deadline bytes used
            for this snapshot.
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

function parseTeamId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d{0,9}$/.test(value)) return null;
  const parsed = Number(value);
  return parsed <= MAX_PUBLIC_ID ? parsed : null;
}

function formatFplMoney(valueTenths: number): string {
  return `${moneyFormatter.format(valueTenths / 10)}m`;
}

function pickAssignment(pick: PublicTeamState["picks"][number]): string {
  if (pick.isCaptain) return "Captain";
  if (pick.isViceCaptain) return "Vice-captain";
  return pick.multiplier === 0 ? "Bench" : "Starting XI";
}

function staleReason(
  reason: Extract<TeamAnalysisState, { status: "stale" }>["reason"],
): string {
  const reasons: Record<typeof reason, string> = {
    fpl_unreachable:
      "FPL is temporarily unreachable. The last verified state remains visible.",
    fpl_source_failed:
      "FPL returned a failed source response. The last verified state remains visible.",
    source_contract_failed:
      "FPL source fields changed or disagreed. The last verified state remains visible.",
    network_error:
      "The refresh request could not connect. The last verified state remains visible.",
    invalid_response:
      "The refresh response failed validation. The last verified state remains visible.",
  };
  return reasons[reason];
}

function terminalStateMessage(
  analysis: Exclude<
    TeamAnalysisState,
    { status: "idle" | "loading" | "ready" | "stale" }
  >,
) {
  if (analysis.status === "unavailable") {
    const unavailable = {
      entry_unavailable: {
        heading: "Team Not Available",
        nextStep:
          "Check the Team ID on your official FPL points-page URL, then try again.",
      },
      no_processed_event: {
        heading: "No processed gameweek yet",
        nextStep:
          "Try again after FPL publishes the first processed event for this team.",
      },
      picks_unavailable: {
        heading: "Gameweek Picks Not Available",
        nextStep: `FPL has no public picks for Gameweek ${analysis.event ?? "this event"}. Try again after processing completes.`,
      },
    }[analysis.reason];
    return {
      tone: "unavailable",
      title: "Public state unavailable",
      detail: "No squad snapshot has been inferred or substituted.",
      ...unavailable,
    };
  }

  const failure = {
    fpl_unreachable: {
      heading: "FPL Cannot Be Reached",
      nextStep: "Wait a moment, then retry the analysis.",
    },
    fpl_source_failed: {
      heading: "FPL Source Request Failed",
      nextStep:
        "Retry after FPL has recovered. No partial source data was used.",
    },
    source_contract_failed: {
      heading: "FPL Source Data Changed",
      nextStep:
        "Retry later while the source contract is reviewed. No incompatible data was used.",
    },
    network_error: {
      heading: "Network Request Failed",
      nextStep: "Check your connection, then retry the analysis.",
    },
    invalid_response: {
      heading: "Analysis Response Failed Validation",
      nextStep:
        "Retry later. No unvalidated response has been displayed or cached.",
    },
  }[analysis.reason];
  return {
    tone: "error",
    title: "No verified snapshot available",
    detail: "The analysis stopped instead of manufacturing team state.",
    ...failure,
  };
}

function MethodPage() {
  return (
    <section className="text-page">
      <p className="eyebrow">Methodology</p>
      <RouteHeading>Evidence before confidence.</RouteHeading>
      <p>
        Every active model must beat or calibrate better than its documented
        baseline.
      </p>
    </section>
  );
}

function CalibrationPage() {
  return (
    <section className="text-page">
      <p className="eyebrow">Calibration</p>
      <RouteHeading>The analyst keeps score.</RouteHeading>
      <p>
        Live sample sizes and walk-forward results will appear here as models
        are promoted.
      </p>
    </section>
  );
}

function NotFoundPage() {
  return (
    <section className="text-page">
      <p className="eyebrow">Route unavailable</p>
      <RouteHeading>Page Not Found</RouteHeading>
      <p>The requested page does not exist in this decision desk.</p>
      <Link className="text-command" to="/">
        Return to Team ID entry
      </Link>
    </section>
  );
}

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <ApplicationFrame />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "team/:teamId", element: <TeamAnalysisPage /> },
      { path: "methodology", element: <MethodPage /> },
      { path: "calibration", element: <CalibrationPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
