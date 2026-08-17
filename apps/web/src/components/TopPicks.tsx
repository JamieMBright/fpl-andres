import { useId, useState } from "react";

import { money, oneDecimal } from "../format";
import { kitForShortName } from "../kit/team-kits";
import { DEFAULT_HORIZON, horizonPointsByCode } from "../state/horizon-points";
import {
  EVENT_INDEX,
  SEASON_EVENTS,
  SEASON_PLAYERS,
  fixtureAtEvent,
  type EventFixture,
  type EventRoutes,
  type SolverPlayer,
} from "../state/season-solver";
import { CeefaxShirt } from "./CeefaxShirt";
import { InfoMarker } from "./InfoMarker";
import { PlayerAvatar } from "./PlayerAvatar";
import { PlayerDetail, type DetailPlayer } from "./PlayerDetail";
import { RankMedal } from "./RankMedal";

/**
 * The best five-gameweek value in each position, and why.
 *
 * Four cards rather than a table because this is the first thing a reader sees
 * and a table asks him to do the ranking himself. The number under each photo
 * is the only claim being made, so it is the thing that opens: hover or focus
 * it, together with the displayed price, exposes the ranking inputs. The five
 * fixtures behind it come apart into opponent, venue, difficulty and the
 * routes that paid.
 *
 * One panel at a time, and it spans the whole row rather than the card that
 * opened it. A panel the width of a card cannot hold five fixtures without
 * breaking "COV" over two lines, and four of them stacked would cover each
 * other.
 *
 * A pick is a pick, not a recommendation to buy: a player already in the squad
 * is still the best player in his position, and this has no idea what the
 * squad is.
 */

const POSITIONS = [
  { code: "GKP", label: "Goalkeeper" },
  { code: "DEF", label: "Defender" },
  { code: "MID", label: "Midfielder" },
  { code: "FWD", label: "Forward" },
] as const;

/** Ordered so the routes that decide a pick are read before the ones that trim it. */
const ROUTE_LABELS: readonly (readonly [keyof EventRoutes, string])[] = [
  ["appearance", "appearance"],
  ["attacking", "goals and assists"],
  ["cleanSheet", "clean sheet"],
  ["saves", "saves"],
  ["defensiveContribution", "defensive contribution"],
  ["bonus", "bonus"],
  ["conceding", "goals conceded"],
  ["yellowCards", "yellow cards"],
  ["redCards", "red cards"],
  ["ownGoals", "own goals"],
  ["penaltiesMissed", "penalties missed"],
];

/** Below this a route is rounding, and eight rounding routes bury the two that matter. */
const WORTH_NAMING = 0.05;

const START_INDEX = EVENT_INDEX.get(SEASON_EVENTS[0] ?? -1) ?? null;

interface Pick {
  label: string;
  player: SolverPlayer;
  points: number;
  fixtures: readonly EventFixture[];
  rank: 1 | 2 | 3;
}

/** "COV (H)" as published, which is the only place the venue is recorded. */
function readOpponent(entry: string): { club: string; home: boolean } {
  const [club = entry, venue = ""] = entry.split(" ");
  return { club, home: venue.startsWith("(H") };
}

function picksFor(
  position: string,
  label: string,
  totals: ReadonlyMap<number, number>,
): Pick[] {
  if (START_INDEX === null) return [];
  return SEASON_PLAYERS.filter((player) => player.position === position)
    .flatMap((player) => {
      const points = totals.get(player.code);
      return points === undefined
        ? []
        : [
            {
              player,
              points,
              value: points / (player.priceTenths / 10),
            },
          ];
    })
    .sort(
      (left, right) =>
        right.value - left.value || left.player.code - right.player.code,
    )
    .slice(0, 3)
    .map(({ player, points }, index) => {
      const fixtures: EventFixture[] = [];
      if (index === 0) {
        for (let ahead = 0; ahead < DEFAULT_HORIZON; ahead += 1) {
          const fixture = fixtureAtEvent(player, START_INDEX + ahead);
          if (fixture) fixtures.push(fixture);
        }
      }
      return {
        label,
        player,
        points,
        fixtures,
        rank: (index + 1) as 1 | 2 | 3,
      };
    });
}

function Opponent({ entry }: { entry: string }) {
  const { club, home } = readOpponent(entry);
  const kit = kitForShortName(club);
  return (
    <span className="top-pick-opponent">
      {kit ? (
        <CeefaxShirt className="top-pick-shirt" kit={kit} label={null} />
      ) : null}
      <span translate="no">{club}</span>
      <span className="top-pick-venue">{home ? "home" : "away"}</span>
    </span>
  );
}

