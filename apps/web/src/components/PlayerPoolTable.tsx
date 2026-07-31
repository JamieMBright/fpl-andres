import { useEffect, useMemo, useState } from "react";

import { rateFixtureRun, type FixtureRun } from "../state/fixture-run";
import {
  fetchPlayerPool,
  PlayerPoolError,
  type PlayerPool,
  type PoolFailure,
  type PoolPlayer,
} from "../state/player-pool";
import { projectionSeason } from "../state/squad-projection";

type SortKey = "points" | "perMillion" | "price" | "run";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "points", label: "Points per match" },
  { key: "perMillion", label: "Points per \u00a31m" },
  { key: "price", label: "Price" },
  { key: "run", label: "Opening five" },
];

// Five gameweeks: long enough to matter to a transfer, short enough that the
// squads playing them still resemble the ones named today.
const RUN_WINDOW = 5;

const moneyFormatter = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function money(valueTenths: number): string {
  return `${moneyFormatter.format(valueTenths / 10)}m`;
}

/**
 * The next five gameweeks, rated on the route that matters for the position.
 *
 * A goalkeeper or defender is rated on what his opponents score, an attacker on
 * what they concede. One is average. The opponents are named, because a number
 * you cannot check is not evidence.
 */
function FixtureRunCell({
  position,
  run,
}: {
  position: string;
  run: FixtureRun;
}) {
  if (run.rating === null) {
    return <span className="pool-unrated">—</span>;
  }
  const defensive = position === "GKP" || position === "DEF";
  const kind = defensive ? "score" : "concede";
  const good = defensive ? run.rating < 1 : run.rating > 1;
  const named = run.opponents.filter(Boolean).join(", ");

  return (
    <span
      className={good ? "pool-run-good" : "pool-run-hard"}
      title={`${named || "unknown"} — opponents ${kind} ${run.rating.toFixed(2)}× the average`}
    >
      {run.rating.toFixed(2)}
      {run.rated < run.fixtures ? (
        <span className="pool-partial">
          {" "}
          {run.rated}/{run.fixtures}
        </span>
      ) : null}
    </span>
  );
}

function sortValue(player: PoolPlayer, key: SortKey, run: FixtureRun): number {
  if (key === "price") return player.priceTenths;
  if (key === "perMillion") return player.perMillion ?? -1;
  if (key === "run") {
    if (run.rating === null) return -Infinity;
    // A defender wants opponents who score little; an attacker wants opponents
    // who concede a lot. Both are expressed as an advantage over an average
    // opponent so the two positions can be ordered against each other at all.
    const defensive = player.position === "GKP" || player.position === "DEF";
    return defensive ? 1 - run.rating : run.rating - 1;
  }
  return player.record?.expectedPoints ?? -1;
}

/**
 * Everyone in the 2026/27 game, priced now, measured on last season.
 *
 * The point of this page is that it is useful before a ball is kicked: prices
 * are already published and last season's record is already measured, so the
 * one question that can honestly be answered — what does this player return,
 * and what does he now cost — is answered.
 */
