import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { CeefaxShirt } from "./CeefaxShirt";
import { InfoMarker } from "./InfoMarker";
import type { AnalysisData } from "../state/analysis-pool";
import { money } from "../format";
import { fold } from "../state/fold";
import { kitForShortName } from "../kit/team-kits";
import {
  forgetDeclaredSquad,
  LAST_TEAM_KEY,
  readDeclaredSquad,
  saveDeclaredSquad,
  SQUAD_BUDGET_TENTHS,
  validateDeclaredSquad,
  type RosterPlayer,
  type SquadValidation,
} from "../state/declared-squad";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";

/**
 * Build the fifteen you are actually starting the season with.
 *
 * Before the first deadline FPL publishes nothing, so a Team ID alone can only
 * say who you are. Rather than stop at that, this takes your own fifteen,
 * checks it against the published rules, and — once it is legal — treats it as
 * locked in for gameweek one, which is what the season plan then solves from.
 *
 * It is the same mechanism as declaring a transfer FPL has not published yet:
 * your claim, kept in your own browser, labelled as yours rather than observed.
 */

const SLOTS = [
  { position: "GKP", count: 2, label: "Goalkeepers", offset: 0 },
  { position: "DEF", count: 5, label: "Defenders", offset: 2 },
  { position: "MID", count: 5, label: "Midfielders", offset: 7 },
  { position: "FWD", count: 3, label: "Forwards", offset: 12 },
] as const;

function pounds(tenths: number): string {
  return `${money.format(tenths / 10)}m`;
}

type SquadPlayer = RosterPlayer & {
  /** Expected points a match, absent where the planner holds no record. */
  points: number | undefined;
  startRate: number | undefined;
  /** False where those numbers are a prior for his role, not a record of him. */
  measured: boolean;
};

/** One place on the pitch: a shirt and a price, or an empty outline. */
function SquadSlot({
  player,
  position,
  onClear,
}: {
  player: SquadPlayer | null;
  position: string;
  onClear: () => void;
}) {
  if (!player) {
    return (
      <div className="squad-slot squad-slot-empty">
        <span className="squad-slot-position mono">{position}</span>
      </div>
    );
  }

  // A club with no kit drawn yet gets the name and the price but no shirt,
  // rather than another club's colours.
  const kit = kitForShortName(player.club);

  return (
    <div className="squad-slot">
      <button
        aria-label={`Remove ${player.name}`}
        className="squad-slot-clear"
        onClick={onClear}
        type="button"
      >
        ×
      </button>
      <span className="squad-slot-price mono">
        {pounds(player.priceTenths)}
      </span>
      {kit ? <CeefaxShirt kit={kit} label={null} /> : null}
      <span className="squad-slot-name">{player.name}</span>
      <span className="squad-slot-club mono">{player.club}</span>
    </div>
  );
}

