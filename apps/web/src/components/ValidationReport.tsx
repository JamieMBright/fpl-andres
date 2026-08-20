import { Link } from "react-router-dom";

import validation from "../data/validation.json";
import { timestamp } from "../format";
import {
  captainEvidence,
  type OwnedCaptainPolicy,
  type OwnedCaptainSeason,
} from "../state/captain-evidence";
import { InfoMarker } from "./InfoMarker";
import {
  BarChart,
  IntervalChart,
  SeasonLines,
  type BarDatum,
  type IntervalDatum,
} from "./CalibrationCharts";
import {
  leagueVerdict,
  pooledVerdict,
  positionVerdict,
  rankBandClass,
  rankBandLabel,
  rankPerformanceLabel,
  separableVerdict,
  type RankBandResult,
  type RankBinResult,
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
  prorated38Gameweeks?: number;
  overallRankBand?: RankBandResult | null;
  overallRankBin?: RankBinResult | null;
  rankReason?: string | null;
  best: number;
  wins: number;
  chips: Record<string, number>;
  teamValueTenths: number;
  squad: SquadPlayer[];
};

/** What the squad the method owned could actually get at. */
type Reach = {
  giant: {
    gameweeks: number;
    owned: number;
    started: number;
    captained: number;
    ownedShare: number | null;
    startedShare: number | null;
    captainedShare: number | null;
    leaders: { elementId: number; name: string; gameweeks: number }[];
  };
  captaincy: {
    gameweeks: number;
    meanChosen: number | null;
    meanOwnedCeiling: number | null;
    meanGameCeiling: number | null;
    ownedRegret: number | null;
    reachGap: number | null;
  };
};

/** Opening with the best player in the game, against buying him later. */
type GiantFirst = {
  elementId: number;
  name: string;
  startGameweek: number;
  seasons: number;
  meanWithout: number;
  meanOpeningWithHim: number;
  gain: number;
  meanGameweeksBeforeOwned: number | null;
  neverOwned: number;
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
  /**
   * The opening gameweek scored on its own, off the previous season only.
   * Absent from artifacts generated before the opening was measured.
   */
  openingGameweek?: {
    previousSeason: string;
    event: number;
    scored: number;
    meanAbsoluteError: number;
    rootMeanSquaredError: number;
    bias: number;
    spearman: number | null;
  };
  /** Absent until captain rules were replayed on model-owned legal XIs. */
  ownedCaptainPolicies?: OwnedCaptainPolicy[];
  /** Absent from artifacts generated before reach was measured. */
  reach?: Reach;
  /** Absent from artifacts generated before the opening was compared. */
  giantFirst?: GiantFirst;
  league: {
    policies: Record<string, PolicyResult>;
    leaguesPlayed: number;
  };
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
  /** Absent from artifacts published before the model was versioned. */
  modelVersion?: string;
  captainEvidenceScope?: string;
  seasons: SeasonReport[];
  league: { managers: number; advisedShare: number; seeds: number[] };
  /** Absent from artifacts generated before the theses were tested. */
  captainSignificance?: Significance[];
};

const report = validation as Report;

/** How old the published run is, said plainly rather than as a bare date. */
function freshnessOf(generatedAt: string): {
  when: string;
  age: string | null;
} {
  const run = new Date(generatedAt);
  if (Number.isNaN(run.getTime()))
    return { when: "at an unknown time", age: null };
  const days = Math.floor((Date.now() - run.getTime()) / 86_400_000);
  const when = timestamp.format(run);
  if (days <= 0) return { when, age: "today" };
  if (days === 1) return { when, age: "yesterday" };
  return { when, age: `${String(days)} days ago` };
}

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

