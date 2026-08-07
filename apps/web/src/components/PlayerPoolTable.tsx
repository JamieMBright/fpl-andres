import { useCallback, useEffect, useMemo, useState } from "react";

import { PlayerDetail } from "./PlayerDetail";
import { classifyFetchFailure } from "../state/fetch-failure";
import { rateFixtureRun, type FixtureRun } from "../state/fixture-run";
import {
  fetchPlayerPool,
  PlayerPoolError,
  type PlayerPool,
  type PoolFailure,
  type PoolPlayer,
} from "../state/player-pool";
import { describeFreshness } from "../state/freshness";
import { retryingFetch } from "../state/retrying-fetch";
import { projectionSeason } from "../state/squad-projection";
import { money as sharedMoney } from "../format";

type SortKey =
  | "points"
  | "perMillion"
  | "price"
  | "run"
  | "returned"
  | "ceiling"
  | "apps"
  | "name"
  | "position"
  | "club";

interface Column {
  key: SortKey;
  label: string;
  /** What the number means. Shown on hover and to assistive technology. */
  explains: string;
  /** Text sorts A to Z; numbers sort high to low. */
  text?: boolean;
}

const COLUMNS: Column[] = [
  {
    key: "name",
    label: "Player",
    explains: "FPL's short name. A flag means FPL has news on him.",
    text: true,
  },
  {
    key: "position",
    label: "Pos",
    explains: "Goalkeeper, defender, midfielder or forward.",
    text: true,
  },
  { key: "club", label: "Club", explains: "Who he plays for now.", text: true },
  {
    key: "price",
    label: "Price",
    explains: "What FPL charges for him in 2026/27, today.",
  },
  {
    key: "points",
    label: "Pts / match",
    explains:
      "Expected FPL points in one match against an average opponent, from last season's per-90 rates and minutes. Four to six is a good starter.",
  },
  {
    key: "perMillion",
    label: "Per \u00a31m",
    explains:
      "Points per match divided by price. The cheapest route to a point, ignoring that you only field eleven.",
  },
  {
    key: "returned",
    label: "Returned",
    explains:
      "Share of his appearances with a goal or an assist. High means he delivers often; it says nothing about how much.",
  },
  {
    key: "ceiling",
    label: "Ceiling",
    explains: "His best single-match haul last season.",
  },
  {
    key: "apps",
    label: "Apps",
    explains: "Matches he appeared in last season.",
  },
  {
    key: "run",
    label: "Next 5",
    explains:
      "His next five fixtures, rated on the route that matters for his position: what opponents score if he defends, what they concede if he attacks. One is average.",
  },
];

// Five gameweeks: long enough to matter to a transfer, short enough that the
// squads playing them still resemble the ones named today.
const RUN_WINDOW = 5;

// Every gameweek that remains. A season is thirty-eight, so this asks for all
// of them and takes whatever the calendar still holds.
const SEASON_WINDOW = 38;