/** Clubs as shirts, because a kit is recognised faster than a three-letter code. */
function ClubStrip({
  clubs,
  picked,
  onPick,
}: {
  clubs: readonly string[];
  picked: string;
  onPick: (club: string) => void;
}) {
  return (
    <ul className="squad-club-strip">
      {clubs.map((club) => {
        const kit = kitForShortName(club);
        return (
          <li key={club}>
            <button
              aria-pressed={picked === club}
              className={picked === club ? "is-picked" : undefined}
              onClick={() => {
                onPick(picked === club ? "ALL" : club);
              }}
              title={club}
              type="button"
            >
              {kit ? <CeefaxShirt kit={kit} label={null} /> : null}
              <span className="mono">{club}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

type SortKey =
  | "name"
  | "club"
  | "position"
  | "points"
  | "perMillion"
  | "startRate"
  | "priceTenths";

const MARKET_PAGE = 40;

/** Null where the planner holds no record, so it can be sorted last either way. */
function sortValue(player: SquadPlayer, key: SortKey): number | null {
  switch (key) {
    case "points":
      return player.points ?? null;
    case "perMillion":
      return player.points === undefined
        ? null
        : player.points / (player.priceTenths / 10);
    case "startRate":
      return player.startRate ?? null;
    default:
      return player.priceTenths;
  }
}

/** The list you pick from, filtered the way the official transfer page filters. */
function SquadMarket({
  players,
  picked,
  remainingTenths,
  onAdd,
}: {
  players: readonly SquadPlayer[];
  picked: ReadonlySet<number>;
  remainingTenths: number;
  onAdd: (player: SquadPlayer) => void;
}) {
  const [position, setPosition] = useState("ALL");
  const [club, setClub] = useState("ALL");
  const [maxTenths, setMaxTenths] = useState(155);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("points");
  const [descending, setDescending] = useState(true);
  const [shownCount, setShownCount] = useState(MARKET_PAGE);

  const clubs = useMemo(
    () => [...new Set(players.map((player) => player.club))].sort(),
    [players],
  );

  const shown = useMemo(() => {
    const needle = fold(search.trim());
    const direction = descending ? -1 : 1;
    return players
      .filter((player) => position === "ALL" || player.position === position)
      .filter((player) => club === "ALL" || player.club === club)
      .filter((player) => player.priceTenths <= maxTenths)
      .filter(
        (player) =>
          !needle ||
          fold(player.name).includes(needle) ||
          fold(player.club).includes(needle),
      )
      .sort((left, right) => {
        if (sort === "name" || sort === "club" || sort === "position") {
          return direction * -left[sort].localeCompare(right[sort]);
        }
        // Unrated players sort last either way: a missing number is not a low
        // one, and floating them to the top of an ascending sort would say so.
        const a = sortValue(left, sort);
        const b = sortValue(right, sort);
        if (a === null) return 1;
        if (b === null) return -1;
        return direction * (a - b) || right.priceTenths - left.priceTenths;
      });
  }, [players, position, club, maxTenths, search, sort, descending]);

  const toggle = (key: SortKey) => {
    setShownCount(MARKET_PAGE);
    if (key === sort) {
      setDescending(!descending);
      return;
    }
    setSort(key);
    // Text reads better A-Z; a number you are ranking on reads better best-first.
    setDescending(key !== "name" && key !== "club" && key !== "position");
  };

  return (
    <div className="squad-market">
      <div className="squad-market-filters">
        <select
          aria-label="Position"
          onChange={(changed) => {
            setPosition(changed.target.value);
            setShownCount(MARKET_PAGE);
          }}
          value={position}
        >
          <option value="ALL">All players</option>
          {SLOTS.map((slot) => (
            <option key={slot.position} value={slot.position}>
              {slot.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Club"
          onChange={(changed) => {
            setClub(changed.target.value);
            setShownCount(MARKET_PAGE);
          }}
          value={club}
        >
          <option value="ALL">All clubs</option>
          {clubs.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <select
          aria-label="Maximum price"
          onChange={(changed) => {
            setMaxTenths(Number(changed.target.value));
            setShownCount(MARKET_PAGE);
          }}
          value={maxTenths}
        >
          {[155, 130, 110, 90, 75, 60, 50, 45].map((tenths) => (
            <option key={tenths} value={tenths}>
              {pounds(tenths)}
            </option>
          ))}
        </select>
        <input
          aria-label="Search by name or club"
          onChange={(changed) => {
            setSearch(changed.target.value);
            setShownCount(MARKET_PAGE);
          }}
          autoComplete="off"
          name="player-search"
          placeholder="Search…"
          type="search"
          value={search}
        />
      </div>

      <ClubStrip
        clubs={clubs}
        onPick={(pickedClub) => {
          setClub(pickedClub);
          setShownCount(MARKET_PAGE);
        }}
        picked={club}
      />

      <p className="squad-market-count mono">
        Showing {Math.min(shownCount, shown.length)} of {shown.length} ·{" "}
        {pounds(remainingTenths)} left
      </p>

      <div
        aria-label="Scrollable player market"
        className="squad-market-scroll squad-table-wrap"
        role="region"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Desktop users need keyboard access to the bounded market scroll.
        tabIndex={0}
      >
        <div className="squad-market-headings mono">
          {(
            [
              ["name", "Player", "Sort by name"],
              ["club", "Club", "Sort by club"],
              ["position", "Pos", "Sort by position"],
              ["points", "Pts", "Sort by expected points"],
              ["perMillion", "£/pt", "Sort by points per million"],
              ["startRate", "Start", "Sort by how often he started"],
              ["priceTenths", "Price", "Sort by price"],
            ] as const
          ).map(([key, label, title]) => (
            <button
              className={sort === key ? "is-sorted" : undefined}
              key={key}
              onClick={() => {
                toggle(key);
              }}
              title={title}
              type="button"
            >
              {label}
              {sort === key ? (descending ? " ▾" : " ▴") : ""}
              {/* `aria-sort` belongs on a `columnheader`, and this market is a
                  CSS grid of buttons rather than a table, so axe rejected it as
                  a disallowed attribute. The arrow says which way it is sorted
                  to anyone who can see it; this says the same thing to anyone
                  who cannot. */}
              {sort === key ? (
                <span className="visually-hidden">
                  {descending ? ", sorted descending" : ", sorted ascending"}
                </span>
              ) : null}
            </button>
          ))}
          <span>Add</span>
        </div>

        <ol className="squad-market-list">
          {shown.slice(0, shownCount).map((player) => {
            const already = picked.has(player.id);
            const tooDear = player.priceTenths > remainingTenths;
            const perMillion =
              player.points === undefined
                ? null
                : (player.points / (player.priceTenths / 10)).toFixed(2);
            return (
              <li key={player.id}>
                <span className="squad-market-name">
                  {player.name}
                  {player.measured ? null : (
                    <abbr
                      className="squad-market-prior"
                      title="No Premier League record. These numbers are what players of his position and place in the club's pecking order do, not a measurement of him."
                    >
                      ~
                    </abbr>
                  )}
                </span>
                <span className="squad-market-club mono">{player.club}</span>
                <span className="squad-market-pos mono">{player.position}</span>
                <span className="squad-market-cell mono">
                  {player.points === undefined ? "—" : player.points.toFixed(2)}
                </span>
                <span className="squad-market-cell mono">
                  {perMillion ?? "—"}
                </span>
                <span className="squad-market-cell mono">
                  {player.startRate === undefined
                    ? "—"
                    : `${Math.round(player.startRate * 100)}%`}
                </span>
                <span className="squad-market-price mono">
                  {pounds(player.priceTenths)}
                </span>
                <button
                  aria-label={`Add ${player.name}`}
                  disabled={already || tooDear}
                  onClick={() => {
                    onAdd(player);
                  }}
                  title={
                    already
                      ? "Already in your fifteen"
                      : tooDear
                        ? "More than you have left"
                        : "Add"
                  }
                  type="button"
                >
                  +
                </button>
              </li>
            );
          })}
        </ol>
      </div>
      {shownCount < shown.length ? (
        <p className="squad-market-more">
          <button
            className="secondary-command"
            onClick={() => {
              setShownCount((current) => current + MARKET_PAGE);
            }}
            type="button"
          >
            Show more players
          </button>
        </p>
      ) : null}
    </div>
  );
}

function declaredSquadAnnouncement(
  chosenCount: number,
  saved: boolean,
  validation: SquadValidation | null,
  event: number,
): string {
  if (validation === null) {
    return `${String(chosenCount)} of 15 picked.`;
  }
  if (validation.valid) {
    return saved
      ? `Squad locked in for gameweek ${String(event)}.`
      : "Squad is legal and ready to lock in.";
  }
  return `Squad has ${String(validation.problems.length)} problem${validation.problems.length === 1 ? "" : "s"}.`;
}

export function DeclaredSquadBuilder({
  entryId,
  event,
  onDeclared,
}: {
  entryId: number;
  event: number;
  onDeclared?: () => void;
}) {
  const [pool, setPool] = useState<AnalysisData | null>(null);

  // The live FPL list, not the planning pool. The planner carries 144 players
  // it holds a record for; the game has around 570, and a manager declaring the
  // squad he actually picked must be able to name any of them.
  //
  // Imported dynamically: statically it drags the whole analysis pool into the
  // entry chunk, which put the bundle over its budget for a component most
  // visitors never open.
  useEffect(() => {
    const controller = new AbortController();
    void import("../state/analysis-pool")
      .then(({ fetchAnalysisPool }) => {
        // The import resolves after a tick, by which time the component may be
        // gone. Without this the fetch still leaves, which is a request nobody
        // will read and, in tests, one that lands in someone else's mock.
        if (controller.signal.aborted) return null;
        return fetchAnalysisPool(fetch, controller.signal);
      })
      .then((live) => {
        if (live && !controller.signal.aborted) setPool(live);
      })
      .catch(() => {
        // Aborted means the page moved on, which is not a failure to report.
      });
    return () => {
      controller.abort();
    };
  }, []);

  const players: SquadPlayer[] = useMemo(() => {
    const live = pool?.pool.players ?? [];
    if (live.length === 0) {
      return [...PLAYERS_BY_ELEMENT_ID.values()].map((player) => ({
        id: player.id,
        name: player.name,
        position: player.position,
        club: player.club,
        priceTenths: player.priceTenths,
        points: player.basePoints,
        startRate: player.startRate,
        measured: player.rated !== false,
      }));
    }
    return live.map((player) => {
      const rated = PLAYERS_BY_ELEMENT_ID.get(player.elementId);
      return {
        id: player.elementId,
        name: player.name,
        position: player.position,
        club: player.club,
        priceTenths: player.priceTenths,
        points: rated?.basePoints,
        startRate: rated?.startRate,
        // False where the numbers are a prior for his role rather than a
        // record of him. Shown, because a prior is not a measurement.
        measured: rated?.rated !== false,
      };
    });
  }, [pool]);

  const roster = useMemo(
    () => new Map(players.map((player) => [player.id, player])),
    [players],
  );

  const stored = useMemo(
    () => readDeclaredSquad(window.localStorage, entryId, event),
    [entryId, event],
  );
  const [picks, setPicks] = useState<string[]>(() =>
    stored
      ? stored.elementIds.map(String)
      : Array.from({ length: 15 }, () => ""),
  );
  const [saved, setSaved] = useState(stored !== null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const chosen = picks
    .map((pick) => Number(pick))
    .filter((elementId) => Number.isInteger(elementId) && elementId > 0);
  const complete = chosen.length === 15;
  const validation: SquadValidation | null = complete
    ? validateDeclaredSquad(chosen, roster, {
        enforceOpeningBudget: event === 1,
      })
    : null;

  const spentTenths = chosen.reduce(
    (total, elementId) => total + (roster.get(elementId)?.priceTenths ?? 0),
    0,
  );

  const setSlot = (index: number, value: string) => {
    setPicks((current) => {
      const next = [...current];
      next[index] = value;
      return next;
    });
    setSaved(false);
  };

  const lockIn = () => {
    if (!validation?.valid) return;
    try {
      saveDeclaredSquad(
        window.localStorage,
        entryId,
        event,
        chosen,
        roster,
        () => new Date(),
        { enforceOpeningBudget: event === 1 },
      );
      // Remembered so the plan page knows whose season to solve without the
      // team id having to be carried in every link.
      window.localStorage.setItem(LAST_TEAM_KEY, String(entryId));
      setSaved(true);
      setSaveError(null);
      // The season below is solved from this fifteen, so it has to be told.
      onDeclared?.();
    } catch (error) {
      // Storage can be full or blocked, and a rejected save must say so rather
      // than leaving a button that looks like it did nothing.
      setSaveError(
        error instanceof Error
          ? error.message
          : "The squad could not be saved.",
      );
    }
  };

  /** Drop a player into the first free slot of his own position. */
  const addPlayer = (player: SquadPlayer) => {
    const group = SLOTS.find((slot) => slot.position === player.position);
    if (!group) return;
    const free = Array.from(
      { length: group.count },
      (_u, o) => group.offset + o,
    ).find((index) => !picks[index]);
    if (free === undefined) return;
    setSlot(free, String(player.id));
  };

  const clear = () => {
    forgetDeclaredSquad(window.localStorage, entryId, event);
    setPicks(Array.from({ length: 15 }, () => ""));
    setSaved(false);
    onDeclared?.();
  };

  return (
    <section className="declared-squad" aria-labelledby="declared-squad-title">
      <div className="dossier-heading dossier-heading-compact">
        <div>
          <p className="eyebrow">Your claim, not FPL&rsquo;s record</p>
          <h2 id="declared-squad-title">Build your gameweek {event} fifteen</h2>
        </div>
        <span className="mono">
          {pounds(spentTenths)} of {pounds(SQUAD_BUDGET_TENTHS)}
        </span>
      </div>

      <p>
        Name your current fifteen and I&rsquo;ll plan from it. Stays in this
        browser.
        <InfoMarker label="why you have to name it">
          {event === 1
            ? "FPL keeps every squad private until the first deadline, so there is nothing public to read yet."
            : "FPL has not processed picks for this entry, so only you can state the current fifteen."}
        </InfoMarker>
      </p>

      <div className="squad-builder">
        <SquadMarket
          onAdd={addPlayer}
          picked={new Set(chosen)}
          players={players}
          remainingTenths={SQUAD_BUDGET_TENTHS - spentTenths}
        />

        <div className="squad-pitch">
          {SLOTS.map((group) => (
            <div className="squad-pitch-row" key={group.position}>
              {Array.from({ length: group.count }, (_unused, offset) => {
                const index = group.offset + offset;
                const elementId = Number(picks[index] ?? "");
                const player = roster.get(elementId) ?? null;
                return (
                  <SquadSlot
                    key={index}
                    onClear={() => {
                      setSlot(index, "");
                    }}
                    player={player}
                    position={group.position}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      <div className="declared-squad-actions">
        <button
          className="primary-command"
          disabled={validation?.valid !== true}
          onClick={lockIn}
          type="button"
        >
          Lock this in for gameweek {event}
        </button>
        <button className="secondary-command" onClick={clear} type="button">
          Clear
        </button>
      </div>

      {saveError === null ? null : (
        <p className="declared-squad-error" role="alert">
          {saveError}
        </p>
      )}

      <p aria-live="polite" className="visually-hidden" role="status">
        {declaredSquadAnnouncement(chosen.length, saved, validation, event)}
      </p>
      <div className="declared-squad-report">
        {validation === null ? (
          <p>
            {String(chosen.length)} of 15 picked. Nothing is stored, and no
            squad is assumed for you, until all fifteen obey the rules.
          </p>
        ) : validation.valid ? (
          <>
            <dl className="record-summary">
              <div>
                <dt>Spent</dt>
                <dd className="mono">
                  {pounds(validation.summary.spentTenths)}
                </dd>
              </div>
              <div>
                <dt>In the bank</dt>
                <dd className="mono">
                  {pounds(validation.summary.bankTenths)}
                </dd>
              </div>
              <div>
                <dt>Best eleven, on last season&rsquo;s record</dt>
                <dd className="mono">
                  {validation.summary.bestElevenPoints.toFixed(1)} pts a match
                </dd>
              </div>
              <div>
                <dt>Most from one club</dt>
                <dd className="mono">
                  {validation.summary.clubCounts[0]
                    ? `${String(validation.summary.clubCounts[0].count)} ${validation.summary.clubCounts[0].club}`
                    : "\u2014"}
                </dd>
              </div>
            </dl>
            <p>
              {saved ? (
                <>
                  Locked in. Your{" "}
                  <Link to={`/plan?team=${String(entryId)}`}>
                    gameweek {event} to 38 plan
                  </Link>{" "}
                  now starts from these fifteen.
                </>
              ) : (
                "This squad is legal. Lock it in to plan the season from it."
              )}
            </p>
            <p className="record-caveat">
              The eleven figure is last season&rsquo;s scoring record, before
              fixtures and before the captain. It is what is measurable today,
              not a projection of this season.
            </p>
          </>
        ) : (
          <>
            <p>I will not hold a squad that could not be entered:</p>
            <ul className="declared-squad-problems">
              {validation.problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