/** Averaged across seasons, because one season of manager-XIs decides nothing. */
function policyAverages(seasons: readonly OwnedCaptainSeason[]): BarDatum[] {
  const totals = new Map<string, number[]>();
  const ceilings = new Map<string, number[]>();
  for (const season of seasons) {
    for (const entry of season.ownedCaptainPolicies ?? []) {
      if (entry.meanChosenPoints === null) continue;
      totals.set(entry.label, [
        ...(totals.get(entry.label) ?? []),
        entry.meanChosenPoints,
      ]);
      if (entry.meanReachableCeiling !== null) {
        ceilings.set(entry.label, [
          ...(ceilings.get(entry.label) ?? []),
          entry.meanReachableCeiling,
        ]);
      }
    }
  }
  const mean = (values: number[]) =>
    values.reduce((sum, value) => sum + value, 0) / values.length;
  return [...totals].map(([label, values]) => {
    const ceiling = ceilings.get(label);
    return {
      label,
      value: mean(values),
      mine: label === "expected_points",
      ...(ceiling && ceiling.length > 0 ? { reference: mean(ceiling) } : {}),
    };
  });
}

/** Drops any verdict the bootstrap could not resolve into a real interval. */
function intervals(
  entries: readonly {
    label: string;
    improvement: number;
    lower: number;
    upper: number;
    better: boolean;
  }[],
): IntervalDatum[] {
  return entries.flatMap((entry) => [
    {
      label: entry.label,
      improvement: entry.improvement,
      lower: entry.lower,
      upper: entry.upper,
      better: entry.better,
    },
  ]);
}

