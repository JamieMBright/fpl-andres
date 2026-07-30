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

const SOCIAL_LINKS = [
  {
    name: "X",
    href: "https://x.com/fpl_andres",
    path: "M18.9 2H22l-7.3 8.3L23 22h-6.6l-5.2-6.8L5.3 22H2.2l7.8-8.9L1.7 2h6.8l4.7 6.2zm-1.1 18h1.7L7.3 3.7H5.5z",
  },
  {
    name: "Reddit",
    href: "https://reddit.com/user/fpl_andres",
    path: "M22 12a2 2 0 0 0-3.4-1.4 10 10 0 0 0-5.1-1.6l.9-4.1 2.9.6a1.7 1.7 0 1 0 .2-1l-3.4-.7a.5.5 0 0 0-.6.4l-1 4.8a10 10 0 0 0-5.2 1.6A2 2 0 1 0 4.6 14a4 4 0 0 0 0 .6c0 3 3.4 5.4 7.5 5.4s7.4-2.4 7.4-5.4a4 4 0 0 0 0-.6A2 2 0 0 0 22 12M7.5 13.4a1.4 1.4 0 1 1 1.4 1.4 1.4 1.4 0 0 1-1.4-1.4m7.7 4a5 5 0 0 1-3.1.9 5 5 0 0 1-3.2-.9.4.4 0 0 1 .5-.6 4.2 4.2 0 0 0 2.7.7 4.2 4.2 0 0 0 2.6-.7.4.4 0 1 1 .5.6m-.2-2.6a1.4 1.4 0 1 1 1.4-1.4 1.4 1.4 0 0 1-1.4 1.4",
  },
  {
    name: "Instagram",
    href: "https://instagram.com/fpl_andres",
    path: "M12 2.2c3.2 0 3.6 0 4.9.1 3.3.1 4.8 1.7 5 5 0 1.3.1 1.6.1 4.7s0 3.5-.1 4.8c-.2 3.3-1.7 4.9-5 5-1.3.1-1.7.1-4.9.1s-3.6 0-4.9-.1c-3.3-.1-4.8-1.7-5-5C2 15.5 2 15.1 2 12s0-3.4.1-4.7c.2-3.3 1.7-4.9 5-5C8.4 2.2 8.8 2.2 12 2.2m0 5.1A4.7 4.7 0 1 0 16.7 12 4.7 4.7 0 0 0 12 7.3m0 7.7A3 3 0 1 1 15 12a3 3 0 0 1-3 3m4.9-8.9a1.1 1.1 0 1 0 1.1 1.1 1.1 1.1 0 0 0-1.1-1.1",
  },
  {
    name: "TikTok",
    href: "https://tiktok.com/@fpl_andres",
    path: "M16.6 2h-3v13.1a2.4 2.4 0 1 1-2.4-2.4c.2 0 .4 0 .6.1V9.7h-.6a5.4 5.4 0 1 0 5.4 5.4V8.6a6.2 6.2 0 0 0 3.6 1.2V6.8a3.4 3.4 0 0 1-3.6-3.3z",
  },
  {
    name: "YouTube",
    href: "https://youtube.com/@fpl_andres",
    path: "M21.6 7.2a2.5 2.5 0 0 0-1.8-1.8C18.2 5 12 5 12 5s-6.2 0-7.8.4a2.5 2.5 0 0 0-1.8 1.8A26 26 0 0 0 2 12a26 26 0 0 0 .4 4.8 2.5 2.5 0 0 0 1.8 1.8C5.8 19 12 19 12 19s6.2 0 7.8-.4a2.5 2.5 0 0 0 1.8-1.8A26 26 0 0 0 22 12a26 26 0 0 0-.4-4.8M10 15V9l5.2 3z",
  },
] as const;

const TELETEXT_CELLS = [
  "P100",
  "ANDRES",
  "xPTS",
  "OOP",
  "DEFCON",
  "@FPL_ANDRES",
] as const;

