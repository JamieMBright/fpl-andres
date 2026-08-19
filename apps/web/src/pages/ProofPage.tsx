import { Link } from "react-router-dom";

import { MethodFlow } from "../components/MethodFlow";
import { Methodology } from "../components/Methodology";
import { RouteHeading } from "../components/RouteHeading";
import fpl500 from "../data/fpl500.json";
import validation from "../data/validation.json";
import { captureDay, integer } from "../format";
import { useDocumentTitle } from "../state/use-document-title";

export default function ProofPage() {
  useDocumentTitle(
    "Proof",
    "Measured results, model method and source limits behind FPL Andres.",
    { canonicalPath: "/proof" },
  );

  const observations = validation.seasons.reduce(
    (total, season) => total + season.rows,
    0,
  );
  const leaguesPlayed = validation.seasons.reduce(
    (total, season) => total + season.league.leaguesPlayed,
    0,
  );

  return (
    <section className="text-page proof-page" aria-label="Proof">
      <p className="eyebrow">Did it work?</p>
      <RouteHeading>Proof</RouteHeading>
      <p className="lede">
        The measured record and the method sit together here: what worked, what
        lost, and what the model refuses to invent.
      </p>

      <section className="proof-results" aria-labelledby="proof-results">
        <h2 id="proof-results">Measured results</h2>
        <dl className="market-scoreboard proof-scoreboard">
          <div>
            <dt>Seasons</dt>
            <dd className="mono">{validation.seasons.length}</dd>
          </div>
          <div>
            <dt>Observations</dt>
            <dd className="mono">{integer.format(observations)}</dd>
          </div>
          <div>
            <dt>Leagues played</dt>
            <dd className="mono">{integer.format(leaguesPlayed)}</dd>
          </div>
          <div>
            <dt>FPL500</dt>
            <dd className="mono">{integer.format(fpl500.size)}</dd>
          </div>
        </dl>
        <p className="mono">
          Validation run{" "}
          <time dateTime={validation.generatedAt}>
            {captureDay.format(new Date(validation.generatedAt))}
          </time>
        </p>
        <p>
          <Link to="/calibration">Open full calibration</Link> ·{" "}
          <Link to="/results">Open the old results view</Link>
        </p>
      </section>

      <section className="proof-method" aria-labelledby="proof-method">
        <h2 id="proof-method">How it works</h2>
        <MethodFlow />
        <Methodology />
      </section>
    </section>
  );
}
