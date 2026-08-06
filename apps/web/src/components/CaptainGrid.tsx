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
export type PickCell = [number, number, string] | null;

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
  /** Element id to `[web name, own club code]`. */
  players: Readonly<Record<string, [string, number | null]>>;
  /** Best return available on the shared shortlist, per gameweek. */
  ceiling: readonly (number | null)[];
  rows: readonly PickRow[];
}

export interface CaptainGridProps {
  seasons: readonly SeasonPicks[];
  names?: Readonly<Record<string, string>>;
  /** Marked so the eye finds this project's own row among the fourteen. */
  mine?: readonly string[];
}

/** Above this a haul is worth the ink; below it the cell stays quiet. */
const GOOD_HAUL = 10;

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
                    players={season.players}
                  />
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
  players,
}: {
  cell: PickCell;
  players: SeasonPicks["players"];
}) {
  if (cell === null) {
    return (
      <td className="captain-grid-cell captain-grid-empty">
        <span aria-hidden="true">·</span>
        <span className="visually-hidden">No pick</span>
      </td>
    );
  }
  const [element, points, opponent] = cell;
  const player = players[String(element)];
  const name = player?.[0] ?? `#${String(element)}`;
  const club = player?.[1] ?? null;
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
      <Shirt code={club} />
      <span className="captain-grid-name">{name}</span>
      <span className="captain-grid-against">{opponent || "—"}</span>
      <span className="captain-grid-points">{points}</span>
    </td>
  );
}

export default CaptainGrid;
