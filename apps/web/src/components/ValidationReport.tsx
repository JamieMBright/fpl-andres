import validation from "../data/validation.json";

type Method = {
  label: string;
  scored: number;
  meanAbsoluteError: number | null;
  rootMeanSquaredError: number | null;
  bias: number | null;
  spearman: number | null;
  topNHitRate: number | null;
  byPosition: Record<string, number | null>;
};

type SeasonReport = {
  season: string;
  rows: number;
  gameweeks: number;
  elements: number;
  firstScoredGameweek: number;
  methods: Method[];
  league: {
    advisedMean: number;
    zombieMean: number;
    advisedBest: number;
    zombieBest: number;
    advisedWins: number;
    leaguesPlayed: number;
  };
};

type Report = {
  generatedAt: string;
  seasons: SeasonReport[];
  league: { managers: number; advisedShare: number; seeds: number[] };
};

const report = validation as Report;

const METHOD_NAMES: Record<string, string> = {
  model: "My projection",
  recent_mean: "Last 5 average",
  ownership: "What the crowd owns",
};

function methodOf(season: SeasonReport, label: string): Method | undefined {
  return season.methods.find((method) => method.label === label);
}

function show(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

/** Bar scaled against the strongest correlation on the page. */
function Bar({ value, max }: { value: number | null; max: number }) {
  if (value === null) return <span className="mono">—</span>;
  const share = Math.max(0, Math.min(1, value / max));
  return (
    <span className="rho-bar">
      <span className="rho-bar-fill" style={{ width: `${share * 100}%` }} />
      <span className="rho-bar-value mono">{value.toFixed(3)}</span>
    </span>
  );
}

export function ValidationReport() {
  const totalRows = report.seasons.reduce(
    (sum, season) => sum + season.rows,
    0,
  );
  const leaguesPlayed = report.seasons.reduce(
    (sum, season) => sum + season.league.leaguesPlayed,
    0,
  );
  const advisedWins = report.seasons.reduce(
    (sum, season) => sum + season.league.advisedWins,
    0,
  );
  const maxRho = Math.max(
    ...report.seasons.flatMap((season) =>
      season.methods.map((method) => method.spearman ?? 0),
    ),
  );

  return (
    <>
      <section className="validation-summary" aria-label="What I tested">
        <dl>
          <div>
            <dt>Seasons</dt>
            <dd className="mono">{report.seasons.length}</dd>
          </div>
          <div>
            <dt>Observations</dt>
            <dd className="mono">{totalRows.toLocaleString("en-GB")}</dd>
          </div>
          <div>
            <dt>Leagues played</dt>
            <dd className="mono">{leaguesPlayed}</dd>
          </div>
          <div>
            <dt>Advised won</dt>
            <dd className="mono">
              {advisedWins}/{leaguesPlayed}
            </dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="ranking-title">
        <h2 id="ranking-title">Can I rank players?</h2>
        <p>
          Rank correlation against what actually happened, gameweek by gameweek.
          Higher is better. One is perfect.
        </p>
        <div
          aria-label="Scrollable rank correlation table"
          className="squad-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
          tabIndex={0}
        >
          <table aria-label="Rank correlation by season and method">
            <thead>
              <tr>
                <th scope="col">Season</th>
                <th scope="col">My projection</th>
                <th scope="col">Last 5 average</th>
                <th scope="col">Crowd ownership</th>
              </tr>
            </thead>
            <tbody>
              {report.seasons.map((season) => (
                <tr key={season.season}>
                  <th scope="row" className="mono">
                    {season.season}
                  </th>
                  <td>
                    <Bar
                      value={methodOf(season, "model")?.spearman ?? null}
                      max={maxRho}
                    />
                  </td>
                  <td>
                    <Bar
                      value={methodOf(season, "recent_mean")?.spearman ?? null}
                      max={maxRho}
                    />
                  </td>
                  <td>
                    <Bar
                      value={methodOf(season, "ownership")?.spearman ?? null}
                      max={maxRho}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="validation-verdict">
          The dumbest possible baseline — a player&rsquo;s last five scores,
          averaged — ranks better than my projection in every season I tested.
          That is why nothing here is promoted yet.
        </p>
      </section>

      <section aria-labelledby="league-title">
        <h2 id="league-title">Does following me actually help?</h2>
        <p>
          {report.league.managers} managers per league, each starting from a
          different random squad. {Math.round(report.league.advisedShare * 100)}
          % follow my projection. The rest are zombies: they leave the squad
          alone until someone stops playing, then take the best recent form.
          Five leagues per season.
        </p>
        <div
          aria-label="Scrollable mini-league table"
          className="squad-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
          tabIndex={0}
        >
          <table aria-label="Mini-league outcomes by season">
            <thead>
              <tr>
                <th scope="col">Season</th>
                <th scope="col">Advised</th>
                <th scope="col">Zombie</th>
                <th scope="col">Margin</th>
                <th scope="col">Leagues won</th>
              </tr>
            </thead>
            <tbody>
              {report.seasons.map((season) => {
                const margin =
                  season.league.advisedMean - season.league.zombieMean;
                return (
                  <tr key={season.season}>
                    <th scope="row" className="mono">
                      {season.season}
                    </th>
                    <td className="mono">{season.league.advisedMean}</td>
                    <td className="mono">{season.league.zombieMean}</td>
                    <td className="mono">
                      {margin > 0 ? "+" : ""}
                      {margin}
                    </td>
                    <td className="mono">
                      {season.league.advisedWins}/{season.league.leaguesPlayed}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="validation-verdict">
          Following the projection beat sitting still in all{" "}
          {report.seasons.length} seasons. Both things are true at once: my
          ranking is worse than the naive baseline, and acting on it still beat
          doing nothing. Ranking every player well and picking a squad well are
          not the same job.
        </p>
      </section>

      <section aria-labelledby="detail-title">
        <h2 id="detail-title">Check my working</h2>
        <p>
          Every number above, per season. Error is in points per player per
          gameweek. Bias is my average error — negative means I under-predict.
        </p>
        {report.seasons.map((season) => (
          <details key={season.season} className="source-trail">
            <summary>
              <span className="mono">
                {season.season} — {season.rows.toLocaleString("en-GB")}{" "}
                observations, scored from GW{season.firstScoredGameweek}
              </span>
            </summary>
            <div className="source-trail-body">
              <div
                aria-label={`Scrollable ${season.season} metrics`}
                className="squad-table-wrap"
                role="region"
                // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
                tabIndex={0}
              >
                <table aria-label={`Detailed metrics for ${season.season}`}>
                  <thead>
                    <tr>
                      <th scope="col">Method</th>
                      <th scope="col">Scored</th>
                      <th scope="col">Error</th>
                      <th scope="col">Bias</th>
                      <th scope="col">Rank corr.</th>
                      <th scope="col">Top 20</th>
                    </tr>
                  </thead>
                  <tbody>
                    {season.methods.map((method) => (
                      <tr key={method.label}>
                        <th scope="row">
                          {METHOD_NAMES[method.label] ?? method.label}
                        </th>
                        <td className="mono">
                          {method.scored
                            ? method.scored.toLocaleString("en-GB")
                            : "—"}
                        </td>
                        <td className="mono">
                          {show(method.meanAbsoluteError)}
                        </td>
                        <td className="mono">{show(method.bias)}</td>
                        <td className="mono">{show(method.spearman)}</td>
                        <td className="mono">{show(method.topNHitRate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mono validation-positions">
                My rank correlation by position:{" "}
                {Object.entries(methodOf(season, "model")?.byPosition ?? {})
                  .map(([position, value]) => `${position} ${show(value)}`)
                  .join("  ")}
              </p>
            </div>
          </details>
        ))}
        <p className="mono validation-generated">
          Generated {report.generatedAt.slice(0, 10)} from the corpus. Rerun
          with <code translate="no">python -m fpl_andres.cli.validate</code>.
        </p>
      </section>
    </>
  );
}
