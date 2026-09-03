import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { InfoMarker } from "./InfoMarker";
import { PlayerDetail } from "./PlayerDetail";
import { classifyFetchFailure } from "../state/fetch-failure";
import { rateFixtureRun, type FixtureRun } from "../state/fixture-run";
import { fold } from "../state/fold";
import {
  fetchPlayerPool,
  PlayerPoolError,
  type PlayerPool,
  type PoolFailure,
  type PoolPlayer,
} from "../state/player-pool";
import { describeFreshness } from "../state/freshness";
import {
  DEFAULT_HORIZON,
  horizonPointsByCode,
  horizonsAvailable,
  type Horizon,
} from "../state/horizon-points";
import { retryingFetch } from "../state/retrying-fetch";
import { projectionThroughGameweek } from "../state/projection-meta";
import { projectionSeason } from "../state/squad-projection";
import { money as sharedMoney } from "../format";
import {
  readColumnOrder,
  readHiddenColumns,
  saveColumnOrder,
  saveHiddenColumns,
  toCsv,
} from "../state/player-pool-columns";

type SortKey =
  | "points"
  | "horizon"
  | "perMillion"
  | "price"
  | "run"
  | "returned"
  | "ceiling"
  | "apps"
  | "seasonPoints"
  | "lastGameweekPoints"
  | "expectedGoals"
  | "expectedAssists"
  | "expectedGoalInvolvements"
  | "expectedGoalsConceded"
  | "defensiveContribution"
  | "transfersInEvent"
  | "transfersOutEvent"
  | "priceChangeEvent"
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
    key: "lastGameweekPoints",
    label: "GW Pts",
    explains: "What he actually scored in the gameweek FPL last confirmed.",
  },
  {
    key: "seasonPoints",
    label: "Total Pts",
    explains: "What he has actually scored so far this season, live from FPL.",
  },
  {
    key: "points",
    label: "Pts / match",
    explains:
      "Expected FPL points in one match against an average opponent, from last season's per-90 rates and minutes. Four to six is a good starter.",
  },
  {
    key: "horizon",
    label: "xPts",
    explains:
      "Expected points added up over the next few gameweeks, against the real opponents. A double counts twice and a blank counts nothing, which is what a per-match figure cannot say.",
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
  {
    key: "expectedGoals",
    label: "xG",
    explains: "Expected goals so far this season, live from FPL.",
  },
  {
    key: "expectedAssists",
    label: "xA",
    explains: "Expected assists so far this season, live from FPL.",
  },
  {
    key: "expectedGoalInvolvements",
    label: "xGI",
    explains:
      "Expected goal involvements (xG plus xA) so far this season, live from FPL.",
  },
  {
    key: "expectedGoalsConceded",
    label: "xGC",
    explains:
      "Expected goals conceded while he was on the pitch so far this season, live from FPL.",
  },
  {
    key: "defensiveContribution",
    label: "DefCon",
    explains:
      "Defensive-contribution points scored so far this season, live from FPL.",
  },
  {
    key: "transfersInEvent",
    label: "Xfers in",
    explains: "Managers who bought him in the current gameweek, live from FPL.",
  },
  {
    key: "transfersOutEvent",
    label: "Xfers out",
    explains: "Managers who sold him in the current gameweek, live from FPL.",
  },
  {
    key: "priceChangeEvent",
    label: "Price \u0394",
    explains:
      "How his price has moved in tenths of a million since the current gameweek started.",
  },
];

/** Columns shown by default. Everything else exists but starts hidden, so a
 * reader who wants xG or transfer counts can add them without a table that
 * arrives twenty columns wide. */
const DEFAULT_HIDDEN_COLUMNS: SortKey[] = [
  "expectedGoals",
  "expectedAssists",
  "expectedGoalInvolvements",
  "expectedGoalsConceded",
  "defensiveContribution",
  "transfersInEvent",
  "transfersOutEvent",
  "priceChangeEvent",
];

const DEFAULT_COLUMN_ORDER = COLUMNS.map((column) => column.key);

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

