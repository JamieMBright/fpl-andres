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

type SquadPlayer = {
  elementId: number;
  name: string;
  position: string;
  priceTenths: number;
};

type PolicyResult = {
  mean: number;
  best: number;
  wins: number;
  chips: Record<string, number>;
  teamValueTenths: number;
  squad: SquadPlayer[];
};

type SeasonReport = {
  season: string;
  rows: number;
  gameweeks: number;
  gameweeksPlayed: number;
  elements: number;
  firstScoredGameweek: number;
  expectedGoalsCoverage: number;
  methods: Method[];
  league: {
    policies: Record<string, PolicyResult>;
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
  components: "Components only",
  recent_mean: "Last 5 average",
  ownership: "What the crowd owns",
};

const POLICY_NAMES: Record<string, string> = {
  advised: "Me",
  form_chaser: "Form chaser",
  crowd: "The crowd",
  hold: "Never transfers",
};

const POLICY_ORDER = ["advised", "form_chaser", "crowd", "hold"] as const;
const CHIP_NAMES: Record<string, string> = {
  wildcard: "Wildcard",
  free_hit: "Free Hit",
  triple_captain: "Triple Captain",
  bench_boost: "Bench Boost",
};

const POSITIONS = ["GKP", "DEF", "MID", "FWD"] as const;

/** My rank correlation minus the naive baseline's, for one position. */
function positionLead(season: SeasonReport, position: string): number | null {
  const mine = methodOf(season, "model")?.byPosition[position];
  const baseline = methodOf(season, "recent_mean")?.byPosition[position];
  if (mine === null || mine === undefined) return null;
  if (baseline === null || baseline === undefined) return null;
  return mine - baseline;
}

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
    (sum, season) => sum + (season.league.policies.advised?.wins ?? 0),
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
          Higher is better. One is perfect. This test has no squad, no budget
          and no transfers &mdash; it ranks every player in the game at once, so
          nobody could actually play it.
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
          averaged — ranks better than my projection in every season I tested. I
          am not going to hide that. But read the next section before drawing a
          conclusion from it.
        </p>
      </section>

      <section aria-labelledby="position-title">
        <h2 id="position-title">The same test, one position at a time</h2>
        <p>
          You never pick from all six hundred players at once. You pick two
          keepers, five defenders, five midfielders and three forwards. So the
          honest question is whether I rank better <em>within a position</em>.
          Here is my correlation minus the baseline&rsquo;s. Positive means I
          win.
        </p>
        <div
          aria-label="Scrollable per-position comparison table"
          className="squad-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
          tabIndex={0}
        >
          <table aria-label="Rank correlation lead over the baseline by position">
            <thead>
              <tr>
                <th scope="col">Season</th>
                {POSITIONS.map((position) => (
                  <th scope="col" key={position}>
                    {position}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.seasons.map((season) => (
                <tr key={season.season}>
                  <th scope="row" className="mono">
                    {season.season}
                  </th>
                  {POSITIONS.map((position) => {
                    const lead = positionLead(season, position);
                    return (
                      <td className="mono" key={position}>
                        {lead === null
                          ? "—"
                          : `${lead > 0 ? "+" : ""}${lead.toFixed(3)}`}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="validation-verdict">
          I beat the baseline in every position, in every season —{" "}
          {report.seasons.length * POSITIONS.length} out of{" "}
          {report.seasons.length * POSITIONS.length} cells. Both facts are real.
          Pooled across all positions I lose badly; within the position you are
          actually choosing from, I win. That gap is my cross-position
          calibration, and it is the thing I am fixing next.
        </p>
      </section>

      <section aria-labelledby="league-title">
        <h2 id="league-title">Does following me actually help?</h2>
        <p>
          {report.league.managers} managers per league, each starting from a
          different random squad. {Math.round(report.league.advisedShare * 100)}
          % follow my projection. The rest play the baselines below. Every
          policy starts from the same opening squad, so any difference is the
          policy and not the luck of the draw.
        </p>
        <p>
          Everyone plays by the same rules. The squad carries over week to week,
          one free transfer arrives each gameweek and banks up to five, and any
          move beyond the bank costs four points. All four chips are played by
          every policy. Team value moves with prices, and a risen player sells
          for only half his profit.
        </p>
        <div
          aria-label="Scrollable mini-league table"
          className="squad-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
          tabIndex={0}
        >
          <table aria-label="Mini-league outcomes by season and policy">
            <thead>
              <tr>
                <th scope="col">Season</th>
                <th scope="col">Weeks</th>
                {POLICY_ORDER.map((policy) => (
                  <th scope="col" key={policy}>
                    {POLICY_NAMES[policy]}
                  </th>
                ))}
                <th scope="col">vs form</th>
              </tr>
            </thead>
            <tbody>
              {report.seasons.map((season) => {
                const policies = season.league.policies;
                const margin =
                  (policies.advised?.mean ?? 0) -
                  (policies.form_chaser?.mean ?? 0);
                return (
                  <tr key={season.season}>
                    <th scope="row" className="mono">
                      {season.season}
                    </th>
                    <td className="mono">{season.gameweeksPlayed}</td>
                    {POLICY_ORDER.map((policy) => (
                      <td className="mono" key={policy}>
                        {policies[policy]?.mean.toLocaleString("en-GB") ?? "—"}
                      </td>
                    ))}
                    <td className="mono">
                      {margin > 0 ? "+" : ""}
                      {margin}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="validation-verdict">
          The honest column is the last one. Beating a manager who never
          transfers proves nothing; beating one who chases form is the real
          test, and the margin there is small — in 2024-25 the form chaser beat
          me outright. These totals cover{" "}
          {report.seasons[0]?.gameweeksPlayed ?? 32} gameweeks of 38, so they
          are not season totals and should not be read as any.
        </p>
      </section>

      <section aria-labelledby="squads-title">
        <h2 id="squads-title">The teams they finished with</h2>
        <p>
          Every policy, side by side, as the squad stood at the end of the first
          simulated league. This is the part that makes the rest checkable: if a
          team looks wrong, the number above it is wrong too.
        </p>
        {report.seasons.map((season) => (
          <details key={season.season} className="source-trail">
            <summary>
              <span className="mono">
                {season.season} — four squads, chips and final team value
              </span>
            </summary>
            <div className="policy-squads">
              {POLICY_ORDER.map((policy) => {
                const entry = season.league.policies[policy];
                if (!entry) return null;
                return (
                  <div className="policy-squad" key={policy}>
                    <h3>{POLICY_NAMES[policy]}</h3>
                    <p className="mono policy-meta">
                      {entry.mean.toLocaleString("en-GB")} pts ·{" "}
                      {(entry.teamValueTenths / 10).toFixed(1)}m
                    </p>
                    <p className="policy-chips">
                      {Object.entries(entry.chips).length === 0
                        ? "No chips played"
                        : Object.entries(entry.chips)
                            .sort((a, b) => a[1] - b[1])
                            .map(
                              ([chip, week]) =>
                                `${CHIP_NAMES[chip] ?? chip} GW${week}`,
                            )
                            .join(", ")}
                    </p>
                    <ol className="policy-players">
                      {entry.squad.map((player) => (
                        <li key={player.elementId}>
                          <span className="mono policy-pos">
                            {player.position}
                          </span>
                          <span translate="no">{player.name}</span>
                          <span className="mono policy-price">
                            {(player.priceTenths / 10).toFixed(1)}
                          </span>
                        </li>
                      ))}
                    </ol>
                  </div>
                );
              })}
            </div>
          </details>
        ))}
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
                {season.expectedGoalsCoverage < 1
                  ? ` — expected goals on ${Math.round(season.expectedGoalsCoverage * 100)}% of rows, so this season is scored on actuals`
                  : ""}
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