function show(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

/** A share printed as a percentage, because "84%" is read and "0.844" is parsed. */
function percent(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "—"
    : `${String(Math.round(value * 100))}%`;
}

/**
 * The opening gameweek, scored on its own.
 *
 * Every other number on this page pools the whole season, by which point the
 * model has watched players in the current campaign. GW1 has none of that: it
 * runs off last season and the summer market alone. Someone locking a squad
 * before a ball is kicked is buying the worse of the two numbers, so it is
 * printed rather than averaged away.
 */
function OpeningGameweekAccuracy({
  seasons,
}: {
  seasons: readonly SeasonReport[];
}) {
  const rows = seasons
    .map((season) => ({
      season: season.season,
      opening: season.openingGameweek,
      inSeason: methodOf(season, "model")?.spearman ?? null,
    }))
    .filter(
      (
        row,
      ): row is {
        season: string;
        opening: NonNullable<SeasonReport["openingGameweek"]>;
        inSeason: number | null;
      } => row.opening !== undefined,
    );
  if (rows.length === 0) {
    // Older artifact: say nothing rather than imply the opening was tested.
    return null;
  }
  return (
    <div className="validation-opening">
      <h3>How much of that survives gameweek one?</h3>
      <p>
        Less of it, most years. Replaying each season&rsquo;s opening gameweek
        with nothing but the previous season and the summer market, ranking came
        out worse in three of the four seasons I have &mdash; there is no
        current-season form to lean on yet. {rows[0]?.season} is the exception,
        and with four seasons that is far too few to call the size of the gap.
      </p>
      <table>
        <caption className="visually-hidden">
          Opening-gameweek rank correlation against the same season pooled
        </caption>
        <thead>
          <tr>
            <th scope="col">Season</th>
            <th scope="col">Priced off</th>
            <th scope="col">Players scored</th>
            <th scope="col">GW1 rank correlation</th>
            <th scope="col">Whole season</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.season}>
              <td>{row.season}</td>
              <td>{row.opening.previousSeason}</td>
              <td className="mono">{row.opening.scored}</td>
              <td className="mono">{show(row.opening.spearman)}</td>
              <td className="mono">{show(row.inSeason)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="validation-verdict">
        Treat an opening-gameweek ranking as the least tested number I publish.
        It is scored on about half the player list, on one week per season, so
        it is thinner evidence than everything above it. That is why an opening
        squad comes with the evidence behind each pick rather than only a total.
      </p>
    </div>
  );
}

export function ValidationReport() {
  const freshness = freshnessOf(report.generatedAt);
  const captain = captainEvidence(report);
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
  const captaincySeasons = captain.seasons;
  const significance = captain.significance;
  const verdicts = intervals(significance);
  const pooledWeeks = significance[0]?.weeks ?? 0;
  const family = significance[0]?.familySize ?? significance.length;
  const reachSeasons = report.seasons.flatMap((season) =>
    season.reach === undefined
      ? []
      : [{ season: season.season, reach: season.reach }],
  );
  const openingSeasons = report.seasons.flatMap((season) =>
    season.giantFirst === undefined
      ? []
      : [{ season: season.season, opening: season.giantFirst }],
  );

  // The whole page in five lines, derived. Anybody who reads nothing else
  // should still leave knowing what was measured and what it came to.
  const headlines: { figure: string; heading: string; detail: string }[] = [];
  const pooled = pooledVerdict(report.seasons as VerdictSeason[]);
  const positions = positionVerdict(
    report.seasons as VerdictSeason[],
    POSITIONS,
  );
  headlines.push({
    figure: `${String(positions.modelWins)}/${String(positions.cells)}`,
    heading: "season-and-position cells my ranking wins",
    detail:
      "Against a last-five-gameweek average, within a position, which is the " +
      "only comparison a transfer ever faces.",
  });
  headlines.push({
    figure: `${String(pooled.modelWins)}/${String(pooled.seasons)}`,
    heading: "seasons my ranking wins with every player pooled",
    detail:
      "The harder framing, and the one dominated by telling positions apart " +
      "rather than telling players apart.",
  });
  if (leaguesPlayed > 0) {
    headlines.push({
      figure: `${String(advisedWins)}/${String(leaguesPlayed)}`,
      heading: "simulated leagues the advised policy won",
      detail:
        "Twenty managers a league, every policy starting from the same squad, " +
        "so a win is the policy and not the draw.",
    });
  }
  if (verdicts.length > 0) {
    const separable = verdicts.filter(
      (entry) => entry.lower > 0 || entry.upper < 0,
    ).length;
    headlines.push({
      figure: `${String(separable)}/${String(verdicts.length)}`,
      heading: "captaincy rules the data can separate from mine",
      detail:
        "Every published strategy, paired against my projection week for week " +
        "and resampled. Most of the table is inside its own noise.",
    });
  }
  const worstReach = reachSeasons
    .map(({ reach }) => reach.captaincy.reachGap ?? 0)
    .sort((left, right) => right - left)[0];
  if (worstReach !== undefined) {
    headlines.push({
      figure: `${show(worstReach, 1)}`,
      heading: "points a week no captaincy rule can reach",
      detail:
        "The distance from the best captain in the squad you own to the best " +
        "in the game. It dwarfs the argument between the rules.",
    });
  }

  return (
    <>
      <p className="validation-freshness">
        <strong>Last run {freshness.when}</strong>
        {freshness.age === null ? null : <> · {freshness.age}</>}
        {report.modelVersion === undefined ? null : (
          <> · model {report.modelVersion}</>
        )}
        . Every figure below comes from that run and nothing on this page is
        typed by hand.
      </p>

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

      <section aria-labelledby="scoreboard-title" className="validation-board">
        <h2 id="scoreboard-title">The short version</h2>
        <ol className="validation-claims">
          {headlines.map((claim) => (
            <li key={claim.heading}>
              <p className="validation-claim-figure mono">{claim.figure}</p>
              <p className="validation-claim-heading">{claim.heading}</p>
              <p className="validation-claim-detail">{claim.detail}</p>
            </li>
          ))}
        </ol>
        <p className="validation-note">
          Each of those is a section below, with the table it came from.
        </p>
      </section>

      <section aria-labelledby="ranking-title">
        <h2 id="ranking-title">Can I rank players?</h2>
        <p>
          Rank correlation against what actually happened, week by week. Higher
          is better, one is perfect.
          <InfoMarker label="this ranking test">
            No squad, no budget and no transfers &mdash; it ranks every player
            in the game at once, so nobody could actually play it. It is the
            cleanest measure of ordering, not of a season.
          </InfoMarker>
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
        <OpeningGameweekAccuracy seasons={report.seasons} />
      </section>

      <section aria-labelledby="position-title">
        <h2 id="position-title">The same test, one position at a time</h2>
        <p>
          My correlation minus the baseline&rsquo;s, within each position.
          Positive means I win.
          <InfoMarker label="why position by position">
            You never pick from all six hundred players at once. You pick two
            keepers, five defenders, five midfielders and three forwards, so the
            honest question is whether the ranking holds inside a position.
          </InfoMarker>
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
          routine transfer does.
          <InfoMarker label="how captaincy is scored">
            Every rule picks only from the eleven fielded by a legal simulated
            squad following the model. The ceiling is the best return inside
            that same eleven, so the regret is a call that manager could really
            have made. Historical real-manager squads are not recoverable from
            FPL and are not approximated here as fact.
          </InfoMarker>
        </p>
        {captaincySeasons.length === 0 ? (
          <p className="validation-note">
            This artifact predates the owned-squad captain score. The old
            crowd-shortlist result is deliberately not shown as a substitute.
            This appears the next time{" "}
            <span className="mono">fpl_andres.cli.validate</span> runs.
          </p>
        ) : (
          <>
            <BarChart
              title="Captain rules on model-owned elevens"
              caption="Bars are each chosen captain's own score. The tick is the best return reachable inside the same fielded eleven; the gap is owned-squad regret."
              referenceLabel="Reachable XI ceiling"
              data={policyAverages(captaincySeasons)}
            />
            <IntervalChart
              title="Which of those leads are real?"
              caption={`Each rule against my projection, paired week by week across all ${String(pooledWeeks)} scored gameweeks, then resampled 2,000 times. The dot is the mean gap; the whisker is the 95% interval, widened for the ${String(family)} rules tested at once \u2014 ${String(family)} chances at a 95% bar would otherwise fail about ${String(Math.round((1 - 0.95 ** family) * 100))}% of the time. A whisker touching the rule means the ranking above cannot tell those two apart, so the order it happened to land in is noise. A whisker clear of it on either side is a finding. ${separableVerdict(verdicts)}`}
              data={verdicts}
            />
          </>
        )}
        <p className="validation-note">
          Figures are the player&rsquo;s own score, not the doubled one. The
          doubling is a constant on every row, so it changes no ordering &mdash;
          but over a season a gap here is worth twice what it reads. The full
          table of rules, and what a season of each is worth, is on{" "}
          <Link to="/methodology#method-captaincy">the method page</Link>.
        </p>
      </section>

      <section aria-labelledby="reach-title">
        <h2 id="reach-title">Could the squad even reach that?</h2>
        <p>
          The captain rules above already use the fielded eleven. This section
          separates that decision from the squad-building gap: whether the best
          projection in the whole game was owned or fielded at all.
          <InfoMarker label="where these come from">
            The simulated leagues, replayed. Each gameweek keeps the squad it
            was played with, so &ldquo;was the best player in the game on your
            field&rdquo; and &ldquo;what could you have captained&rdquo; can be
            asked of a season that has already happened. No re-projection and no
            hindsight: the squad is whatever the transfers left.
          </InfoMarker>
        </p>

        {reachSeasons.length === 0 ? (
          <p className="validation-note">
            This artifact predates the reach measurements. They appear the next
            time <span className="mono">fpl_andres.cli.validate</span> runs.
          </p>
        ) : (
          <>
            <h3>Was the best player in the game on the field?</h3>
            <p className="validation-note">
              The highest projection in the game each week, and whether the
              advised squad owned him, started him and captained him. Counted
              over every advised manager and every gameweek they played.
            </p>
            <div
              aria-label="Scrollable reach table"
              className="squad-table-wrap"
              role="region"
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
              tabIndex={0}
            >
              <table aria-label="How often the game's best projection was on the field">
                <thead>
                  <tr>
                    <th scope="col">Season</th>
                    <th scope="col">Manager-gameweeks</th>
                    <th scope="col">Owned</th>
                    <th scope="col">Started</th>
                    <th scope="col">Captained</th>
                    <th scope="col">Held top spot longest</th>
                  </tr>
                </thead>
                <tbody>
                  {reachSeasons.map(({ season, reach }) => (
                    <tr key={season}>
                      <th scope="row">{season}</th>
                      <td className="mono">{reach.giant.gameweeks}</td>
                      <td className="mono">
                        {percent(reach.giant.ownedShare)}
                      </td>
                      <td className="mono">
                        {percent(reach.giant.startedShare)}
                      </td>
                      <td className="mono">
                        {percent(reach.giant.captainedShare)}
                      </td>
                      <td translate="no">
                        {reach.giant.leaders[0]
                          ? `${reach.giant.leaders[0].name} (${String(
                              reach.giant.leaders[0].gameweeks,
                            )} weeks)`
                          : "\u2014"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="validation-verdict">
              He is owned in three-quarters to nine-tenths of manager-gameweeks,
              which is the opposite of what I expected. Where owned and started
              differ he was on the bench, scoring nothing. The last column is
              the contested part: one season a single player held top spot for
              23 of 32 weeks, another the longest run was 8. &ldquo;Buy the best
              player and keep him&rdquo; is a strategy in some seasons and a
              fiction in others, and August cannot tell you which.
            </p>

            <h3>What the armband could have returned</h3>
            <p className="validation-note">
              Per gameweek, the player&rsquo;s own score rather than the doubled
              one. Best in your eleven is the best captain in the side that was
              fielded; best in the game is the best in the entire league, which
              nobody can reach.
            </p>
            <div
              aria-label="Scrollable captaincy reach table"
              className="squad-table-wrap"
              role="region"
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
              tabIndex={0}
            >
              <table aria-label="Captaincy scored against the eleven that was fielded">
                <thead>
                  <tr>
                    <th scope="col">Season</th>
                    <th scope="col">Captained</th>
                    <th scope="col">Best in your eleven</th>
                    <th scope="col">Best in the game</th>
                    <th scope="col">Avoidable</th>
                    <th scope="col">Out of reach</th>
                  </tr>
                </thead>
                <tbody>
                  {reachSeasons.map(({ season, reach }) => (
                    <tr key={season}>
                      <th scope="row">{season}</th>
                      <td className="mono">
                        {show(reach.captaincy.meanChosen, 2)}
                      </td>
                      <td className="mono">
                        {show(reach.captaincy.meanOwnedCeiling, 2)}
                      </td>
                      <td className="mono">
                        {show(reach.captaincy.meanGameCeiling, 2)}
                      </td>
                      <td className="mono">
                        {show(reach.captaincy.ownedRegret, 2)}
                      </td>
                      <td className="mono">
                        {show(reach.captaincy.reachGap, 2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="validation-verdict">
              Two different failures, and only one of them is a decision.
              &ldquo;Avoidable&rdquo; is what better captaincy from the same
              eleven was worth &mdash; that is skill, and it is on me.
              &ldquo;Out of reach&rdquo; is the distance from the best captain
              in your squad to the best captain in the game, which no call on
              the day could close. The owned-XI comparison above keeps that gap
              separate from the captain rule.
            </p>
          </>
        )}

        {openingSeasons.length === 0 ? null : (
          <>
            <h3>Is it easier to start with him than to get him later?</h3>
            <p className="validation-note">
              The same season played twice from the same seeds. The only
              difference is whether the highest projection at the opening
              gameweek was forced into the opening fifteen. Who that is comes
              from the projection at that deadline, not from how the season
              turned out.
            </p>
            <div
              aria-label="Scrollable opening comparison table"
              className="squad-table-wrap"
              role="region"
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
              tabIndex={0}
            >
              <table aria-label="Opening with the best player against buying him later">
                <thead>
                  <tr>
                    <th scope="col">Season</th>
                    <th scope="col">Who</th>
                    <th scope="col">Left to the transfers</th>
                    <th scope="col">Opened with him</th>
                    <th scope="col">Difference</th>
                    <th scope="col">Weeks before he was owned</th>
                  </tr>
                </thead>
                <tbody>
                  {openingSeasons.map(({ season, opening }) => (
                    <tr key={season}>
                      <th scope="row">{season}</th>
                      <td translate="no">{opening.name}</td>
                      <td className="mono">
                        {opening.meanWithout.toLocaleString("en-GB")}
                      </td>
                      <td className="mono">
                        {opening.meanOpeningWithHim.toLocaleString("en-GB")}
                      </td>
                      <td className="mono">
                        {opening.gain >= 0 ? "+" : "\u2212"}
                        {Math.abs(opening.gain).toLocaleString("en-GB")}
                      </td>
                      <td className="mono">
                        {show(opening.meanGameweeksBeforeOwned, 1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="validation-verdict">
              Worth doing when the man at the top is a premium attacker, worth
              nothing when he is not. The negative season is the informative
              one: the highest projection at that deadline was a goalkeeper, and
              spending the opening budget on the biggest number in the game is a
              worse rule than it sounds when that number belongs to somebody who
              cannot be captained. Read the last column too &mdash; where the
              transfers were going to buy him within a fortnight anyway, forcing
              him in bought a week, not a season.
            </p>
          </>
        )}
      </section>

      <section aria-labelledby="league-title">
        <h2 id="league-title">Does following me actually help?</h2>
        <p>
          {report.league.managers} managers per league, each starting from a
          different random squad. {Math.round(report.league.advisedShare * 100)}
          % follow my projection. The rest play the baselines below.
          <InfoMarker label="how the leagues are run">
            Every policy starts from the same opening squad, so any difference
            is the policy and not the luck of the draw. The squad carries over
            week to week, one free transfer arrives each gameweek and banks up
            to five, and any move beyond the bank costs four points. All four
            chips are played by every policy. Team value moves with prices, and
            a risen player sells for only half his profit.
          </InfoMarker>
        </p>
        <div
          aria-label="Scrollable Overall Rank comparison table"
          className="squad-table-wrap policy-rank-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
          tabIndex={0}
        >
          <table aria-label="Overall Rank bands implied by simulated policy points">
            <thead>
              <tr>
                <th scope="col">Season</th>
                <th scope="col">Policy</th>
                <th scope="col">Simulated</th>
                <th scope="col">38-GW pro-rate</th>
                <th scope="col">Empirical OR</th>
              </tr>
            </thead>
            <tbody>
              {report.seasons.flatMap((season) =>
                POLICY_ORDER.map((policy) => {
                  const result = season.league.policies[policy];
                  if (!result) return null;
                  const band = result.overallRankBin ?? result.overallRankBand;
                  return (
                    <tr
                      className={`${rankBandClass(band)} ${policy === "advised" ? "is-mine" : ""}`}
                      key={`${season.season}-${policy}`}
                    >
                      <th scope="row">{season.season}</th>
                      <td>{POLICY_NAMES[policy]}</td>
                      <td className="mono">
                        {result.mean.toLocaleString("en-GB")} /{" "}
                        {season.gameweeksPlayed} GW
                      </td>
                      <td className="mono">
                        {result.prorated38Gameweeks?.toLocaleString("en-GB") ??
                          "awaiting refresh"}
                      </td>
                      <td>
                        <span className="policy-rank-label">
                          {rankBandLabel(band)}
                        </span>
                        <span className="policy-rank-performance mono">
                          {rankPerformanceLabel(band)}
                        </span>
                        {band ? (
                          <span className="policy-rank-sample mono">
                            {band.sampleSize ?? "rough"} observed finishes
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
        </div>
        <p className="validation-note">
          The rank column uses the nearest observed finish inside and outside
          fixed 1k, 10k, 50k, 100k, 250k, 500k, 1m, 2m and 3m cutoffs. Around
          means the score sits inside that measured point bracket; it is not an
          interpolated exact rank. The simulated totals cover 31 or 32
          gameweeks, so the 38-GW figure is a straight pro-rate. Top 500k is the
          minimum acceptable outcome here; anything below it is labelled a total
          flop.
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
          test. {leagueVerdict(report.seasons)} These totals cover{" "}
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