function money(valueTenths: number): string {
  return `${sharedMoney.format(valueTenths / 10)}m`;
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
  if (key === "returned") return player.record?.returnRate ?? -1;
  if (key === "ceiling") return player.record?.ceiling ?? -1;
  if (key === "apps") return player.record?.appearances ?? -1;
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

function textValue(player: PoolPlayer, key: SortKey): string {
  if (key === "position") return player.position;
  if (key === "club") return player.club;
  return player.name;
}

const TEXT_KEYS = new Set<SortKey>(["name", "position", "club"]);

/** Fold accents so searching "saliba" finds "Salib\u00e1". */
function fold(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
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
  const [descending, setDescending] = useState(true);
  const [maxPrice, setMaxPrice] = useState(0);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<PoolPlayer | null>(null);
  // Bumping this re-runs the load. A reader who is told to reload the page is
  // being asked to perform the retry by hand.
  const [attempt, setAttempt] = useState(0);

  // Clearing the previous failure belongs to the click rather than to the
  // effect: a setState in an effect body costs a cascading render for a value
  // only this button ever changes.
  const retry = useCallback(() => {
    setFailed(null);
    setAttempt((previous) => previous + 1);
  }, []);

  // Clicking a column sorts by it; clicking it again turns the order around.
  // Numbers start high, names start at A, because that is what each is for.
  const reorder = (key: SortKey) => {
    if (key === sort) {
      setDescending((was) => !was);
      return;
    }
    setSort(key);
    setDescending(!TEXT_KEYS.has(key));
  };

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    fetchPlayerPool(retryingFetch(), controller.signal)
      .then((result) => {
        if (active) setPool(result);
      })
      .catch((error: unknown) => {
        // One place decides what a thrown value was; this decides what to do
        // about it. Abort is a case rather than an exception to the cases,
        // because it arrives through the same channel and leaving it out is
        // how it ends up rendered as an error.
        const failure = classifyFetchFailure(error);
        if (failure.kind === "aborted" || !active) return;
        setFailed(
          error instanceof PlayerPoolError ? error.reason : "unreachable",
        );
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [attempt]);

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

    const needle = fold(search.trim());
    const direction = descending ? -1 : 1;

    return pool.players
      .filter((player) => position === "ALL" || player.position === position)
      .filter((player) => maxPrice === 0 || player.priceTenths <= maxPrice)
      .filter(
        (player) =>
          needle === "" ||
          fold(player.name).includes(needle) ||
          fold(player.club).includes(needle),
      )
      .map((player) => ({ player, run: runFor(player) }))
      .sort((left, right) => {
        if (TEXT_KEYS.has(sort)) {
          return (
            direction *
            -textValue(left.player, sort).localeCompare(
              textValue(right.player, sort),
            )
          );
        }
        return (
          direction *
          (sortValue(left.player, sort, left.run) -
            sortValue(right.player, sort, right.run))
        );
      });
  }, [pool, position, sort, descending, maxPrice, search]);

  // The whole remaining season, computed only for the card that is open. Doing
  // it for every row would be thirty-eight fixtures times six hundred players
  // to draw five of them.
  const seasonRun = useMemo(
    () =>
      pool && selected
        ? rateFixtureRun(
            pool.clubCodeByTeamId,
            pool.fixtures,
            selected.teamId,
            selected.position,
            SEASON_WINDOW,
          )
        : null,
    [pool, selected],
  );

  if (failed && (failed === "source_contract_failed" || !pool)) {
    return (
      <div className="pool-state" role="alert">
        <p>
          {failed === "source_contract_failed"
            ? "FPL answered, but not in the shape I expect. Rather than guess " +
              "at what changed, I am showing you nothing. This one is mine to " +
              "fix."
            : "FPL is not answering, and I have no earlier copy of the player " +
              "list to fall back on. Nothing has been substituted for it."}
        </p>
        {failed === "unreachable" ? (
          <button className="pool-retry" onClick={retry} type="button">
            Try again
          </button>
        ) : null}
      </div>
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

  const staleness = describeFreshness(pool.freshness);

  return (
    <>
      {staleness ? (
        <p className="pool-stale" role="status">
          {staleness}{" "}
          <button className="pool-retry" onClick={retry} type="button">
            Try again
          </button>
        </p>
      ) : null}

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
          Search
          <input
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Name or club"
            type="search"
            value={search}
          />
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
              {COLUMNS.map((column) => (
                <th
                  aria-sort={
                    sort === column.key
                      ? descending
                        ? "descending"
                        : "ascending"
                      : "none"
                  }
                  key={column.key}
                  scope="col"
                >
                  <button
                    className="pool-sort"
                    onClick={() => reorder(column.key)}
                    title={column.explains}
                    type="button"
                  >
                    {column.label}
                    <span aria-hidden="true" className="pool-arrow">
                      {sort === column.key
                        ? descending
                          ? "\u25be"
                          : "\u25b4"
                        : ""}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.slice(0, 200).map(({ player, run }) => (
              <tr key={player.code}>
                <th scope="row" translate="no">
                  <button
                    className="pool-open"
                    onClick={() => setSelected(player)}
                    type="button"
                  >
                    {player.name}
                  </button>
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
        <strong>Next 5</strong> rates the next five gameweeks against the
        opponents&rsquo; measured strength, at the venue each match is played.
        For a goalkeeper or defender it is what those opponents <em>score</em>,
        so below one is good. For a midfielder or forward it is what they{" "}
        <em>concede</em>, so above one is good. One blended difficulty number
        would hide that a hard fixture suppresses clean sheets while raising
        saves. Where a fraction appears, the rest of the run is against promoted
        clubs I have never measured; blanks count as no fixture and doubles
        count twice.
      </p>

      {selected ? (
        <PlayerDetail
          onClose={() => setSelected(null)}
          player={selected}
          run={
            shown.find(({ player }) => player.code === selected.code)?.run ??
            null
          }
          season={seasonRun}
        />
      ) : null}
    </>
  );
}
