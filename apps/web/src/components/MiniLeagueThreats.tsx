import { useEffect, useState } from "react";

import { kitForShortName } from "../kit/team-kits";
import {
  MiniLeagueError,
  fetchMiniLeague,
  overlookedIn,
  threatsIn,
  RIVAL_LIMIT,
  type LeagueExposure,
  type MiniLeague,
} from "../state/mini-league";
import { projectionFor } from "../state/squad-projection";
import { CeefaxShirt } from "./CeefaxShirt";
import { InfoMarker } from "./InfoMarker";
import { BarChart, type Bar } from "./MethodChart";

/**
 * Who you are racing, and what they are holding that you are not.
 *
 * A projection says what a player is worth. It cannot say what he is worth
 * *to you*, which in a league of a dozen named squads is a different number:
 * a name nine of them start is a threat whether or not he is a good buy, and
 * a name none of them own is a lever whether or not he is the best available.
 *
 * Read post-deadline only, because FPL keeps a squad private until its
 * gameweek starts. Before then this says so rather than showing an empty board
 * that reads as "nobody owns anybody".
 */

/** Above this share of the league, matching a name is defence rather than choice. */
const TEMPLATE_SHARE = 0.6;

/** How many names each board shows. Beyond a dozen the bars stop being read. */
const BOARD_SIZE = 10;

/** What the full FPL list can tell us about an element id. */
interface Named {
  name: string;
  club: string;
  code: number;
}

type Roll = ReadonlyMap<number, Named>;

function nameOf(elementId: number, roll: Roll): string {
  return roll.get(elementId)?.name ?? `Element ${String(elementId)}`;
}

function barsFor(
  rows: readonly LeagueExposure[],
  roll: Roll,
  sign: 1 | -1,
): Bar[] {
  return rows.slice(0, BOARD_SIZE).map((row) => ({
    label: nameOf(row.elementId, roll),
    value: sign * row.effective,
    shown: `${String(Math.round(row.effective * 100))}%`,
  }));
}

