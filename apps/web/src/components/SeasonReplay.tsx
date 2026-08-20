import { useMemo, useState } from "react";

import validation from "../data/validation.json";

/**
 * One replayed season, one week at a time.
 *
 * The rest of this page reports totals, and a total is a claim nobody can
 * check. This is the same season as a ledger: step to any week and see what was
 * bought, what was sold, what the armband was worth, which chip was burned and
 * what the bench was left holding. If a week looks wrong, it can be said so.
 */

type ReplayTransfer = {
  out: number;
  outName: string | null;
  in: number;
  inName: string | null;
};

type ReplayWeek = {
  event: number;
  points: number;
  runningTotal: number;
  chip: string | null;
  captain: number | null;
  captainName: string | null;
  captainPoints: number;
  benchPoints: number;
  hitPoints: number;
  transfers: ReplayTransfer[];
  teamValueTenths: number;
  bankTenths: number;
  starters: number[];
};

type ReplayBenchmark = {
  managers: number;
  beaten: number;
  percentile: number;
  best: number;
  medianPoints: number;
};

type SeasonReplayData = {
  season: string;
  startGameweek: number;
  totalPoints: number;
  hitPoints: number;
  netPoints: number;
  transfers: number;
  chips: Record<string, number[]>;
  finalTeamValueTenths: number;
  benchmark: ReplayBenchmark | null;
  weeks: ReplayWeek[];
};

const CHIP_LABELS: Record<string, string> = {
  bench_boost: "Bench Boost",
  free_hit: "Free Hit",
  triple_captain: "Triple Captain",
  wildcard: "Wildcard",
};

function chipLabel(chip: string): string {
  return CHIP_LABELS[chip] ?? chip;
}

function replaysFrom(report: unknown): SeasonReplayData[] {
  const seasons = (report as { seasons?: { replay?: SeasonReplayData }[] })
    .seasons;
  return (seasons ?? [])
    .map((season) => season.replay)
    .filter((replay): replay is SeasonReplayData =>
      Boolean(replay && replay.weeks?.length),
    );
}

export function SeasonReplay() {
  const replays = useMemo(() => replaysFrom(validation), []);
  // Newest season first: the one a reader cares about is the one just played.
  const ordered = useMemo(
    () => [...replays].sort((a, b) => b.season.localeCompare(a.season)),
    [replays],
  );
  const [seasonIndex, setSeasonIndex] = useState(0);
  const [week, setWeek] = useState(0);

  const replay = ordered[seasonIndex];
  if (replay === undefined) {
    // The measurement arrives with the next validate run. Say nothing rather
    // than render an empty season.
    return null;
  }

  const current = replay.weeks[Math.min(week, replay.weeks.length - 1)];
  if (current === undefined) return null;

  function selectSeason(index: number) {
    setSeasonIndex(index);
    setWeek(0);
  }

  return (
    <section aria-labelledby="replay-title" className="replay">
      <h2 id="replay-title">Play the season back, week by week</h2>
      <p>
        The same model, opening in August and playing to the end: transfers,
        hits, captaincy, auto-substitutions and every chip the season actually
        granted &mdash; which from 2025-26 is two of each rather than one, a set
        per half. Step through it and check the weeks rather than taking the
        total on trust.
      </p>

      <div className="replay-controls">
        <label>
          <span>Season</span>
          <select
            value={seasonIndex}
            onChange={(event) => selectSeason(Number(event.target.value))}
          >
            {ordered.map((entry, index) => (
              <option key={entry.season} value={index}>
                {entry.season}
              </option>
            ))}
          </select>
        </label>
        <label className="replay-scrub">
          <span>Gameweek {current.event}</span>
          <input
            type="range"
            min={0}
            max={replay.weeks.length - 1}
            value={Math.min(week, replay.weeks.length - 1)}
            onChange={(event) => setWeek(Number(event.target.value))}
            aria-label="Gameweek"
          />
        </label>
      </div>

      <div className="replay-week">
        <h3>
          Gameweek {current.event}
          {current.chip ? ` — ${chipLabel(current.chip)}` : ""}
        </h3>
        <dl className="replay-figures">
          <div>
            <dt>Scored</dt>
            <dd className="mono">{current.points}</dd>
          </div>
          <div>
            <dt>Hits</dt>
            <dd className="mono">
              {current.hitPoints === 0 ? "0" : `\u2212${current.hitPoints}`}
            </dd>
          </div>
          <div>
            <dt>Running total</dt>
            <dd className="mono">
              {current.runningTotal.toLocaleString("en-GB")}
            </dd>
          </div>
          <div>
            <dt>Captain</dt>
            <dd>
              {current.captainName ?? "—"}
              <span className="mono"> ({current.captainPoints})</span>
            </dd>
          </div>
          <div>
            <dt>Left on the bench</dt>
            <dd className="mono">{current.benchPoints}</dd>
          </div>
          <div>
            <dt>Squad value</dt>
            <dd className="mono">
              {(current.teamValueTenths / 10).toFixed(1)}m
            </dd>
          </div>
        </dl>
        <div className="replay-transfers">
          <h4>Transfers</h4>
          {current.transfers.length === 0 ? (
            <p>None. The free transfer was banked.</p>
          ) : (
            <ul>
              {current.transfers.map((transfer) => (
                <li key={`${transfer.out}-${transfer.in}`}>
                  <span className="replay-out">
                    {transfer.outName ?? transfer.out}
                  </span>
                  {" \u2192 "}
                  <span className="replay-in">
                    {transfer.inName ?? transfer.in}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <SeasonOutcome replay={replay} />
    </section>
  );
}

function SeasonOutcome({ replay }: { replay: SeasonReplayData }) {
  const chips = Object.entries(replay.chips)
    .flatMap(([chip, weeks]) => weeks.map((week) => ({ chip, week })))
    .sort((a, b) => a.week - b.week);
  return (
    <div className="replay-outcome">
      <h3>Where {replay.season} finished</h3>
      <dl className="replay-figures">
        <div>
          <dt>Points</dt>
          <dd className="mono">{replay.netPoints.toLocaleString("en-GB")}</dd>
        </div>
        <div>
          <dt>Transfers</dt>
          <dd className="mono">
            {replay.transfers}
            {replay.hitPoints > 0 ? ` (\u2212${replay.hitPoints})` : ""}
          </dd>
        </div>
        <div>
          <dt>Chips played</dt>
          <dd className="mono">{chips.length}</dd>
        </div>
      </dl>
      <p className="replay-chips">
        {chips.length === 0
          ? "No chips played."
          : chips
              .map(({ chip, week }) => `${chipLabel(chip)} GW${week}`)
              .join(" · ")}
      </p>
      {replay.benchmark === null ? (
        <p className="validation-note">
          No harvested manager totals for this season, so there is nothing
          honest to compare it against.
        </p>
      ) : (
        <p className="validation-verdict">
          Against {replay.benchmark.managers.toLocaleString("en-GB")} real
          managers whose {replay.season} totals I hold, that beats{" "}
          {replay.benchmark.beaten.toLocaleString("en-GB")} of them &mdash; the{" "}
          {replay.benchmark.percentile.toFixed(0)}th percentile of that group.
          Their median was{" "}
          {replay.benchmark.medianPoints.toLocaleString("en-GB")} and the best
          of them scored {replay.benchmark.best.toLocaleString("en-GB")}. They
          are a ranked cohort rather than the whole game, so this is a harder
          room than an overall rank.
        </p>
      )}
    </div>
  );
}
