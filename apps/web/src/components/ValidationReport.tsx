import validation from "../data/validation.json";
import { CaptainGrid, type SeasonPicks } from "./CaptainGrid";
import {
  BarChart,
  IntervalChart,
  SeasonLines,
  type BarDatum,
  type IntervalDatum,
} from "./CalibrationCharts";
import {
  pooledVerdict,
  positionVerdict,
  separableVerdict,
  type VerdictSeason,
} from "../state/validation-verdict";

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
  /** Absent from artifacts generated before captaincy was scored. */
  captaincy?: CaptaincyScore[];
  /** Absent from artifacts generated before the theses were scored. */
  captainPolicies?: CaptaincyScore[];
  /** Absent from artifacts generated before the picks were retained. */
  captainPicks?: Omit<SeasonPicks, "season">;
  league: {
    policies: Record<string, PolicyResult>;
    leaguesPlayed: number;
  };
};

type CaptaincyScore = {
  label: string;
  gameweeks: number;
  meanPoints: number | null;
  meanBestPoints: number | null;
  regret: number | null;
  shareOfCeiling: number | null;
  perfectWeeks: number;
  blankRate: number | null;
};

/** One thesis measured against the incumbent projection, week for week. */
type Significance = {
  label: string;
  weeks: number;
  meanPoints: number | null;
  baselineMeanPoints: number | null;
  improvement: number | null;
  lower: number | null;
  upper: number | null;
  better: boolean;
  reasonCodes: string[];
  /** How many theses were tested at once. Absent on older artifacts. */
  familySize?: number;
};

