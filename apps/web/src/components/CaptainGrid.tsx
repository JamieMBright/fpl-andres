import { useMemo, useState } from "react";

import { CeefaxShirt } from "./CeefaxShirt";
import { kitForCode } from "../kit/team-kits";
/**
 * Every armband, week by week, side by side.
 *
 * The charts above this settle whether one captaincy rule beats another by a
 * tenth of a point a week. They cannot show what the disagreement was *about*.
 * Two rules separated by 0.15 still differ on which player, in which week, and
 * that is the part somebody can check against a scoresheet and argue with.
 *
 * So: rows are methods, columns are gameweeks, and the whole grid scrolls
 * sideways with the labels pinned. A cell is a shirt, a surname, the opponent
 * and the haul — deliberately four things, because fourteen rows across
 * thirty-eight columns is five hundred cells on screen and anything more
 * becomes a wall.
 *
 * The opponent is cased to carry the venue: `ARS` at home, `ars` away, both in
 * a double gameweek. That casing arrives from the artifact already applied.
 * Nothing here may re-case it and the stylesheet pins `text-transform: none`.
 */

/** `[element id, points hauled, opponent]`, or null where nothing was picked. */
export type PickCell = readonly (string | number)[] | null;

/** The three values a cell carries, once narrowed out of the wire array. */
interface Pick {
  element: number;
  points: number;
  opponent: string;
}

function readPick(cell: PickCell): Pick | null {
  if (cell === null) return null;
  const [element, points, opponent] = cell;
  if (typeof element !== "number" || typeof points !== "number") return null;
  return {
    element,
    points,
    opponent: typeof opponent === "string" ? opponent : "",
  };
}

export interface PickRow {
  /** `method` ranks the whole pool; `thesis` is a captaincy rule. Both are
   *  needed because `components` is the name of one of each. */
  group: string;
  label: string;
  picks: readonly PickCell[];
}

export interface SeasonPicks {
  season: string;
  gameweeks: readonly number[];
  /** Stable FPL club code to three-letter short name. */
  clubs: Readonly<Record<string, string>>;
  /** Element id to `[web name, own club code]`, positional as published. */
  players: Readonly<Record<string, readonly (string | number | null)[]>>;
  /** Best return available on the shared shortlist, per gameweek. */
  ceiling: readonly (number | null)[];
  rows: readonly PickRow[];
  /**
   * Per gameweek, the numbers each policy read, keyed by element id. Values are
   * positional against `MATHS_FIELDS`. Absent on artifacts generated before the
   * arithmetic was published.
   */
  maths?: readonly Readonly<Record<string, readonly (number | null)[]>>[];
}

/** Matches `MATHS_FIELDS` in `backtesting/captain_picks.py`. */
const MATHS_FIELDS = [
  ["Projection", 0],
  ["Components only", 1],
  ["Last 5 average", 2],
  ["Chance he starts", 3],
  ["Ownership", 4],
  ["Ceiling", 5],
  ["Fixture ease", 6],
] as const;

export interface CaptainGridProps {
  seasons: readonly SeasonPicks[];
  names?: Readonly<Record<string, string>>;
  /** Marked so the eye finds this project's own row among the fourteen. */
  mine?: readonly string[];
}

/** Above this a haul is worth the ink; below it the cell stays quiet. */
const GOOD_HAUL = 10;

function playerName(
  players: SeasonPicks["players"],
  element: string | number,
): string {
  const entry = players[String(element)]?.[0];
  return typeof entry === "string" ? entry : `#${String(element)}`;
}

function playerClub(
  players: SeasonPicks["players"],
  element: string | number,
): number | null {
  const entry = players[String(element)]?.[1];
  return typeof entry === "number" ? entry : null;
}

function Shirt({ code }: { code: number | null }) {
  const kit = code === null ? null : kitForCode(code);
  // A club relegated before the current season has no kit in the map, and a
  // blank of the same size keeps the row from jumping.
  return kit ? (
    <CeefaxShirt className="grid-shirt" kit={kit} label={null} />
  ) : (
    <span className="grid-shirt" aria-hidden="true" />
  );
}