function FixtureColumn({ fixture }: { fixture: EventFixture }) {
  const named = ROUTE_LABELS.filter(
    ([key]) => Math.abs(fixture.routes[key]) >= WORTH_NAMING,
  );
  return (
    <li className="top-pick-fixture">
      <p className="top-pick-fixture-head">
        <span className="top-pick-gw">GW{fixture.event}</span>
        <b>{oneDecimal.format(fixture.points)}</b>
      </p>
      <p className="top-pick-fixture-against">
        {fixture.opponents.length === 0 ? (
          <span className="top-pick-blank">no fixture</span>
        ) : (
          fixture.opponents.map((entry) => (
            <Opponent entry={entry} key={entry} />
          ))
        )}
      </p>
      {fixture.difficulty === null ? null : (
        <p className="top-pick-difficulty">
          difficulty {oneDecimal.format(fixture.difficulty)}
        </p>
      )}
      {named.length === 0 ? null : (
        <ul className="top-pick-routes">
          {named.map(([key, label]) => (
            <li key={key}>
              <span>{label}</span>
              <b>{oneDecimal.format(fixture.routes[key])}</b>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function TopPickColumn({
  onOpen,
  onProfile,
  openCode,
  panelId,
  picks,
}: {
  onOpen: (code: number | null) => void;
  onProfile: (player: DetailPlayer) => void;
  openCode: number | null;
  panelId: string;
  picks: readonly Pick[];
}) {
  const winner = picks[0];
  if (!winner) return null;
  const { player } = winner;
  const open = openCode === player.code;
  return (
    <li className="top-pick-column" data-position={player.position}>
      <p className="top-pick-role">{winner.label}</p>
      <article className="top-pick-hero">
        <span className="top-pick-frame">
          <PlayerAvatar
            club={player.club}
            name={player.name}
            playerCode={player.code}
          />
        </span>
        <div className="top-pick-hero-detail">
          <RankMedal rank={1} />
          <p className="top-pick-name">
            <button onClick={() => onProfile(player)} type="button">
              {player.name}
            </button>
          </p>
          <p className="top-pick-club">
            <span translate="no">{player.club}</span>
            <span>{money.format(player.priceTenths / 10)}</span>
          </p>
          <p className="top-pick-metric">
            <button
              aria-controls={panelId}
              aria-expanded={open}
              className="top-pick-points"
              onClick={() => onOpen(player.code)}
              onFocus={() => onOpen(player.code)}
              onKeyDown={(event) => {
                if (event.key === "Escape") onOpen(null);
              }}
              onMouseEnter={() => onOpen(player.code)}
              type="button"
            >
              <b>{oneDecimal.format(winner.points)}</b>
              <span>xPts5</span>
            </button>
            <InfoMarker label="xPts5">
              Expected points over the next five gameweeks. A double counts
              twice and a blank counts nothing.
            </InfoMarker>
          </p>
        </div>
      </article>
      <ol className="top-pick-runners">
        {picks.slice(1).map((pick) => (
          <li key={pick.player.code}>
            <RankMedal rank={pick.rank} />
            <button
              className="top-pick-runner-name"
              onClick={() => onProfile(pick.player)}
              type="button"
            >
              {pick.player.name}
            </button>
            <span className="top-pick-runner-club" translate="no">
              {pick.player.club}
            </span>
            <span className="top-pick-runner-points mono">
              <b>{oneDecimal.format(pick.points)}</b>
              <span>xPts5</span>
            </span>
          </li>
        ))}
      </ol>
    </li>
  );
}

export function TopPicks() {
  const panelId = useId();
  const [selected, setSelected] = useState<DetailPlayer | null>(null);
  const [openCode, setOpenCode] = useState<number | null>(null);
  const totals = horizonPointsByCode(DEFAULT_HORIZON);
  const columns = POSITIONS.map(({ code, label }) =>
    picksFor(code, label, totals),
  ).filter((picks) => picks.length > 0);
  const picks = columns.flat();
  const shown = picks.find((pick) => pick.player.code === openCode) ?? null;

  return (
    <section aria-labelledby="top-picks" className="top-picks">
      <h2 id="top-picks">Top players for the next five gameweeks</h2>
      <p>
        The top three in every position by xPts5/£m. The leader gets the full
        fixture breakdown; every name opens the player profile.
      </p>
      {picks.length === 0 ? (
        <p className="mono">
          Fewer than five gameweeks remain, so there is no five-gameweek
          projection to rank anyone on.
        </p>
      ) : (
        <div
          className="top-pick-board"
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget))
              setOpenCode(null);
          }}
          onMouseLeave={() => setOpenCode(null)}
        >
          <ul className="top-pick-grid">
            {columns.map((column) => (
              <TopPickColumn
                key={column[0]?.player.position}
                onOpen={setOpenCode}
                onProfile={(player) => setSelected(player)}
                openCode={openCode}
                panelId={panelId}
                picks={column}
              />
            ))}
          </ul>
          <div className="top-pick-panel" hidden={shown === null} id={panelId}>
            {shown ? (
              <>
                <p className="top-pick-panel-head">
                  {shown.player.name} — where the{" "}
                  {oneDecimal.format(shown.points)} comes from
                </p>
                <ul>
                  {shown.fixtures.map((fixture) => (
                    <FixtureColumn fixture={fixture} key={fixture.event} />
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        </div>
      )}
      {selected ? (
        <PlayerDetail onClose={() => setSelected(null)} player={selected} />
      ) : null}
    </section>
  );
}