export function PlayerPoolTable() {
  const [pool, setPool] = useState<PlayerPool | null>(null);
  const [failed, setFailed] = useState<PoolFailure | null>(null);
  const [position, setPosition] = useState("ALL");
  const [sort, setSort] = useState<SortKey>("points");
  const [maxPrice, setMaxPrice] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    fetchPlayerPool(fetch, controller.signal)
      .then((result) => {
        if (active) setPool(result);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        if (!active) return;
        setFailed(
          error instanceof PlayerPoolError ? error.reason : "unreachable",
        );
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  const shown = useMemo(() => {
    if (!pool) return [];
    const runs = new Map<number, FixtureRun>();
    const runFor = (player: PoolPlayer): FixtureRun => {
      const cached = runs.get(player.elementId);
      if (cached) return cached;
      const run = rateFixtureRun(
        pool.clubCodeByTeamId,
        pool.fixtures,
        player.teamId,
        player.position,
        RUN_WINDOW,
      );
      runs.set(player.elementId, run);
      return run;
    };

    return pool.players
      .filter((player) => position === "ALL" || player.position === position)
      .filter((player) => maxPrice === 0 || player.priceTenths <= maxPrice)
      .map((player) => ({ player, run: runFor(player) }))
      .sort(
        (left, right) =>
          sortValue(right.player, sort, right.run) -
          sortValue(left.player, sort, left.run),
      );
  }, [pool, position, sort, maxPrice]);

  if (failed) {
    return (
      <p className="pool-state" role="alert">
        {failed === "source_contract_failed"
          ? "FPL answered, but not in the shape I expect. Rather than guess at " +
            "what changed, I am showing you nothing. This one is mine to fix."
          : "I could not reach the player list. Nothing has been substituted " +
            "for it. Reload to try again."}
      </p>
    );
  }

  if (!pool) {
    return (
      <p className="pool-state" role="status">
        Reading the 2026/27 player list from FPL…
      </p>
    );
  }

  const unknown = pool.players.filter(
    (player) => player.record === null,
  ).length;

  return (
    <>
      <p className="pool-basis">
        Prices are the ones FPL has published for 2026/27. The points figure is
        what each player actually returned per match in {projectionSeason},
        rebuilt from every scoring route. Dividing one by the other tells you
        what he costs per point <em>today</em> — which is the only part of this
        that is new information.
      </p>

      <div className="pool-controls">
        <label>
          Position
          <select
            onChange={(event) => setPosition(event.target.value)}
            value={position}
          >
            <option value="ALL">All</option>
            {pool.positions.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        <label>
          Sort by
          <select
            onChange={(event) => setSort(event.target.value as SortKey)}
            value={sort}
          >
            {SORTS.map(({ key, label }) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Max price
          <select
            onChange={(event) => setMaxPrice(Number(event.target.value))}
            value={maxPrice}
          >
            <option value={0}>Any</option>
            {[45, 55, 65, 75, 85, 100, 120].map((tenths) => (
              <option key={tenths} value={tenths}>
                {money(tenths)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="pool-count mono">
        {shown.length} shown · {unknown} in the game with no record
      </p>

      <div
        aria-label="Scrollable player list"
        className="squad-table-wrap"
        role="region"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
        tabIndex={0}
      >
        <table aria-label="2026/27 players against last season's record">
          <thead>
            <tr>
              <th scope="col">Player</th>
              <th scope="col">Pos</th>
              <th scope="col">Club</th>
              <th scope="col">Price</th>
              <th scope="col">Pts / match</th>
              <th scope="col">Per £1m</th>
              <th scope="col">Returned</th>
              <th scope="col">Ceiling</th>
              <th scope="col">Apps</th>
              <th scope="col">Opening five</th>
            </tr>
          </thead>
          <tbody>
            {shown.slice(0, 200).map(({ player, run }) => (
              <tr key={player.code}>
                <th scope="row" translate="no">
                  {player.name}
                  {player.available ? null : (
                    <span className="pool-flag" title="Flagged by FPL">
                      {" "}
                      ⚑
                    </span>
                  )}
                </th>
                <td className="mono">{player.position}</td>
                <td className="mono" translate="no">
                  {player.club}
                </td>
                <td className="mono">{money(player.priceTenths)}</td>
                <td className="mono">
                  {player.record
                    ? player.record.expectedPoints.toFixed(2)
                    : "—"}
                </td>
                <td className="mono">{player.perMillion?.toFixed(2) ?? "—"}</td>
                <td className="mono">
                  {player.record?.returnRate === null ||
                  player.record?.returnRate === undefined
                    ? "—"
                    : `${Math.round(player.record.returnRate * 100)}%`}
                </td>
                <td className="mono">{player.record?.ceiling ?? "—"}</td>
                <td className="mono">{player.record?.appearances ?? "—"}</td>
                <td className="mono">
                  <FixtureRunCell position={player.position} run={run} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {shown.length > 200 ? (
        <p className="pool-truncated">
          Showing the first 200 of {shown.length}. Narrow the filters rather
          than scrolling: nobody picks a squad from row 400.
        </p>
      ) : null}

      <p className="pool-footnote">
        A dash means I hold no Premier League record for that player — a
        promoted-club regular, an arrival from abroad, or someone who played too
        little of {projectionSeason} to describe. There are {unknown} of them.
        They are left blank on purpose. A price is not evidence.
      </p>

      <p className="pool-footnote">
        <strong>Opening five</strong> rates the next five gameweeks against the
        opponents&rsquo; measured strength, at the venue each match is played.
        For a goalkeeper or defender it is what those opponents <em>score</em>,
        so below one is good. For a midfielder or forward it is what they{" "}
        <em>concede</em>, so above one is good. One blended difficulty number
        would hide that a hard fixture suppresses clean sheets while raising
        saves. Where a fraction appears, the rest of the run is against promoted
        clubs I have never measured; blanks count as no fixture and doubles
        count twice.
      </p>
    </>
  );
}