function sortValue(
  player: PoolPlayer,
  key: SortKey,
  run: FixtureRun,
  horizon: ReadonlyMap<number, number>,
): number {
  if (key === "price") return player.priceTenths;
  if (key === "horizon") return horizon.get(player.code) ?? -Infinity;
  if (key === "perMillion") return player.perMillion ?? -1;
  if (key === "returned") return player.record?.returnRate ?? -1;
  if (key === "ceiling") return player.record?.ceiling ?? -1;
  if (key === "apps") return player.record?.appearances ?? -1;
  if (key === "seasonPoints") return player.seasonPoints;
  if (key === "lastGameweekPoints") return player.lastGameweekPoints ?? -1;
  if (key === "expectedGoals") return player.expectedGoals ?? -1;
  if (key === "expectedAssists") return player.expectedAssists ?? -1;
  if (key === "expectedGoalInvolvements")
    return player.expectedGoalInvolvements ?? -1;
  if (key === "expectedGoalsConceded")
    return player.expectedGoalsConceded ?? -1;
  if (key === "defensiveContribution")
    return player.defensiveContribution ?? -1;
  if (key === "transfersInEvent") return player.transfersInEvent ?? -1;
  if (key === "transfersOutEvent") return player.transfersOutEvent ?? -1;
  if (key === "priceChangeEvent") return player.priceChangeEvent ?? -Infinity;
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

/**
 * The text a cell shows, shared between the table and the CSV export so the
 * download reads the same numbers the screen does — a dash for a missing
 * record, not an empty cell a spreadsheet reads as zero.
 */
function cellText(
  player: PoolPlayer,
  key: SortKey,
  run: FixtureRun,
  horizon: ReadonlyMap<number, number>,
): string {
  switch (key) {
    case "name":
      return player.name;
    case "position":
      return player.position;
    case "club":
      return player.club;
    case "price":
      return money(player.priceTenths);
    case "lastGameweekPoints":
      return player.lastGameweekPoints?.toString() ?? "\u2014";
    case "seasonPoints":
      return player.seasonPoints.toString();
    case "points":
      return player.record ? player.record.expectedPoints.toFixed(2) : "\u2014";
    case "horizon":
      return horizon.get(player.code)?.toFixed(1) ?? "\u2014";
    case "perMillion":
      return player.perMillion?.toFixed(2) ?? "\u2014";
    case "returned":
      return player.record?.returnRate === null ||
        player.record?.returnRate === undefined
        ? "\u2014"
        : `${Math.round(player.record.returnRate * 100)}%`;
    case "ceiling":
      return player.record?.ceiling?.toString() ?? "\u2014";
    case "apps":
      return player.record?.appearances?.toString() ?? "\u2014";
    case "run":
      return run.rating === null ? "\u2014" : run.rating.toFixed(2);
    case "expectedGoals":
      return player.expectedGoals?.toFixed(2) ?? "\u2014";
    case "expectedAssists":
      return player.expectedAssists?.toFixed(2) ?? "\u2014";
    case "expectedGoalInvolvements":
      return player.expectedGoalInvolvements?.toFixed(2) ?? "\u2014";
    case "expectedGoalsConceded":
      return player.expectedGoalsConceded?.toFixed(2) ?? "\u2014";
    case "defensiveContribution":
      return player.defensiveContribution?.toString() ?? "\u2014";
    case "transfersInEvent":
      return player.transfersInEvent?.toString() ?? "\u2014";
    case "transfersOutEvent":
      return player.transfersOutEvent?.toString() ?? "\u2014";
    case "priceChangeEvent":
      return player.priceChangeEvent === null
        ? "\u2014"
        : money(player.priceChangeEvent);
  }
}

function cellNumber(
  player: PoolPlayer,
  key: SortKey,
  horizon: ReadonlyMap<number, number>,
): number | null {
  switch (key) {
    case "lastGameweekPoints":
      return player.lastGameweekPoints;
    case "seasonPoints":
      return player.seasonPoints;
    case "points":
      return player.record?.expectedPoints ?? null;
    case "horizon":
      return horizon.get(player.code) ?? null;
    case "perMillion":
      return player.perMillion;
    case "returned":
      return player.record?.returnRate ?? null;
    case "ceiling":
      return player.record?.ceiling ?? null;
    case "apps":
      return player.record?.appearances ?? null;
    case "expectedGoals":
      return player.expectedGoals;
    case "expectedAssists":
      return player.expectedAssists;
    case "expectedGoalInvolvements":
      return player.expectedGoalInvolvements;
    case "expectedGoalsConceded":
      return player.expectedGoalsConceded;
    case "defensiveContribution":
      return player.defensiveContribution;
    case "transfersInEvent":
      return player.transfersInEvent;
    case "transfersOutEvent":
      return player.transfersOutEvent;
    case "priceChangeEvent":
      return player.priceChangeEvent;
    case "club":
    case "name":
    case "position":
    case "price":
    case "run":
      return null;
  }
}

type CellHighlight = "best" | "worst";
type CellHighlights = ReadonlyMap<SortKey, ReadonlyMap<number, CellHighlight>>;

const HIGHLIGHT_COUNT = 5;
const LOWER_IS_BETTER = new Set<SortKey>([
  "expectedGoalsConceded",
  "transfersOutEvent",
]);

function cellHighlights(
  pool: PlayerPool,
  horizon: ReadonlyMap<number, number>,
): CellHighlights {
  const result = new Map<SortKey, ReadonlyMap<number, CellHighlight>>();
  for (const { key } of COLUMNS) {
    const ranked = pool.players.flatMap((player) => {
      const value = cellNumber(player, key, horizon);
      return value === null ? [] : [{ code: player.code, value }];
    });
    if (
      ranked.length < 2 ||
      ranked.every((row) => row.value === ranked[0]?.value)
    ) {
      continue;
    }
    const direction = LOWER_IS_BETTER.has(key) ? 1 : -1;
    ranked.sort(
      (left, right) =>
        direction * (left.value - right.value) || left.code - right.code,
    );
    const count = Math.min(HIGHLIGHT_COUNT, Math.floor(ranked.length / 2));
    const highlights = new Map<number, CellHighlight>();
    for (const row of ranked.slice(0, count)) highlights.set(row.code, "best");
    for (const row of ranked.slice(-count)) highlights.set(row.code, "worst");
    result.set(key, highlights);
  }
  return result;
}

/** How many rows to draw at once. "All" is every match still worth a ranking. */
const ROW_LIMITS = [25, 50, 75, 100] as const;
const SHOW_ALL = "all";
type RowLimit = (typeof ROW_LIMITS)[number] | typeof SHOW_ALL;

function updateTableScrollState(region: HTMLDivElement): void {
  const scrollable = region.scrollWidth > region.clientWidth + 1;
  const atEnd =
    !scrollable ||
    region.scrollLeft + region.clientWidth >= region.scrollWidth - 1;
  region.dataset.scrollable = String(scrollable);
  region.dataset.scrollEnd = String(atEnd);
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
  const [horizonWeeks, setHorizonWeeks] = useState<Horizon>(DEFAULT_HORIZON);
  const [descending, setDescending] = useState(true);
  const [maxPrice, setMaxPrice] = useState(0);
  const [maxOwned, setMaxOwned] = useState(0);
  const [minMinutes, setMinMinutes] = useState(0);
  const [search, setSearch] = useState("");
  const [rowLimit, setRowLimit] = useState<RowLimit>(25);
  const [selected, setSelected] = useState<PoolPlayer | null>(null);
  const [columnOrder, setColumnOrder] = useState<SortKey[]>(() =>
    readColumnOrder(window.localStorage, DEFAULT_COLUMN_ORDER),
  );
  const [hiddenColumns, setHiddenColumns] = useState<ReadonlySet<string>>(() =>
    readHiddenColumns(window.localStorage, DEFAULT_HIDDEN_COLUMNS),
  );
  const [customizingColumns, setCustomizingColumns] = useState(false);
  const tableRegionRef = useRef<HTMLDivElement>(null);
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

  const orderedColumns = useMemo(
    () =>
      columnOrder.flatMap((key) => {
        const column = COLUMNS.find((candidate) => candidate.key === key);
        return column ? [column] : [];
      }),
    [columnOrder],
  );
  const shownColumns = useMemo(
    () => orderedColumns.filter((column) => !hiddenColumns.has(column.key)),
    [orderedColumns, hiddenColumns],
  );
  const columnsChanged = useMemo(
    () =>
      columnOrder.length !== DEFAULT_COLUMN_ORDER.length ||
      columnOrder.some((key, index) => key !== DEFAULT_COLUMN_ORDER[index]) ||
      hiddenColumns.size !== DEFAULT_HIDDEN_COLUMNS.length ||
      DEFAULT_HIDDEN_COLUMNS.some((key) => !hiddenColumns.has(key)),
    [columnOrder, hiddenColumns],
  );

  const toggleColumn = (key: SortKey) => {
    setHiddenColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      saveHiddenColumns(window.localStorage, next);
      return next;
    });
  };

  const moveColumn = (key: SortKey, direction: -1 | 1) => {
    setColumnOrder((current) => {
      const index = current.indexOf(key);
      const target = index + direction;
      if (index === -1 || target < 0 || target >= current.length) {
        return current;
      }
      const next = [...current];
      const [removed] = next.splice(index, 1);
      if (removed === undefined) return current;
      next.splice(target, 0, removed);
      saveColumnOrder(window.localStorage, next);
      return next;
    });
  };

  const resetColumns = () => {
    const hidden = new Set<SortKey>(DEFAULT_HIDDEN_COLUMNS);
    setColumnOrder([...DEFAULT_COLUMN_ORDER]);
    setHiddenColumns(hidden);
    saveColumnOrder(window.localStorage, DEFAULT_COLUMN_ORDER);
    saveHiddenColumns(window.localStorage, hidden);
  };

  useEffect(() => {
    const region = tableRegionRef.current;
    if (!region) return;
    const updateScrollState = () => updateTableScrollState(region);
    updateScrollState();
    window.addEventListener("resize", updateScrollState);
    return () => {
      window.removeEventListener("resize", updateScrollState);
    };
  }, [pool, shownColumns]);

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

  const horizon = useMemo(
    () => horizonPointsByCode(horizonWeeks),
    [horizonWeeks],
  );
  const highlights = useMemo(
    () => (pool ? cellHighlights(pool, horizon) : new Map()),
    [pool, horizon],
  );
  const available = useMemo(() => horizonsAvailable(), []);

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
          maxOwned === 0 ||
          player.ownedPercent === null ||
          player.ownedPercent <= maxOwned,
      )
      .filter(
        (player) =>
          minMinutes === 0 ||
          player.minutesPlayed === null ||
          player.minutesPlayed >= minMinutes,
      )
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
          (sortValue(left.player, sort, left.run, horizon) -
            sortValue(right.player, sort, right.run, horizon))
        );
      });
  }, [
    pool,
    position,
    sort,
    descending,
    maxPrice,
    maxOwned,
    minMinutes,
    search,
    horizon,
  ]);

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
        2026/27 prices against {projectionSeason} returns. Sort by{" "}
        <strong>per £1m</strong> to see what a player costs per point today.
        Fixture projections through GW{projectionThroughGameweek}.
        <InfoMarker label="where these numbers come from">
          Prices are the ones FPL has published for 2026/27. The points figure
          is what each player actually returned per match in {projectionSeason},
          rebuilt from every scoring route rather than taken from a summary
          column.
        </InfoMarker>
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
        <label>
          xPts over
          <select
            onChange={(event) =>
              setHorizonWeeks(Number(event.target.value) as Horizon)
            }
            value={horizonWeeks}
          >
            {available.map((weeks) => (
              <option key={weeks} value={weeks}>
                {weeks} GW
              </option>
            ))}
          </select>
        </label>
        <label>
          Max ownership
          <input
            aria-label="Max ownership"
            autoComplete="off"
            inputMode="decimal"
            max={100}
            min={0}
            name="max-ownership"
            onChange={(event) => setMaxOwned(Number(event.target.value))}
            step={0.5}
            title="Enter 0 for any ownership"
            type="number"
            value={maxOwned}
          />
          <span aria-hidden="true" className="pool-filter-any">
            0 = Any
          </span>
        </label>
        <label>
          Min minutes
          <input
            aria-label="Min minutes"
            autoComplete="off"
            inputMode="numeric"
            max={3420}
            min={0}
            name="min-minutes"
            onChange={(event) => setMinMinutes(Number(event.target.value))}
            step={1}
            title="Enter 0 for any minutes"
            type="number"
            value={minMinutes}
          />
          <span aria-hidden="true" className="pool-filter-any">
            0 = Any
          </span>
        </label>
        <label>
          Show
          <select
            onChange={(event) =>
              setRowLimit(
                event.target.value === SHOW_ALL
                  ? SHOW_ALL
                  : (Number(event.target.value) as RowLimit),
              )
            }
            value={rowLimit}
          >
            {ROW_LIMITS.map((limit) => (
              <option key={limit} value={limit}>
                {limit}
              </option>
            ))}
            <option value={SHOW_ALL}>All</option>
          </select>
        </label>
        <div className="pool-control-actions">
          <button
            aria-expanded={customizingColumns}
            aria-label={customizingColumns ? "Done" : "Columns"}
            className="pool-customize-toggle"
            data-columns-changed={columnsChanged}
            onClick={() => setCustomizingColumns((was) => !was)}
            type="button"
          >
            {customizingColumns ? "Done" : "Columns"}
            {columnsChanged ? (
              <span aria-hidden="true" className="pool-customize-status">
                Changed
              </span>
            ) : null}
          </button>
          <button
            className="pool-csv-download"
            onClick={() => {
              const header = shownColumns.map((column) => column.label);
              const rows = shown.map(({ player, run }) =>
                shownColumns.map((column) =>
                  cellText(player, column.key, run, horizon),
                ),
              );
              const blob = new Blob([toCsv(header, rows)], {
                type: "text/csv;charset=utf-8",
              });
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = "fpl-andres-players.csv";
              link.click();
              URL.revokeObjectURL(url);
            }}
            type="button"
          >
            Download CSV
          </button>
        </div>
      </div>

      {customizingColumns ? (
        <fieldset className="pool-column-customize">
          <legend>
            Show, hide and reorder columns. Changes are remembered on this
            device.
          </legend>
          <button
            className="pool-columns-reset"
            disabled={!columnsChanged}
            onClick={resetColumns}
            type="button"
          >
            Reset columns
          </button>
          <ol>
            {orderedColumns.map((column, index) => (
              <li key={column.key}>
                <label>
                  <input
                    checked={!hiddenColumns.has(column.key)}
                    onChange={() => toggleColumn(column.key)}
                    type="checkbox"
                  />
                  {column.label}
                </label>
                <span className="pool-column-move">
                  <button
                    aria-label={`Move ${column.label} up`}
                    disabled={index === 0}
                    onClick={() => moveColumn(column.key, -1)}
                    type="button"
                  >
                    {"\u2191"}
                  </button>
                  <button
                    aria-label={`Move ${column.label} down`}
                    disabled={index === orderedColumns.length - 1}
                    onClick={() => moveColumn(column.key, 1)}
                    type="button"
                  >
                    {"\u2193"}
                  </button>
                </span>
              </li>
            ))}
          </ol>
        </fieldset>
      ) : null}

      <p className="pool-count mono">
        {shown.length} shown · {unknown} in the game with no record
      </p>

      <p className="pool-horizon-note">
        Sort on <strong>xPts{horizonWeeks}</strong> to find the transfer worth
        making.
        <InfoMarker label="what xPts over a horizon is">
          <span className="info-marker-line">
            Every gameweek in the horizon added up, against the real opponents:
            a double counts twice and a blank counts nothing.
          </span>
          <span className="info-marker-line">
            Not discounted. The solver weights later weeks down because it will
            get another transfer before them; you are asking what the next{" "}
            {horizonWeeks} gameweeks are worth, which is a different question.
          </span>
          <span className="info-marker-line">
            One gameweek is who to captain. Five and beyond is who to buy: a
            striker with one soft fixture and then the top three outranks a
            steadier one on Saturday and is the worse buy by gameweek five.
          </span>
          <span className="info-marker-line">
            The per-match rates are based on {projectionSeason}. The horizon
            applies them to the current season&rsquo;s real fixtures; live
            minutes change the xStart read separately.
          </span>
        </InfoMarker>
      </p>

      <div
        aria-label="Scrollable player list"
        className="squad-table-wrap pool-table-wrap"
        data-scroll-end="true"
        data-scrollable="false"
        onScroll={(event) => updateTableScrollState(event.currentTarget)}
        ref={tableRegionRef}
        role="region"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
        tabIndex={0}
      >
        <span className="visually-hidden">
          Scroll horizontally to read every shown column.
        </span>
        <table aria-label="2026/27 players against last season's record">
          <thead>
            <tr>
              {shownColumns.map((column) => (
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
                    {column.key === "horizon"
                      ? `${column.label}${String(horizonWeeks)}`
                      : column.label}
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
            {(rowLimit === SHOW_ALL ? shown : shown.slice(0, rowLimit)).map(
              ({ player, run }) => (
                <tr key={player.code}>
                  {shownColumns.map((column) =>
                    column.key === "name" ? (
                      <th key={column.key} scope="row" translate="no">
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
                    ) : (
                      <td
                        className={`mono${(() => {
                          const highlight = highlights
                            .get(column.key)
                            ?.get(player.code);
                          return highlight ? ` pool-stat-${highlight}` : "";
                        })()}`}
                        data-stat-key={column.key}
                        key={column.key}
                        title={
                          highlights.get(column.key)?.get(player.code) ===
                          "best"
                            ? "Top 5 in this column"
                            : highlights.get(column.key)?.get(player.code) ===
                                "worst"
                              ? "Bottom 5 in this column"
                              : undefined
                        }
                        translate={column.key === "club" ? "no" : undefined}
                      >
                        {column.key === "run" ? (
                          <FixtureRunCell
                            position={player.position}
                            run={run}
                          />
                        ) : (
                          cellText(player, column.key, run, horizon)
                        )}
                      </td>
                    ),
                  )}
                </tr>
              ),
            )}
          </tbody>
        </table>
        <span aria-hidden="true" className="pool-scroll-hint">
          More columns
        </span>
      </div>

      {rowLimit !== SHOW_ALL && shown.length > rowLimit ? (
        <p className="pool-truncated">
          Showing the first {rowLimit} of {shown.length}. Narrow the filters or
          choose a bigger "Show" to see more.
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