function Roster({ league, roll }: { league: MiniLeague; roll: Roll }) {
  return (
    <ol className="league-roster">
      {league.rivals.map((rival) => (
        <li key={rival.entryId}>
          <span className="league-roster-rank mono">{rival.rank}</span>
          <span className="league-roster-team">{rival.entryName}</span>
          <span className="league-roster-captain">
            C: {rival.captain === null ? "\u2014" : nameOf(rival.captain, roll)}
          </span>
          <span className="league-roster-points mono">
            {rival.totalPoints.toLocaleString("en-GB")}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Shirt({ club }: { club: string | null }) {
  const kit = kitForShortName(club);
  return kit ? (
    <CeefaxShirt className="league-shirt" kit={kit} label={null} />
  ) : null;
}

interface Read {
  leagueId: number;
  event: number;
  league: MiniLeague | null;
  failed: string | null;
}

export function MiniLeagueThreats({
  leagueId,
  event,
  mine,
}: {
  leagueId: number;
  event: number;
  /** The element ids the reader started this gameweek. */
  mine: readonly number[];
}) {
  const [read, setRead] = useState<Read | null>(null);
  const [roll, setRoll] = useState<Roll>(new Map());

  const current =
    read?.leagueId === leagueId && read.event === event ? read : null;
  const league = current?.league ?? null;
  const failed = current?.failed ?? null;

  // The full FPL list, so a rival's player can be named. Imported lazily for
  // the same reason the squad builder does it: statically it drags the whole
  // pool into a chunk most readers never open.
  useEffect(() => {
    const abort = new AbortController();
    void import("../state/analysis-pool")
      .then(({ fetchAnalysisPool }) =>
        abort.signal.aborted ? null : fetchAnalysisPool(fetch, abort.signal),
      )
      .then((pool) => {
        if (!pool || abort.signal.aborted) return;
        setRoll(
          new Map(
            pool.pool.players.map((player) => [
              player.elementId,
              { name: player.name, club: player.club, code: player.code },
            ]),
          ),
        );
      })
      .catch(() => {
        // A player without a name is still a share. The board falls back to
        // the element id rather than refusing to draw.
      });
    return () => {
      abort.abort();
    };
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    fetchMiniLeague(leagueId, event, mine, undefined, abort.signal)
      .then((answer) => {
        setRead({ leagueId, event, league: answer, failed: null });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setRead({
          leagueId,
          event,
          league: null,
          failed:
            error instanceof MiniLeagueError
              ? error.message
              : "the league could not be read",
        });
      });
    return () => {
      abort.abort();
    };
    // `mine` is a fresh array each render; the league it belongs to is what
    // decides whether this has to be asked again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leagueId, event]);

  if (failed !== null) {
    return (
      <section aria-labelledby="mini-league" className="mini-league">
        <h2 id="mini-league">Your league</h2>
        <p className="mini-league-failed" role="status">
          {failed}
        </p>
      </section>
    );
  }

  if (league === null) {
    return (
      <section aria-labelledby="mini-league" className="mini-league">
        <h2 id="mini-league">Your league</h2>
        <p className="mono">Reading the squads you are racing…</p>
      </section>
    );
  }

  const threats = threatsIn(league);
  const overlooked = overlookedIn(league);
  const template = threats.filter((row) => row.effective >= TEMPLATE_SHARE);
  const worst = threats[0];

  return (
    <section aria-labelledby="mini-league" className="mini-league">
      <h2 id="mini-league">
        {league.leagueName}
        <InfoMarker label="what these shares mean">
          Counted over the {league.rivals.length} squads read from the top of
          the table, not the whole league, and over the eleven each of them
          fielded rather than their fifteen: a rival&rsquo;s bench threatens
          nothing. A captain counts twice, because he scores twice. Gameweek{" "}
          {league.event}, which is the last one FPL has made public.
        </InfoMarker>
      </h2>

      <p className="mini-league-lede">
        {league.rivals.length} squads read
        {league.rivals.length === RIVAL_LIMIT ? ", the top of the table" : ""}
        {league.unavailable.length > 0
          ? `. ${String(league.unavailable.length)} could not be read and are not in any share below`
          : ""}
        .{" "}
        {worst
          ? `The name that hurts most is ${nameOf(worst.elementId, roll)}, on ${String(Math.round(worst.effective * 100))}%.`
          : "You start everything this league starts."}
      </p>

      {template.length > 0 ? (
        <p className="mini-league-verdict">
          {template.length === 1
            ? "One name is"
            : `${String(template.length)} names are`}{" "}
          held by more than {Math.round(TEMPLATE_SHARE * 100)}% of the squads
          you are racing. Matching those is defence, not ambition: it does not
          win you the league, it stops one afternoon losing it.
        </p>
      ) : null}

      {threats.length > 0 ? (
        <div className="mini-league-board">
          <h3>What they hold and you do not</h3>
          <BarChart
            bars={barsFor(threats, roll, 1)}
            caption="Share of the squads you are racing that started him, captaincy counted twice"
            unit="share of the league"
          />
          <ul className="mini-league-names">
            {threats.slice(0, BOARD_SIZE).map((row) => {
              const known = roll.get(row.elementId);
              return (
                <li key={row.elementId}>
                  <Shirt club={known?.club ?? null} />
                  <span>{nameOf(row.elementId, roll)}</span>
                  <span className="mono">
                    {known
                      ? (projectionFor(known.code)?.expectedPoints.toFixed(2) ??
                        "\u2014")
                      : "\u2014"}{" "}
                    xPts
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {overlooked.length > 0 ? (
        <div className="mini-league-board">
          <h3>What you hold and they overlook</h3>
          <BarChart
            bars={barsFor(overlooked, roll, -1)}
            caption="The same share for the players you started. A short bar is a lever nobody else is pulling"
            unit="share of the league"
          />
        </div>
      ) : null}

      <details className="mini-league-roster">
        <summary>
          <span className="mono">The squads this was read from</span>
        </summary>
        <Roster league={league} roll={roll} />
      </details>
    </section>
  );
}
