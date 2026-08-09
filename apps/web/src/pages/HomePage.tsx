import { ArrowRight, Clock3 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { InfoMarker } from "../components/InfoMarker";
import { RouteHeading } from "../components/RouteHeading";
import { MAX_PUBLIC_ID } from "../public-ids";
import { readLastTeam } from "../state/declared-squad";
import { useDocumentTitle } from "../state/use-document-title";

export default function HomePage() {
  const navigate = useNavigate();
  // Offered back rather than demanded again: a returning reader has already
  // told us who they are, and the number is a public id kept in this browser.
  const [teamId, setTeamId] = useState(
    () => readLastTeam(window.localStorage)?.toString() ?? "",
  );
  const [error, setError] = useState<string | null>(null);
  useDocumentTitle(
    "FPL Andres",
    "An evidence-first Fantasy Premier League assistant that shows its working and admits what it cannot know.",
  );

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
      <p className="eyebrow">
        <Clock3 aria-hidden="true" size={14} /> Reading the public record
      </p>
      <RouteHeading>Six pages. No opinions.</RouteHeading>

      <ul className="index-grid">
        <li className="index-cell is-plan">
          <h2>
            <span aria-hidden="true">01</span>
            <Link to="/plan">Plan</Link>
          </h2>
          <p>Your fifteen, solved to gameweek 38.</p>

          <form className="index-form" noValidate onSubmit={analyseTeam}>
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
              In the URL of your FPL points page. No login needed.
              <InfoMarker label="what I read">
                Squad, captain, bank and transfers, exactly as FPL last recorded
                them at a deadline. Nothing about your team is sent anywhere to
                build the plan.
              </InfoMarker>
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

        <li className="index-cell is-calibration">
          <h2>
            <span aria-hidden="true">05</span>
            <Link to="/calibration">Calibration</Link>
          </h2>
          <p>Where I win, where I lose. Scored four seasons back.</p>
        </li>

        <li className="index-cell is-faq">
          <h2>
            <span aria-hidden="true">06</span>
            <Link to="/faq">FAQ</Link>
          </h2>
          <p>Quick answers and the FPL lingo glossary.</p>
        </li>
      </ul>
    </section>
  );
}