type Report = {
  generatedAt: string;
  seasons: SeasonReport[];
  league: { managers: number; advisedShare: number; seeds: number[] };
  /** Absent from artifacts generated before the theses were tested. */
  captainSignificance?: Significance[];
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

/** Matches `SHORTLIST_SIZE` in `backtesting/captaincy.py`. */
const CAPTAIN_SHORTLIST = 25;

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

/** Averaged across seasons, because one season of 32 weeks decides nothing. */
function averaged(
  seasons: readonly SeasonReport[],
  pick: (season: SeasonReport) => readonly CaptaincyScore[] | undefined,
  names: Record<string, string> = {},
): BarDatum[] {
  const totals = new Map<string, number[]>();
  const ceilings = new Map<string, number[]>();
  for (const season of seasons) {
    for (const entry of pick(season) ?? []) {
      if (entry.meanPoints === null) continue;
      totals.set(entry.label, [
        ...(totals.get(entry.label) ?? []),
        entry.meanPoints,
      ]);
      if (entry.meanBestPoints !== null) {
        ceilings.set(entry.label, [
          ...(ceilings.get(entry.label) ?? []),
          entry.meanBestPoints,
        ]);
      }
    }
  }
  const mean = (values: number[]) =>
    values.reduce((sum, value) => sum + value, 0) / values.length;
  return [...totals].map(([label, values]) => {
    const ceiling = ceilings.get(label);
    return {
      label: names[label] ?? label,
      value: mean(values),
      mine: label === "model" || label === "expected_points",
      ...(ceiling && ceiling.length > 0 ? { reference: mean(ceiling) } : {}),
    };
  });
}

function captaincyAverages(seasons: readonly SeasonReport[]): BarDatum[] {
  return averaged(seasons, (season) => season.captaincy, METHOD_NAMES);
}

function policyAverages(seasons: readonly SeasonReport[]): BarDatum[] {
  return averaged(seasons, (season) => season.captainPolicies);
}

/** Drops any verdict the bootstrap could not resolve into a real interval. */
function intervals(entries: readonly Significance[]): IntervalDatum[] {
  return entries.flatMap((entry) =>
    entry.improvement === null || entry.lower === null || entry.upper === null
      ? []
      : [
          {
            label: entry.label,
            improvement: entry.improvement,
            lower: entry.lower,
            upper: entry.upper,
            better: entry.better,
          },
        ],
  );
}

function show(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
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
  const captaincySeasons = report.seasons.filter(
    (season) => (season.captaincy ?? []).length > 0,
  );
  const significance = report.captainSignificance ?? [];
  const verdicts = intervals(significance);
  const pooledWeeks = significance[0]?.weeks ?? 0;
  const family = significance[0]?.familySize ?? significance.length;
  const pickSeasons = report.seasons.flatMap((season) =>
    season.captainPicks === undefined
      ? []
      : [{ season: season.season, ...season.captainPicks }],
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
        <SeasonLines
          title="Rank correlation, season by season"
          caption="Each line is one method. What matters is whether the gap holds, not the level in any single season."
          seasons={report.seasons.map((season) => season.season)}
          series={["model", "components", "recent_mean", "ownership"].map(
            (label) => ({
              label: METHOD_NAMES[label] ?? label,
              mine: label === "model",
              points: report.seasons.map(
                (season) => methodOf(season, label)?.spearman ?? null,
              ),
            }),
          )}
        />
        <p className="validation-verdict">
          {pooledVerdict(report.seasons as VerdictSeason[]).sentence}
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
          {
            positionVerdict(report.seasons as VerdictSeason[], POSITIONS)
              .sentence
          }
        </p>
      </section>

      <section aria-labelledby="captaincy-title">
        <h2 id="captaincy-title">Who would I have captained?</h2>
        <p>
          The captain doubles, so this one call swings two to three times what a
          routine transfer does. Every method picks from the same shortlist
          &mdash; the {CAPTAIN_SHORTLIST} most-owned players going into that
          gameweek, which is roughly the pool a real squad draws from. Picking
          from the whole league would be grading hindsight. The ceiling is the
          best captain <em>in that shortlist</em>, so the regret is a call
          somebody could have made.
        </p>
        {captaincySeasons.length === 0 ? (
          <p className="validation-verdict">
            This artifact predates the captaincy score, so there is nothing
            measured to show. It appears the next time{" "}
            <span className="mono">fpl_andres.cli.validate</span> runs.
          </p>
        ) : (
          <>
            <BarChart
              title="Captain points per gameweek, averaged across every season"
              caption="Bars are the captain's own score, not the doubled one. The tick is the best captain available on the same shortlist — the gap to it is what every method leaves behind."
              referenceLabel="Nobody gets close to it."
              data={captaincyAverages(captaincySeasons)}
            />
            <BarChart
              title="Competing captaincy theses"
              caption="Nine rules from the practitioner literature, each maximising something different, all picking from the same shortlist in the same weeks."
              data={policyAverages(report.seasons)}
            />
            <IntervalChart
              title="Which of those leads are real?"
              caption={`Each rule against my projection, paired week by week across all ${String(pooledWeeks)} scored gameweeks, then resampled 2,000 times. The dot is the mean gap; the whisker is the 95% interval, widened for the ${String(family)} rules tested at once \u2014 ${String(family)} chances at a 95% bar would otherwise fail about ${String(Math.round((1 - 0.95 ** family) * 100))}% of the time. A whisker touching the rule means the ranking above cannot tell those two apart, so the order it happened to land in is noise. A whisker clear of it on either side is a finding. ${separableVerdict(verdicts)}`}
              data={verdicts}
            />
          </>
        )}
        <p className="validation-verdict">
          Figures are the player&rsquo;s own score, not the doubled one. The
          doubling is a constant on every row, so it changes no ordering &mdash;
          but over a season a gap here is worth twice what it reads.
        </p>
      </section>

      <section aria-labelledby="picks-title">
        <h2 id="picks-title">Every armband, week by week</h2>
        <p>
          The charts above settle whether one rule beats another by a tenth of a
          point. They cannot show what the disagreement was about. Two rules
          separated by 0.15 still differ on which player, in which week &mdash;
          and that is the part you can check against a scoresheet.
        </p>
        <p>
          Rows are the fourteen methods, columns every scored gameweek. Each
          cell is the shirt, the player, who he faced and what he returned.
          Opponents carry the venue in their casing:{" "}
          <span className="mono">ARS</span> at home,{" "}
          <span className="mono">ars</span> away, both listed in a double. The
          number under each gameweek is the best return available on that
          week&rsquo;s shortlist, so a haul can be read against what was on
          offer. Scroll sideways; the method names stay put.
        </p>
        <p>
          <strong>Point at any pick to see why it was made.</strong> The panel
          underneath shows the arithmetic every rule read that week &mdash; the
          projection, the components under it, recent scoring, the chance he
          started, ownership, his ceiling and how kind the fixture was &mdash;
          for the player chosen and for the ones he was chosen over, ranked by
          projection. Tabbing to a cell does the same thing, so the reasoning is
          not reserved for people using a mouse.
        </p>
        <CaptainGrid
          mine={["model", "expected_points"]}
          names={METHOD_NAMES}
          seasons={pickSeasons}
        />
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