type ThemeName = "dark" | "light";

const THEME_STORAGE_KEY = "fpl-andres:theme";

function readStoredTheme(): ThemeName {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === "light"
      ? "light"
      : "dark";
  } catch {
    // A blocked storage partition must not stop the page rendering.
    return "dark";
  }
}

function BielsaBucket() {
  return (
    <svg
      aria-hidden="true"
      className="brand-mark"
      viewBox="0 0 260 200"
      xmlns="http://www.w3.org/2000/svg"
    >
      <ellipse
        cx="130"
        cy="186"
        fill="currentColor"
        opacity="0.25"
        rx="104"
        ry="6"
      />
      <path
        d="M 84 30 Q 130 24 176 30 Q 188 30 192 42 C 214 82 226 128 226 168 Q 226 178 216 178 Q 130 184 44 178 Q 34 178 34 168 C 34 128 46 82 68 42 Q 72 30 84 30 Z"
        fill="currentColor"
      />
      <path
        d="M 88 32 Q 130 26 172 32"
        fill="none"
        stroke="#fff"
        strokeLinecap="round"
        strokeOpacity="0.35"
        strokeWidth="1.4"
      />
      <rect fill="#f8f6ea" height="36" rx="3" width="144" x="58" y="104" />
      <text
        fill="#4a008e"
        fontFamily="'IBM Plex Mono', ui-monospace, monospace"
        fontSize="18"
        fontWeight="700"
        textAnchor="middle"
        x="130"
        y="128"
      >
        @fpl_andres
      </text>
    </svg>
  );
}

function RouteHeading({
  children,
  translate,
}: PropsWithChildren<{ translate?: "yes" | "no" }>) {
  return (
    <h1 tabIndex={-1} translate={translate}>
      {children}
    </h1>
  );
}

function ApplicationFrame() {
  const location = useLocation();
  const previousPath = useRef(location.pathname);
  const [theme, setTheme] = useState<ThemeName>(readStoredTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Preference is cosmetic; failing to persist it is not an error.
    }
  }, [theme]);

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
      <div aria-hidden="true" className="teletext-strip">
        {TELETEXT_CELLS.map((cell) => (
          <span key={cell}>{cell}</span>
        ))}
      </div>
      <header className="site-header">
        <Link aria-label="FPL Andres home" className="brand" to="/">
          <BielsaBucket />
          <span>
            <strong translate="no">FPL Andres</strong>
            <small>Analysis, not opinion</small>
          </span>
        </Link>
        <div className="header-controls">
          <nav aria-label="Primary navigation">
            <Link to="/methodology">Method</Link>
            <Link to="/calibration">Calibration</Link>
          </nav>
          <button
            aria-pressed={theme === "light"}
            className="theme-toggle"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            type="button"
          >
            {theme === "dark" ? "Third kit" : "Home kit"}
          </button>
        </div>
      </header>
      <main id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="site-footer">
        <p>Independent analysis. Not affiliated with Fantasy Premier League.</p>
        <ul className="social-links">
          {SOCIAL_LINKS.map((social) => (
            <li key={social.name}>
              <a
                aria-label={`FPL Andres on ${social.name}`}
                href={social.href}
                rel="me noopener noreferrer"
                target="_blank"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d={social.path} />
                </svg>
              </a>
            </li>
          ))}
        </ul>
        <p className="mono">I only read what FPL makes public.</p>
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
          <Clock3 aria-hidden="true" size={17} /> Reading the public record
        </span>
        <span className="mono">All forecasts are wrong. Some are useful.</span>
      </section>

      <section className="analysis-entry">
        <div className="section-index" aria-hidden="true">
          01 / TEAM ID
        </div>
        <div className="entry-copy">
          <RouteHeading>Let me look at your squad.</RouteHeading>
          <p className="lede">
            Give me your Team ID and I&rsquo;ll pull what FPL last recorded —
            squad, captain, bank, transfers — and show you exactly where each
            number came from. Changed something since the deadline? Tell me. I
            won&rsquo;t guess.
          </p>
        </div>

        <form className="team-form" noValidate onSubmit={analyseTeam}>
          <label htmlFor="team-id">Your FPL team ID</label>
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
              Analyse my squad <ArrowRight aria-hidden="true" size={19} />
            </button>
          </div>
          <p className="field-hint" id="team-id-hint">
            It&rsquo;s in the URL on your FPL points page. No login, no password
            — I only read what&rsquo;s already public.
          </p>
          {error ? (
            <p className="field-error" id="team-id-error" role="alert">
              {error}
            </p>
          ) : null}
        </form>
      </section>

      <section className="briefing-grid" aria-label="How I work">
        <article>
          <div className="briefing-icon">
            <FileSearch aria-hidden="true" size={21} />
          </div>
          <p className="eyebrow">The record</p>
          <h2>I show you what FPL recorded</h2>
          <p>
            Your squad, captain, bank and transfers as they stood at the last
            deadline. Nothing appears until the source checks out.
          </p>
        </article>
        <article>
          <div className="briefing-icon">
            <Clock3 aria-hidden="true" size={21} />
          </div>
          <p className="eyebrow">Your corrections</p>
          <h2>What&rsquo;s changed since, you tell me</h2>
          <p>
            FPL won&rsquo;t show me your moves until the next deadline. Yours
            stay on your machine, and I keep them apart from the public record.
          </p>
        </article>
        <article>
          <div className="briefing-icon">
            <ShieldCheck aria-hidden="true" size={21} />
          </div>
          <p className="eyebrow">My working</p>
          <h2>Every number, sourced</h2>
          <p>
            Timestamps and hashes stay attached to everything I show you. Where
            I can&rsquo;t source it, I say so rather than fill the gap.
          </p>
        </article>
      </section>
    </>
  );
}

