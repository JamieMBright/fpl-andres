import { useState } from "react";

import { InfoMarker } from "./InfoMarker";
import { BarChart, type Bar } from "./MethodChart";
import { PlannedAnalysis } from "./PlannedAnalysis";
import { RankRidge, type Ridge } from "./RankRidge";
import fpl500 from "../data/fpl500.json";
import { fineShare, integer, share, timestamp } from "../format";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";

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
};
type PortfolioSeries = {
  basis: "catalogue-at-deadline" | "ranked-500";
  label: string;
  events: number[];
  samples: Record<string, PortfolioSample>;
  captains: Record<string, CaptainEntry[]>;
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
  kind,
  open,
  title,
}: {
  children: React.ReactNode;
  kind: string;
  open?: boolean;
  title: string;
}) {
  return (
    <details className={`fpl500-fold is-${kind}`} open={open}>
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
        The first capture covered the whole catalogue. It was not the FPL500. I
        have kept that evidence and added the exact five hundred beside it.
      </p>
      <div className="cohort-armband-series-list">
        <CaptainSeries
          id="catalogue-armband"
          series={data.cataloguePortfolio}
        />
        <CaptainSeries
          id="exact-fpl500-armband"
          series={data.exactFpl500Portfolio}
        />
      </div>
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

  const pages = Math.ceil(rows.length / PAGE);
  const shown = rows.slice(page * PAGE, page * PAGE + PAGE);
  return (
    <>
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

  return (
    <>
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
      </dl>

      <section
        aria-labelledby="fpl500-previous-season-record"
        className="fpl500-history"
      >
        <h2 id="fpl500-previous-season-record">Previous-season record</h2>
        <p>
          How the selected five hundred finished across the five most recent
          completed seasons.
        </p>
        <dl className="dossier-metrics">
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
      </section>

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

      <Fold kind="who" title="Who is scoring this season">
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
        <p>
          {data.exactFpl500Portfolio.events.length === 0
            ? "No exact FPL500 gameweek has been captured yet."
            : `${data.exactFpl500Portfolio.events.length} exact FPL500 gameweek captured.`}
        </p>
        <CaptainDistribution />
        <PlannedAnalysis
          event={Math.max(0, ...data.exactFpl500Portfolio.events) + 1}
        />
        <div className="cohort-caveat">
          <h3>What none of it can tell you</h3>
          <p>
            Being in the FPL500 does not mean a manager will be good this
            season. What it means is that they have been consistent enough for
            long enough to qualify, which is why they are worth learning from
            rather than worth copying.
          </p>
        </div>
      </Fold>
    </>
  );
}
