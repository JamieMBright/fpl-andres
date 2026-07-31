import { useEffect, useMemo, useState } from "react";

import {
  fetchPlayerPool,
  type PlayerPool,
  type PoolPlayer,
} from "../state/player-pool";
import { projectionSeason } from "../state/squad-projection";

type SortKey = "points" | "perMillion" | "price";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "points", label: "Points per match" },
  { key: "perMillion", label: "Points per £1m" },
  { key: "price", label: "Price" },
];

const moneyFormatter = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function money(valueTenths: number): string {
  return `${moneyFormatter.format(valueTenths / 10)}m`;
}

function sortValue(player: PoolPlayer, key: SortKey): number {
  if (key === "price") return player.priceTenths;
  if (key === "perMillion") return player.perMillion ?? -1;
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
  const [failed, setFailed] = useState(false);
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
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  const shown = useMemo(() => {
    if (!pool) return [];
    return pool.players
      .filter((player) => position === "ALL" || player.position === position)
      .filter((player) => maxPrice === 0 || player.priceTenths <= maxPrice)
      .slice()
      .sort((left, right) => sortValue(right, sort) - sortValue(left, sort));
  }, [pool, position, sort, maxPrice]);

  if (failed) {
    return (
      <p className="pool-state" role="alert">
        FPL did not answer, so there is no player list to show. Nothing has been
        substituted for it. Reload to try again.
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
            </tr>
          </thead>
          <tbody>
            {shown.slice(0, 200).map((player) => (
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
    </>
  );
}