function TeamAnalysisRoute() {
  const { teamId } = useParams();
  return <TeamAnalysisPage key={teamId ?? "no-team"} />;
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
            <p className="eyebrow">As it stood</p>
            <h2 id="squad-title">Your last-deadline squad</h2>
          </div>
          <span className="mono">{state.picks.length} picks</span>
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
      </section>

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
    { status: "idle" | "loading" | "refreshing" | "ready" | "stale" }
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
      <p className="eyebrow">Method</p>
      <RouteHeading>How I work.</RouteHeading>
      <p>
        All forecasts are wrong. Some are useful. A model only goes live here
        once it has beaten its baseline on seasons it never saw during training
        — and I show you that margin rather than asking you to take my word for
        it.
      </p>
      <p>
        Where the evidence isn&rsquo;t there, I say nothing. That will happen
        more often than you&rsquo;d like early on.
      </p>
    </section>
  );
}

function CalibrationPage() {
  return (
    <section className="text-page">
      <p className="eyebrow">Calibration</p>
      <RouteHeading>I keep score on myself.</RouteHeading>
      <p>
        Nothing to show you yet. No model has been promoted, so there are no
        results worth putting my name to.
      </p>
      <p>
        When there are, this is where they go: how often I was right, by how
        much, and where I was worst. Including the times I disagreed with the
        crowd and the crowd was right.
      </p>
    </section>
  );
}

function NotFoundPage() {
  return (
    <section className="text-page">
      <p className="eyebrow">Wrong turn</p>
      <RouteHeading>Nothing here.</RouteHeading>
      <p>That page doesn&rsquo;t exist. Let&rsquo;s start again.</p>
      <Link className="text-command" to="/">
        Back to the Team ID
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
      { path: "team/:teamId", element: <TeamAnalysisRoute /> },
      { path: "methodology", element: <MethodPage /> },
      { path: "calibration", element: <CalibrationPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
