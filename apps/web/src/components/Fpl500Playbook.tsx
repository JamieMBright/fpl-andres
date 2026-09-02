import { useState } from "react";

import { InfoMarker } from "./InfoMarker";
import { Fpl500ChipAdoption } from "./Fpl500ChipAdoption";
import { Fpl500Holdings, type Fpl500Holding } from "./Fpl500Holdings";
import { Fpl500Structure, type PortfolioStructure } from "./Fpl500Structure";
import { Fpl500TransferFlow } from "./Fpl500TransferFlow";
import { BarChart, type Bar } from "./MethodChart";
import { PlannedAnalysis } from "./PlannedAnalysis";
import { RankRidge, type Ridge } from "./RankRidge";
import fpl500 from "../data/fpl500.json";
import { fineShare, integer, oneDecimal, share, timestamp } from "../format";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import { pointsDistribution } from "../state/rank-distribution";
import {
  FPL500_SCHEMA_VERSION,
  requireArtifactVersion,
} from "../state/artifact-version";

// `points` arrives only once every fixture in the round has a confirmed score.
// It is absent, never zero, while a week is still being played — a captain who
// blanked and a captain who has not kicked off are different facts.
type CaptainEntry = { elementId: number; share: number; points?: number };
type PortfolioSample = {
  capturedAt: string;
  attempted: number;
  responded: number;
  counted: number;
  coverage: number;
  membershipLabel?: string;
  membershipSourceGeneratedAt?: string;
  membershipSecondsFromDeadline?: number;
  aggregate?: {
    chips: Record<string, number>;
    totalPoints: DistributionSummary;
    benchPoints: DistributionSummary;
    squadValueTenths: DistributionSummary;
    bankTenths: DistributionSummary;
    transfersAvailable: boolean;
  };
  structure?: PortfolioStructure;
};
type DistributionSummary = {
  mean: number;
  median: number;
  p10: number;
  p90: number;
  minimum: number;
  maximum: number;
};
type PortfolioSeries = {
  basis: "catalogue-at-deadline" | "ranked-500";
  label: string;
  events: number[];
  samples: Record<string, PortfolioSample>;
  captains: Record<string, CaptainEntry[]>;
  holdings?: Record<string, Fpl500Holding[]>;
};

type Fpl500 = {
  generatedAt: string;
  catalogueSize: number;
  sweptTo: number | null;
  size: number;
  settings: { rulesChangedIn: number; minimumSeasons: number };
  latestSeason: string | null;
  latestSeasonEntries: number | null;
  minimumCoverage: number;
  cataloguePortfolio: PortfolioSeries;
  exactFpl500Portfolio: PortfolioSeries;
  rankBins: number[];
  rankHistogram: Record<string, number[]>;
  seasonsCounted: Record<string, number>;
  thisSeason: {
    size: number;
    managers: { rank: number; entryId: number; total: number }[];
  };
};

requireArtifactVersion("fpl500", fpl500, FPL500_SCHEMA_VERSION);
const data = fpl500 as Fpl500;
const number = integer;
const PAGE = 20;

function finishesAtOrAbove(rank: number): number {
  const bins = data.rankBins.findIndex((edge) => edge === rank);
  if (bins < 0) {
    return 0;
  }
  return Object.values(data.rankHistogram).reduce(
    (total, counts) =>
      total + counts.slice(0, bins + 1).reduce((sum, count) => sum + count, 0),
    0,
  );
}

/** A fold, colour-coded like the strip above it. */
function Fold({
  children,
  id,
  kind,
  open,
  title,
}: {
  children: React.ReactNode;
  id?: string;
  kind: string;
  open?: boolean;
  title: string;
}) {
  return (
    <details className={`fpl500-fold is-${kind}`} id={id} open={open}>
      <summary>
        <h2>{title}</h2>
      </summary>
      <div className="fpl500-fold-body">{children}</div>
    </details>
  );
}

/**
 * Armband distribution for a set of captured gameweeks.
 *
 * Shows who the cohort captained and by how much. When the cohort is nearly
 * unanimous the week says nothing interesting about strategy — and this
 * component says so. When the week is split, the bar chart makes the
 * disagreement visible.
 */
