import { Link } from "react-router-dom";

import fpl500 from "../data/fpl500.json";
import validation from "../data/validation.json";
import { RouteHeading } from "../components/RouteHeading";
import { captureDay, integer } from "../format";
import { useDocumentTitle } from "../state/use-document-title";

export default function ResultsPage() {
  useDocumentTitle(
    "Measured results",
    "Three measured views of FPL Andres: player ranking, season simulation, and the experienced-manager cohort.",
    { canonicalPath: "/results" },
  );

  const observations = validation.seasons.reduce(
    (total, season) => total + season.rows,
    0,
  );
  const leaguesPlayed = validation.seasons.reduce(
    (total, season) => total + season.league.leaguesPlayed,
    0,
  );
  const advisedWins = validation.seasons.reduce(
    (total, season) => total + (season.league.policies.advised?.wins ?? 0),
    0,
  );

  return (
    <section className="text-page results-page">
      <p className="eyebrow">Evidence, not endorsements</p>
      <RouteHeading>Measured Results</RouteHeading>
      <p className="faq-lede">
        Three questions, tested against completed seasons and public records.
        Open the source view whenever the short answer matters.
      </p>

      <div className="about-ledger">
        <section aria-labelledby="result-ranking">
          <p className="about-ledger-number" aria-hidden="true">
            01
          </p>
          <div>
            <h2 id="result-ranking">Player ranking</h2>
            <dl className="dossier-metrics">
              <div>
                <dt>Seasons</dt>
                <dd>{validation.seasons.length}</dd>
              </div>
              <div>
                <dt>Observations</dt>
                <dd>{integer.format(observations)}</dd>
              </div>
            </dl>
            <p>
              Every player is ranked week by week against what happened, then
              compared with a last-five-gameweek average inside each position.
            </p>
            <p>
              <Link to="/calibration">Open full calibration</Link>
            </p>
            <p className="mono">
              Source run{" "}
              <time dateTime={validation.generatedAt}>
                {captureDay.format(new Date(validation.generatedAt))}
              </time>
            </p>
          </div>
        </section>

        <section aria-labelledby="result-season">
          <p className="about-ledger-number" aria-hidden="true">
            02
          </p>
          <div>
            <h2 id="result-season">Season simulation</h2>
            <dl className="dossier-metrics">
              <div>
                <dt>Leagues played</dt>
                <dd>{integer.format(leaguesPlayed)}</dd>
              </div>
              <div>
                <dt>Advised wins</dt>
                <dd>
                  {integer.format(advisedWins)}/{integer.format(leaguesPlayed)}
                </dd>
              </div>
            </dl>
            <p>
              Each policy starts from the same squad. The simulation measures
              transfer decisions rather than rewarding a kinder initial draw.
            </p>
            <p>
              <Link to="/methodology">Read the method</Link>
            </p>
            <p className="mono">
              Source run{" "}
              <time dateTime={validation.generatedAt}>
                {captureDay.format(new Date(validation.generatedAt))}
              </time>
            </p>
          </div>
        </section>

        <section aria-labelledby="result-managers">
          <p className="about-ledger-number" aria-hidden="true">
            03
          </p>
          <div>
            <h2 id="result-managers">Experienced managers</h2>
            <dl className="dossier-metrics">
              <div>
                <dt>Qualified records</dt>
                <dd>{integer.format(fpl500.catalogueSize)}</dd>
              </div>
              <div>
                <dt>Ranked cohort</dt>
                <dd>{integer.format(fpl500.size)}</dd>
              </div>
            </dl>
            <p>
              Public finishing records identify repeat top-ten-thousand
              managers. Percentiles and recency keep different eras comparable.
            </p>
            <p>
              <Link to="/fpl500">Inspect FPL500</Link>
            </p>
            <p className="mono">
              Source run{" "}
              <time dateTime={fpl500.generatedAt}>
                {captureDay.format(new Date(fpl500.generatedAt))}
              </time>
            </p>
          </div>
        </section>
      </div>
    </section>
  );
}