export function CaptainGrid({
  seasons,
  names = {},
  mine = [],
}: CaptainGridProps) {
  const scored = seasons.filter((season) => season.gameweeks.length > 0);
  const [selected, setSelected] = useState(
    () => scored[scored.length - 1]?.season ?? "",
  );
  const [inspected, setInspected] = useState<Inspected | null>(null);
  const season = useMemo(
    () => scored.find((entry) => entry.season === selected) ?? scored[0],
    [scored, selected],
  );

  if (season === undefined) {
    return (
      <p className="validation-verdict">
        This artifact predates the pick-by-pick record, so there is nothing to
        explore yet. It appears the next time{" "}
        <span className="mono">fpl_andres.cli.validate</span> runs.
      </p>
    );
  }

  return (
    <div className="captain-grid">
      <div className="captain-grid-seasons" role="group" aria-label="Season">
        {scored.map((entry) => (
          <button
            aria-pressed={entry.season === season.season}
            className="captain-grid-season"
            key={entry.season}
            onClick={() => {
              setSelected(entry.season);
              setInspected(null);
            }}
            type="button"
          >
            {entry.season}
          </button>
        ))}
      </div>

      <div
        aria-label="Scrollable gameweek-by-gameweek captaincy grid"
        className="squad-table-wrap captain-grid-scroller"
        role="region"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this grid horizontally.
        tabIndex={0}
      >
        <table className="captain-grid-table">
          <caption className="visually-hidden">
            Which player each captaincy method picked in every scored gameweek
            of {season.season}, with the opponent and the points he returned.
          </caption>
          <thead>
            <tr>
              <th scope="col">Method</th>
              {season.gameweeks.map((week, index) => (
                <th key={week} scope="col">
                  <span className="captain-grid-week">GW{week}</span>
                  <span className="captain-grid-ceiling">
                    {season.ceiling[index] ?? "—"}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {season.rows.map((row) => (
              <tr
                className={mine.includes(row.label) ? "captain-grid-mine" : ""}
                key={`${row.group}:${row.label}`}
              >
                <th scope="row">
                  {names[row.label] ?? row.label}
                  <span className="captain-grid-group">{row.group}</span>
                </th>
                {season.gameweeks.map((week, index) => (
                  <Cell
                    cell={row.picks[index] ?? null}
                    key={week}
                    label={names[row.label] ?? row.label}
                    onInspect={() => {
                      setInspected({ row: row.label, index });
                    }}
                    players={season.players}
                    week={week}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Explanation inspected={inspected} season={season} />
    </div>
  );
}

interface Inspected {
  row: string;
  index: number;
}

/**
 * Why that player, and what he was chosen over.
 *
 * A panel below the grid rather than a tooltip on the cell. Five hundred cells
 * inside a horizontal scroller is the worst possible place to position a
 * floating element, and a tooltip is unreachable by touch and awkward by
 * keyboard. This updates on hover and on focus, so a mouse gets the hover the
 * owner asked for and everyone else gets the same information by tabbing.
 */
function Explanation({
  inspected,
  season,
}: {
  inspected: Inspected | null;
  season: SeasonPicks;
}) {
  if (inspected === null) {
    return (
      <p className="captain-grid-readout captain-grid-readout-idle">
        Point at a pick — or tab to it — to see the numbers behind it, and what
        it was chosen over.
      </p>
    );
  }

  const row = season.rows.find((entry) => entry.label === inspected.row);
  const pick = readPick(row?.picks[inspected.index] ?? null);
  const week = season.gameweeks[inspected.index];
  const shortlist = season.maths?.[inspected.index];

  if (pick === null || week === undefined) {
    return (
      <p className="captain-grid-readout captain-grid-readout-idle">
        Nothing was picked in gameweek {String(week ?? "?")}.
      </p>
    );
  }
  if (shortlist === undefined) {
    return (
      <p className="captain-grid-readout captain-grid-readout-idle">
        This artifact predates the published arithmetic, so the reasoning is not
        available yet. It appears the next time the backtest runs.
      </p>
    );
  }

  const picked = pick.element;
  // Ranked by projection so the pick sits against what the projection preferred,
  // which is the comparison that makes a surprising choice legible.
  const ranked = Object.entries(shortlist).sort(
    (left, right) => (right[1][0] ?? 0) - (left[1][0] ?? 0),
  );

  return (
    <div className="captain-grid-readout">
      <p className="captain-grid-readout-title">
        Gameweek {week} — {inspected.row}
      </p>
      <div
        aria-label="Scrollable captaincy reasoning table"
        className="squad-table-wrap"
        role="region"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
        tabIndex={0}
      >
        <table>
          <thead>
            <tr>
              <th scope="col">Candidate</th>
              {MATHS_FIELDS.map(([title]) => (
                <th key={title} scope="col">
                  {title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ranked.map(([element, values]) => (
              <tr
                className={
                  Number(element) === picked ? "captain-grid-chosen" : ""
                }
                key={element}
              >
                <th scope="row">
                  {playerName(season.players, element)}
                  {Number(element) === picked ? (
                    <span className="captain-grid-chosen-mark"> chosen</span>
                  ) : null}
                </th>
                {MATHS_FIELDS.map(([title, position]) => (
                  <td className="mono" key={title}>
                    {values[position] === null || values[position] === undefined
                      ? "—"
                      : values[position].toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Cell({
  cell,
  label,
  onInspect,
  players,
  week,
}: {
  cell: PickCell;
  label: string;
  onInspect: () => void;
  players: SeasonPicks["players"];
  week: number;
}) {
  if (cell === null) {
    return (
      <td className="captain-grid-cell captain-grid-empty">
        <span aria-hidden="true">·</span>
        <span className="visually-hidden">No pick</span>
      </td>
    );
  }
  const pick = readPick(cell);
  if (pick === null) {
    return (
      <td className="captain-grid-cell captain-grid-empty">
        <span aria-hidden="true">·</span>
        <span className="visually-hidden">No pick</span>
      </td>
    );
  }
  const { element, points, opponent } = pick;
  const name = playerName(players, element);
  const club = playerClub(players, element);
  const blank = points <= 2;
  return (
    <td
      className={
        blank
          ? "captain-grid-cell captain-grid-blank"
          : points >= GOOD_HAUL
            ? "captain-grid-cell captain-grid-haul"
            : "captain-grid-cell"
      }
    >
      <button
        className="captain-grid-pick"
        onFocus={onInspect}
        onMouseEnter={onInspect}
        type="button"
      >
        <span className="visually-hidden">
          {`${label}, gameweek ${String(week)}: ${name} against ${opponent || "nobody"}, ${String(points)} points. Show the reasoning.`}
        </span>
        <Shirt code={club} />
        <span aria-hidden="true" className="captain-grid-name">
          {name}
        </span>
        <span aria-hidden="true" className="captain-grid-against">
          {opponent || "—"}
        </span>
        <span aria-hidden="true" className="captain-grid-points">
          {points}
        </span>
      </button>
    </td>
  );
}

export default CaptainGrid;