function CaptainSeries({
  id,
  series,
}: {
  id: string;
  series: PortfolioSeries;
}) {
  const captains = series.captains;
  const events = Object.keys(captains).sort((a, b) => Number(a) - Number(b));
  if (events.length === 0) {
    return (
      <section
        className="cohort-armband-series"
        aria-labelledby={`${id}-title`}
      >
        <h4 id={`${id}-title`}>{series.label}</h4>
        <p className="mono cohort-armband-empty">No captured gameweeks.</p>
      </section>
    );
  }

  return (
    <section className="cohort-armband-series" aria-labelledby={`${id}-title`}>
      <h4 id={`${id}-title`}>{series.label}</h4>
      <div className="cohort-armband-weeks">
        {events.map((eventKey) => {
          const top = captains[eventKey] ?? [];
          const sample = series.samples[eventKey];
          const best = top[0];
          const isUnanimous = best !== undefined && best.share > 0.5;
          const bestName =
            best !== undefined
              ? (PLAYERS_BY_ELEMENT_ID.get(best.elementId)?.name ??
                `element ${best.elementId}`)
              : "—";
          return (
            <div className="cohort-armband-week" key={eventKey}>
              <p className="cohort-armband-gw mono">GW{Number(eventKey)}</p>
              {sample !== undefined && (
                <p className="cohort-armband-sample mono">
                  {number.format(sample.responded)} of{" "}
                  {number.format(sample.attempted)} managers ·{" "}
                  {fineShare.format(sample.coverage)} coverage · picks read{" "}
                  {timestamp.format(new Date(sample.capturedAt))}
                </p>
              )}
              {sample?.membershipLabel !== undefined && (
                <p className="cohort-armband-provenance">
                  {sample.membershipLabel}
                  {sample.membershipSecondsFromDeadline === undefined
                    ? ""
                    : ` · ranked ${number.format(
                        Math.round(sample.membershipSecondsFromDeadline / 60),
                      )} minutes after the deadline`}
                </p>
              )}
              <ul className="cohort-armband-bars">
                {top.map(({ elementId, share: s, points }) => {
                  const name =
                    PLAYERS_BY_ELEMENT_ID.get(elementId)?.name ??
                    `element ${elementId}`;
                  return (
                    <li key={elementId} className="cohort-armband-bar">
                      <span
                        className="cohort-armband-fill"
                        style={{ width: `${Math.round(s * 100)}%` }}
                        aria-hidden="true"
                      />
                      <span className="cohort-armband-label">
                        {name} {fineShare.format(s)}
                        {points === undefined
                          ? ""
                          : ` · ${integer.format(points)} pts`}
                      </span>
                    </li>
                  );
                })}
              </ul>
              {isUnanimous && (
                <p className="cohort-armband-verdict mono">
                  Near-unanimous on {bestName} — no thesis separates here.
                </p>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function CaptainDistribution() {
  return (
    <section aria-labelledby="cohort-armband-title" className="cohort-armband">
      <h3 id="cohort-armband-title">
        The armband, week by week
        <InfoMarker label="armband samples">
          Two populations, kept separate. The catalogue shows every manager
          captured around the deadline. Exact FPL500 uses the five hundred
          ranked at the stated source time. A points figure appears only after
          every fixture has a confirmed score, including bonus.
        </InfoMarker>
      </h3>
      <p>
        Captain choices from the five hundred managers ranked at the captured
        source time.
      </p>
      <CaptainSeries
        id="exact-fpl500-armband"
        series={data.exactFpl500Portfolio}
      />
    </section>
  );
}

/**
 * The gameweek this page describes: the newest one captured that FPL has also
 * scored.
 *
 * Reading `["01"]` outright kept the page on the opening gameweek all season.
 * Reading the newest capture instead was worse for a day: a round is captured
 * as soon as its deadline passes, hours before FPL confirms the points, and
 * every holding in it reads zero until then. Showing the newest *scored*
 * gameweek means the page is never a wall of zeros, and it still advances on
 * its own the moment the points land.
 */
export function latestCapture(
  series: PortfolioSeries,
): { event: number; key: string } | null {
  const keyed = [...series.events]
    .sort((left, right) => right - left)
    .map((event) => ({ event, key: String(event).padStart(2, "0") }));
  const scored = keyed.find(({ key }) =>
    (series.holdings?.[key] ?? []).some((holding) => holding.lastWeekPoints),
  );
  return scored ?? keyed[0] ?? null;
}

function LatestCohortSummary() {
  const latest = latestCapture(data.exactFpl500Portfolio);
  const sample = latest ? data.exactFpl500Portfolio.samples[latest.key] : null;
  const aggregate = sample?.aggregate;
  if (!latest || !sample || !aggregate) return null;
  const gameweek = `GW${String(latest.event)}`;
  const chipBars: Bar[] = Object.entries(aggregate.chips).map(
    ([chip, count]) => ({
      label:
        chip === "none"
          ? "No chip"
          : chip === "bboost"
            ? "Bench Boost"
            : chip === "3xc"
              ? "Triple Captain"
              : chip,
      value: count,
      shown: number.format(count),
    }),
  );
  return (
    <section
      className="fpl500-gw-summary"
      aria-labelledby="fpl500-gw-summary-title"
      id="fpl500-chips"
    >
      <h3 id="fpl500-gw-summary-title">{gameweek}, across 500 squads</h3>
      <dl className="dossier-metrics">
        <div>
          <dt>Mean score</dt>
          <dd>{oneDecimal.format(aggregate.totalPoints.mean)}</dd>
        </div>
        <div>
          <dt>Median score</dt>
          <dd>{oneDecimal.format(aggregate.totalPoints.median)}</dd>
        </div>
        <div>
          <dt>Mean bench</dt>
          <dd>{oneDecimal.format(aggregate.benchPoints.mean)}</dd>
        </div>
        <div>
          <dt>Score range</dt>
          <dd>
            {aggregate.totalPoints.minimum}–{aggregate.totalPoints.maximum}
          </dd>
        </div>
      </dl>
      <BarChart
        bars={chipBars}
        caption={`Which chips they spent in ${gameweek}`}
        unit="managers"
      />
      <Fpl500ChipAdoption series={data.exactFpl500Portfolio} />
      <p className="mono fpl500-note">
        {number.format(sample.responded)} of {number.format(sample.attempted)}{" "}
        histories · {fineShare.format(sample.coverage)} coverage.
        {latest.event === 1 ? " Transfers start at GW2." : null}
      </p>
    </section>
  );
}

function BenchUse({ holdings }: { holdings: readonly Fpl500Holding[] }) {
  const benched = [...holdings]
    .map((holding) => ({
      ...holding,
      benchedShare: Math.max(0, holding.ownedShare - holding.startedShare),
      player: PLAYERS_BY_ELEMENT_ID.get(holding.elementId),
    }))
    .filter((holding) => holding.benchedShare >= 0.01)
    .sort((left, right) => right.benchedShare - left.benchedShare)
    .slice(0, 6);
  if (benched.length === 0) return null;
  return (
    <section
      className="fpl500-bench-use"
      aria-labelledby="fpl500-bench-use-title"
    >
      <h3 id="fpl500-bench-use-title">Who they left on the bench</h3>
      <ul>
        {benched.map((holding) => (
          <li key={holding.elementId}>
            <span>
              {holding.name ??
                holding.player?.name ??
                `Element ${holding.elementId}`}
            </span>
            <strong className="mono">
              {fineShare.format(holding.benchedShare)}
            </strong>
          </li>
        ))}
      </ul>
    </section>
  );
}

function CurrentSeason() {
  const [page, setPage] = useState(0);
  const rows = data.thisSeason.managers;

  if (rows.length === 0) {
    return (
      <p className="mono">
        The Overall league has no standings until the first gameweek is scored.
      </p>
    );
  }

  const distribution = pointsDistribution(rows);
  const distributionBars: Bar[] = distribution.map((bucket) => ({
    label: bucket.label,
    value: bucket.count,
    shown: String(bucket.count),
  }));
  const pages = Math.ceil(rows.length / PAGE);
  const shown = rows.slice(page * PAGE, page * PAGE + PAGE);
  return (
    <>
      <BarChart
        bars={distributionBars}
        caption={`Points spread across the top ${number.format(rows.length)}`}
        unit="managers"
      />
      <div className="fpl500-scroll">
        <table className="squad-table">
          <caption className="visually-hidden">
            The top {rows.length} of the Overall league this season
          </caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Entry</th>
              <th scope="col">Points</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.entryId}>
                <td className="mono">{row.rank}</td>
                <td className="mono">
                  <a
                    href={`https://fantasy.premierleague.com/entry/${row.entryId}/history`}
                    rel="noreferrer noopener"
                    target="_blank"
                  >
                    {row.entryId}
                  </a>
                </td>
                <td className="mono">{number.format(row.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="fpl500-pager">
        <button
          disabled={page === 0}
          onClick={() => setPage((current) => current - 1)}
          type="button"
        >
          Back
        </button>
        <span className="mono">
          {page * PAGE + 1}–{Math.min(rows.length, page * PAGE + PAGE)} of{" "}
          {rows.length}
        </span>
        <button
          disabled={page + 1 >= pages}
          onClick={() => setPage((current) => current + 1)}
          type="button"
        >
          Next
        </button>
      </div>
    </>
  );
}

function ExactFpl500Analysis() {
  const series = data.exactFpl500Portfolio;
  const latest = latestCapture(series);
  const captured = series.events.length;
  const holdings = latest ? (series.holdings?.[latest.key] ?? []) : [];
  const structure = latest ? series.samples[latest.key]?.structure : undefined;
  // A round captured at its deadline but not yet scored is held back rather
  // than shown as zeros, so the page says where it went.
  const newest = Math.max(0, ...series.events);
  const awaiting = latest && newest > latest.event ? newest : null;

  return (
    <>
      <p>
        {captured === 0
          ? "No exact FPL500 gameweek has been captured yet."
          : `${String(captured)} exact FPL500 ${captured === 1 ? "gameweek" : "gameweeks"} captured, showing GW${String(latest?.event ?? 0)}.`}
        {awaiting === null
          ? null
          : ` GW${String(awaiting)} is captured and waiting on FPL to confirm its points.`}
      </p>
      <LatestCohortSummary />
      <CaptainDistribution />
      {latest ? (
        <Fpl500Holdings
          event={latest.event}
          holdings={holdings}
          keeperPairings={structure?.keeperPairings}
          outfieldTrios={structure?.outfieldTrios}
        />
      ) : null}
      {structure ? (
        <Fpl500Structure holdings={holdings} structure={structure} />
      ) : null}
      <BenchUse holdings={holdings} />
      <section
        aria-labelledby="fpl500-transfer-flow-title"
        id="fpl500-transfers"
      >
        <h3 id="fpl500-transfer-flow-title">Who they are buying and selling</h3>
        <p>
          Net movement in the cohort's own squads between one capture and the
          next, not FPL's transfer counters.
        </p>
        <Fpl500TransferFlow series={series} />
      </section>
      <PlannedAnalysis event={(latest?.event ?? 0) + 1} only={["Hits taken"]} />
    </>
  );
}

/**
 * The cohort: what it is, how it is chosen, who is scoring now, and what will
 * be read off it once a ball is kicked.
 *
 * The five hundred are not named. Who clears the bar is the one thing here
 * somebody could copy outright, so the page carries the distribution instead —
 * which is also the more useful thing to look at.
 */
export function Fpl500Playbook() {
  const seasons: Bar[] = Object.entries(data.seasonsCounted).map(
    ([held, managers]) => ({
      label: held,
      value: managers,
      shown: String(managers),
    }),
  );
  const ridges: Ridge[] = Object.entries(data.rankHistogram).map(
    ([season, counts]) => ({ label: season, counts }),
  );
  const finishes = Object.values(data.rankHistogram).reduce(
    (total, counts) => total + counts.reduce((sum, count) => sum + count, 0),
    0,
  );
  const historicFinishes = [
    { label: "Top 1k finishes", count: finishesAtOrAbove(1_000) },
    { label: "Top 10k finishes", count: finishesAtOrAbove(10_000) },
    { label: "Top 100k finishes", count: finishesAtOrAbove(100_000) },
  ];
  const top10kShare = finishes > 0 ? finishesAtOrAbove(10_000) / finishes : 0;

  return (
    <>
      <p className="fpl500-hook">
        {number.format(data.size)} managers who have finished inside the FPL top
        ten thousand at least twice since 2021 — {share.format(top10kShare)} of
        their tracked seasons landed there. This is what they are doing right
        now, not what they say they do.
      </p>

      <nav aria-label="Jump to a section" className="fpl500-jump">
        <a href="#fpl500-rank">Rank</a>
        <a href="#cohort-armband-title">Captaincy</a>
        <a href="#fpl500-holdings-title">Players</a>
        <a href="#fpl500-chips">Chips</a>
        <a href="#fpl500-spend-title">Value</a>
        <a href="#fpl500-transfers">Transfers</a>
        <a href="#fpl500-structure-title">Squad</a>
      </nav>

      <Fold kind="what" title="What it is">
        <ul className="plan-promises">
          <li>
            Every FPL entry id is public, so the register is read, not guessed
            at.
          </li>
          <li>
            A manager is catalogued once they have finished inside the top ten
            thousand at least twice since 2021.
          </li>
          <li>
            The catalogue is ranked, and the first {number.format(data.size)}{" "}
            are FPL500.
          </li>
          <li>
            Coverage is not complete and is not claimed to be. Four fifths of
            the register is still unread.
          </li>
        </ul>
        <dl className="dossier-metrics">
          <div>
            <dt>Ranked managers</dt>
            <dd>{number.format(data.size)}</dd>
          </div>
          <div>
            <dt>Qualified candidates</dt>
            <dd>{number.format(data.catalogueSize)}</dd>
          </div>
          <div>
            <dt>Entry IDs read</dt>
            <dd>{data.sweptTo === null ? "—" : number.format(data.sweptTo)}</dd>
          </div>
          <div>
            <dt>Field size</dt>
            <dd>{number.format(data.latestSeasonEntries ?? 0)}</dd>
          </div>
          <div>
            <dt>Seasons profiled</dt>
            <dd>{number.format(ridges.length)}</dd>
          </div>
          <div>
            <dt>Finishes observed</dt>
            <dd>{number.format(finishes)}</dd>
          </div>
          {historicFinishes.map((metric) => (
            <div key={metric.label}>
              <dt>{metric.label}</dt>
              <dd>
                {number.format(metric.count)}{" "}
                <small>({share.format(metric.count / finishes)})</small>
              </dd>
            </div>
          ))}
        </dl>
        <p className="mono fpl500-source">
          Observed · FPL histories through{" "}
          {timestamp.format(new Date(data.generatedAt))}
        </p>
      </Fold>

      <Fold kind="how" title="How it is decided">
        <ul className="plan-promises">
          <li>
            <strong>Percentile, never rank.</strong> The field has grown from
            about a million entries to{" "}
            {number.format(data.latestSeasonEntries ?? 0)}. Ten thousandth in
            2007 and ten thousandth today are not the same achievement.
            <InfoMarker label="the rank ladder">
              Averaging raw ranks across seasons rewards being old rather than
              being good. Every season is converted to a position relative to
              its own field first. That field size is estimated from the largest
              rank the catalogue has observed in the season, which is a lower
              bound and makes early percentiles slightly flattering.
            </InfoMarker>
          </li>
          <li>
            <strong>Last season counts for most.</strong> Defensive
            contributions arrived in {data.settings.rulesChangedIn} and the chip
            rules match this year, so it is the only season played under the
            game as it is now. Each earlier season is weighted less than the one
            after it.
          </li>
          <li>
            <strong>Longevity is earned, not assumed.</strong> A thin record is
            pulled toward the middle of the field, so two brilliant seasons do
            not outrank twenty good ones. At least{" "}
            {data.settings.minimumSeasons} completed seasons are required before
            anyone is ranked.
          </li>
          <li>
            <strong>The weights themselves are ours.</strong> The shape is
            above; the numbers are not published.
          </li>
        </ul>
        <BarChart
          bars={seasons}
          caption="Seasons of history held by the ranked five hundred"
          unit="managers"
        />
        <RankRidge
          caption="Where they finish. Every season, the whole cohort, one shared axis."
          edges={data.rankBins}
          ridges={ridges}
        />
        <p className="mono fpl500-note">
          The mass between 1k and 10k is the cohort clearing its own bar. The
          tail past 100k is the same people having a bad year, which is why more
          than one season is weighed.
        </p>
      </Fold>

      <Fold id="fpl500-rank" kind="who" title="Who is scoring this season">
        <p>
          A different list, and a public one: the Overall standings as they
          stand. FPL500 trusts consistent experience; this is raw current form.
        </p>
        <CurrentSeason />
      </Fold>

      <Fold kind="when" title="When it updates">
        <ul className="plan-promises">
          <li>
            <strong>The register, every six hours.</strong> Two hundred requests
            read this season's top ten thousand off the Overall league. The
            slower pass over every entry id runs behind it, and picks up
            managers who have since stopped playing.
          </li>
          <li>
            <strong>The ranking, in the same job.</strong> Rebuilt where the
            catalogue is extended, so the two cannot describe different sweeps.
          </li>
          <li>
            <strong>The squads, after every deadline.</strong> Picks are private
            until one passes, and FPL serves them for the current season only,
            so a gameweek missed is gone for good.
            <InfoMarker label="the coverage floor">
              Every request will not answer. Dividing by however many did makes
              the denominator move every week, so a player looks to be drifting
              when the sample drifted instead. Below{" "}
              {fineShare.format(data.minimumCoverage)} the snapshot is refused
              rather than published with an asterisk.
            </InfoMarker>
          </li>
        </ul>
      </Fold>

      <Fold kind="analysis" open title="Analysing the FPL500">
        <ExactFpl500Analysis />
        <div className="cohort-caveat">
          <h3>What none of it can tell you</h3>
          <p>
            FPL500 measures past consistency, not next season&rsquo;s returns.
            Learn from the cohort; do not copy it.
          </p>
        </div>
      </Fold>
    </>
  );
}
