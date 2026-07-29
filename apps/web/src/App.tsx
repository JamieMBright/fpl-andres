import { ArrowRight, Clock3, FileSearch, ShieldCheck } from "lucide-react";
import {
  useEffect,
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
      <header className="site-header">
        <Link aria-label="FPL Andres home" className="brand" to="/">
          <DossierMark />
          <span>
            <strong>FPL Andres</strong>
            <small>Decision desk</small>
          </span>
        </Link>
        <nav aria-label="Primary navigation">
          <Link to="/methodology">Method</Link>
          <Link to="/calibration">Calibration</Link>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="site-footer">
        <p>Independent analysis. Not affiliated with Fantasy Premier League.</p>
        <p className="mono">Public data · version 0.1</p>
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

    if (!/^[1-9]\d{0,8}$/.test(normalized)) {
      setError("Enter a numeric FPL team ID.");
      return;
    }

    setError(null);
    void navigate(`/team/${normalized}`);
  }

  return (
    <>
      <section className="deadline-strip" aria-label="Analysis scope">
        <span>
          <Clock3 aria-hidden="true" size={17} /> Next-deadline analysis
        </span>
        <span className="mono">
          Public FPL state · manual corrections supported
        </span>
      </section>

      <section className="analysis-entry">
        <div className="section-index" aria-hidden="true">
          01 / IDENTIFY
        </div>
        <div className="entry-copy">
          <p className="eyebrow">
            Your squad, as the last deadline recorded it
          </p>
          <RouteHeading>What should your next FPL move be?</RouteHeading>
          <p className="lede">
            Enter a public Team ID. Andres will attach the numbers, uncertainty,
            and source freshness to every recommendation.
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
              maxLength={9}
              onChange={(event) => setTeamId(event.target.value)}
              placeholder="e.g. 123456"
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
          <p className="eyebrow">Decision</p>
          <h2>One move first</h2>
          <p>
            Bank, buy, sell, captain and bench calls ordered for deadline use.
          </p>
        </article>
        <article>
          <div className="briefing-icon">
            <Clock3 aria-hidden="true" size={21} />
          </div>
          <p className="eyebrow">Horizon</p>
          <h2>Six to eight weeks</h2>
          <p>
            A rolling path, plus a fixture and chip roadmap that can change.
          </p>
        </article>
        <article>
          <div className="briefing-icon">
            <ShieldCheck aria-hidden="true" size={21} />
          </div>
          <p className="eyebrow">Evidence</p>
          <h2>No invented certainty</h2>
          <p>
            Observed, inferred, experimental and unavailable are shown plainly.
          </p>
        </article>
      </section>
    </>
  );
}

function TeamAnalysisPage() {
  const { teamId } = useParams();

  if (!teamId) {
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
      <RouteHeading>Analysis for team {teamId}</RouteHeading>
      <div className="status-rule" role="status">
        <span className="status-pulse" />
        Connecting the rules, squad state and latest source snapshots.
      </div>
      <p className="analysis-note">
        Public team data reflects the last processed deadline. Before a plan is
        finalized, you will be able to correct current transfers, bank and chip
        state.
      </p>
      <Link className="text-command" to="/">
        Analyse another team
      </Link>
    </section>
  );
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

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <ApplicationFrame />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "team/:teamId", element: <TeamAnalysisPage /> },
      { path: "methodology", element: <MethodPage /> },
      { path: "calibration", element: <CalibrationPage /> },
    ],
  },
];
