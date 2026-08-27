import { Link } from "react-router-dom";

import { RouteHeading } from "../components/RouteHeading";
import validation from "../data/validation.json";
import { captureDay, integer } from "../format";
import { useDocumentTitle } from "../state/use-document-title";

const POSITIONS = ["GKP", "DEF", "MID", "FWD"] as const;

function positionWins(): [number, number] {
  let wins = 0;
  let cells = 0;
  for (const season of validation.seasons) {
    const model = season.methods.find((method) => method.label === "model");
    const baseline = season.methods.find(
      (method) => method.label === "recent_mean",
    );
    for (const position of POSITIONS) {
      const mine = model?.byPosition[position];
      const theirs = baseline?.byPosition[position];
      if (mine === null || mine === undefined) continue;
      if (theirs === null || theirs === undefined) continue;
      cells += 1;
      if (mine > theirs) wins += 1;
    }
  }
  return [wins, cells];
}

export default function ProofPage() {
  useDocumentTitle(
    "Proof",
    "Held-out results and known weaknesses behind FPL Andres.",
    { canonicalPath: "/proof" },
  );

  const observations = validation.seasons.reduce(
    (total, season) => total + season.rows,
    0,
  );
  const [wins, cells] = positionWins();
  const leagueWins = validation.seasons.reduce(
    (total, season) => total + season.league.policies.advised.wins,
    0,
  );
  const leaguesPlayed = validation.seasons.reduce(
    (total, season) => total + season.league.leaguesPlayed,
    0,
  );
  const freeGain = validation.seasons.reduce(
    (total, season) => total + season.replay.transferReturn.freeGain,
    0,
  );
  const template = validation.captainSignificance.find(
    (entry) => entry.label === "template",
  );

  return (
    <section className="text-page proof-page" aria-label="Proof">
      <p className="eyebrow">Measured record</p>
      <RouteHeading>Why trust this?</RouteHeading>
      <p className="lede">
        Because forecasts are frozen before matches and scored afterwards. These
        are the current results, including the weak part.
      </p>
      <p className="mono proof-run">
        Model {validation.modelVersion} · {integer.format(observations)}{" "}
        player-weeks · last run{" "}
        <time dateTime={validation.generatedAt}>
          {captureDay.format(new Date(validation.generatedAt))}
        </time>
      </p>

      <dl className="validation-claims proof-claims">
        <div>
          <dt>
            {wins}/{cells}
          </dt>
          <dd>Position-season ranking tests beat the last-five average.</dd>
        </div>
        <div>
          <dt>{template ? `+${template.improvement.toFixed(3)}` : "—"}</dt>
          <dd>
            Captain points per week from the one rule whose interval clears
            zero, over {integer.format(template?.weeks ?? 0)} paired weeks.
          </dd>
        </div>
        <div>
          <dt>
            {leagueWins}/{leaguesPlayed}
          </dt>
          <dd>Simulated mini-leagues won by the advised policy.</dd>
        </div>
        <div>
          <dt>+{freeGain.toFixed(0)}</dt>
          <dd>Points gained by free transfers across four season replays.</dd>
        </div>
      </dl>

      <section
        className="proof-weakness"
        aria-labelledby="proof-weakness-title"
      >
        <h2 id="proof-weakness-title">The weak part: gameweek one</h2>
        <p>
          Before current-season lineups exist, accuracy is worse and has fallen
          in the two latest holdouts. That is why new team sheets now update
          xStart instead of leaving the summer prior untouched.
        </p>
        <div className="fpl500-scroll">
          <table className="squad-table">
            <thead>
              <tr>
                <th scope="col">Season</th>
                <th scope="col">Players</th>
                <th scope="col">MAE</th>
                <th scope="col">Rank corr.</th>
              </tr>
            </thead>
            <tbody>
              {validation.seasons.map((season) => (
                <tr key={season.season}>
                  <th scope="row">{season.season}</th>
                  <td className="mono">{season.openingGameweek.scored}</td>
                  <td className="mono">
                    {season.openingGameweek.meanAbsoluteError.toFixed(3)}
                  </td>
                  <td className="mono">
                    {season.openingGameweek.spearman.toFixed(3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <nav className="proof-links" aria-label="Proof detail">
        <Link to="/calibration">Full calibration</Link>
        <Link to="/methodology">Method</Link>
        <Link to="/fpl500">FPL500</Link>
      </nav>
    </section>
  );
}
