import { ArrowRight } from "lucide-react";
import { Suspense, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ErrorBoundary } from "../components/ErrorBoundary";
import { InfoMarker } from "../components/InfoMarker";
import { RouteHeading } from "../components/RouteHeading";
import { MAX_PUBLIC_ID } from "../public-ids";
import { readLastTeam } from "../state/declared-squad";
import { lazyRoute } from "../state/lazy-route";
import { useDocumentTitle } from "../state/use-document-title";

// The picks need the whole season solver, and the landing page is the one
// chunk every visitor pays for. Its wrapper stays above the wayfinding grid
// even while the chunk loads, so the main rankings never jump below the menu.
const TopPicks = lazyRoute(() =>
  import("../components/TopPicks").then((module) => ({
    default: module.TopPicks,
  })),
);

export default function HomePage() {
  const navigate = useNavigate();
  const { hash } = useLocation();
  const teamIdInput = useRef<HTMLInputElement>(null);
  // Offered back rather than demanded again: a returning reader has already
  // told us who they are, and the number is a public id kept in this browser.
  const [teamId, setTeamId] = useState(
    () => readLastTeam(window.localStorage)?.toString() ?? "",
  );
  const [error, setError] = useState<string | null>(null);
  useDocumentTitle(
    "FPL Andres",
    "An evidence-first Fantasy Premier League assistant that shows its working and admits what it cannot know.",
    { canonicalPath: "/" },
  );

  useEffect(() => {
    if (hash !== "#team-id") return;
    requestAnimationFrame(() => {
      teamIdInput.current?.focus();
      teamIdInput.current?.scrollIntoView({ block: "center" });
    });
  }, [hash]);

  function analyseTeam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = teamId.trim();

    const parsedTeamId = Number(normalized);
    if (!/^[1-9]\d{0,9}$/.test(normalized) || parsedTeamId > MAX_PUBLIC_ID) {
      setError("Enter a numeric FPL team ID.");
      return;
    }

    setError(null);
    void navigate(`/plan?team=${normalized}`);
  }

  return (
    <section className="index-page" aria-label="Index">
      <RouteHeading>Top Picks</RouteHeading>

      <div className="index-rankings">
        <ErrorBoundary>
          <Suspense fallback={null}>
            <TopPicks />
          </Suspense>
        </ErrorBoundary>
      </div>

      <ul className="index-grid">
        <li className="index-cell is-plan">
          <h2>
            <span aria-hidden="true">01</span>
            <Link to="/plan">Plan</Link>
          </h2>
          <p>Your fifteen, solved to gameweek 38.</p>
        </li>

        <li className="index-cell is-entry">
          <form className="index-form" noValidate onSubmit={analyseTeam}>
            <div className="index-form-label">
              <label htmlFor="team-id">Your FPL team ID</label>
              <InfoMarker label="finding your team ID">
                Open the Fantasy Premier League site and go to Points. The
                number in the address bar, after /entry/, is your Team ID.
              </InfoMarker>
            </div>
            <div className="input-command">
              <input
                ref={teamIdInput}
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
              No login needed.
            </p>
            {error ? (
              <p className="field-error" id="team-id-error" role="alert">
                {error}
              </p>
            ) : null}
          </form>
        </li>

        <li className="index-cell is-players">
          <h2>
            <span aria-hidden="true">02</span>
            <Link to="/players">Players</Link>
          </h2>
          <p>Every player in the game, and what they cost.</p>
        </li>

        <li className="index-cell is-analysis">
          <h2>
            <span aria-hidden="true">03</span>
            <Link to="/analysis">Analysis</Link>
          </h2>
          <p>Any two stats, plotted. Find who the market missed.</p>
        </li>

        <li className="index-cell is-method">
          <h2>
            <span aria-hidden="true">04</span>
            <Link to="/methodology">Method</Link>
          </h2>
          <p>Fourteen scoring routes, priced. Every step auditable.</p>
        </li>

        <li className="index-cell is-results">
          <h2>
            <span aria-hidden="true">05</span>
            <Link to="/results">Results</Link>
          </h2>
          <p>Three measured questions, with every source still attached.</p>
        </li>
      </ul>
    </section>
  );
}
