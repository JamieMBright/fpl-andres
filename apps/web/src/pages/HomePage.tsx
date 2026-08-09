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
            Your Team ID is all I need. Squad, captain, bank, transfers &mdash;
            read from the public record.{" "}
            <InfoMarker label="where the numbers come from">
              Every figure carries the FPL endpoint it was read from and the
              deadline it was recorded at. Changed something since? Tell me at
              step two. I never guess.
            </InfoMarker>
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
            In the URL of your FPL points page. No login needed.
          </p>
          {error ? (
            <p className="field-error" id="team-id-error" role="alert">
              {error}
            </p>
          ) : null}
        </form>

        <p className="entry-aside">
          No squad exists until the first deadline. Until then there is the
          market: <Link to="/players">every player in the 2026/27 game</Link>,
          priced at this season&rsquo;s money.{" "}
          <InfoMarker label="the pre-season market">
            FPL wipes every squad between seasons, so a Team ID can only say who
            you are. Each player is shown at this season&rsquo;s price against
            what he actually returned last season.
          </InfoMarker>
        </p>
      </section>

      <section className="method-strip" aria-label="How I work">
        <h2 className="method-strip-title">How I work</h2>
        <ol>
          <li>
            <span className="method-step" aria-hidden="true">
              01
            </span>
            <h3>Your team ID</h3>
            <p>I read what FPL made public. Nothing more.</p>
          </li>
          <li>
            <span className="method-step" aria-hidden="true">
              02
            </span>
            <h3>Your changes</h3>
            <p>
              Tell me what FPL can&rsquo;t see yet. It stays on your machine.
            </p>
          </li>
          <li>
            <span className="method-step" aria-hidden="true">
              03
            </span>
            <h3>I crunch</h3>
            <p>Ten seasons of it. Numbers, not opinions.</p>
          </li>
          <li className="method-pending">
            <span className="method-step" aria-hidden="true">
              04
            </span>
            <h3>The verdict</h3>
            <p>It arrives when the models have earned it.</p>
          </li>
        </ol>
      </section>
    </>
  );
}
