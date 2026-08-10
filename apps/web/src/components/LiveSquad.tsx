import { useEffect, useState } from "react";

import { oneDecimal } from "../format";
import { kitForShortName } from "../kit/team-kits";
import {
  LiveGameweekError,
  fetchLiveGameweek,
  type LiveGameweek,
  type LivePlayer,
} from "../state/live-gameweek";
import { projectionFor } from "../state/squad-projection";
import { CeefaxShirt } from "./CeefaxShirt";
import { InfoMarker } from "./InfoMarker";
import { PlayerDetail, type DetailPlayer } from "./PlayerDetail";
import { ScoreMarks, type ScoreLine } from "./ScoreMarks";
import type { PublicTeamPick } from "@fpl-andres/contracts";

/**
 * The fifteen, and what each of them actually did.
 *
 * Every other surface here says what is expected. This is the only one that
 * says what happened, and a projection nobody ever scores against is a
 * projection nobody can argue with.
 *
 * The yardstick is his own per-match projection against an average opponent,
 * not a per-gameweek one: the season artifact is forward-looking and drops a
 * gameweek once it is finished, so the number that priced this week is gone by
 * the time the week can be read. Stated on the page rather than fudged. The
 * fixture is therefore not in the comparison, which flatters a player who had
 * an easy week and is unfair to one who did not.
 */

/** How far past the projection a score has to be before it is a haul. */
const HAUL_MULTIPLE = 2;
/** And a floor, so a 0.4 projection is not hauled by a two-point cameo. */
const HAUL_FLOOR = 8;

/** The defensive-contribution bar, by position. A keeper has none. */
const DEFENSIVE_BAR: Record<string, number> = { DEF: 10, MID: 12, FWD: 12 };

type Band = "under" | "met" | "over" | "haul";

function bandFor(scored: number, expected: number): Band {
  if (scored >= HAUL_FLOOR && scored >= expected * HAUL_MULTIPLE) return "haul";
  if (scored > expected + 0.5) return "over";
  if (scored < expected - 0.5) return "under";
  return "met";
}

const BAND_WORDS: Record<Band, string> = {
  under: "below",
  met: "as projected",
  over: "above",
  haul: "haul",
};

function lineFor(live: LivePlayer, position: string, band: Band): ScoreLine {
  const bar = DEFENSIVE_BAR[position];
  return {
    goals: live.goals,
    assists: live.assists,
    cleanSheets: live.minutes >= 60 ? live.cleanSheets : 0,
    defensiveContribution: bar !== undefined && live.defensiveActions >= bar,
    bonus: live.bonus,
    haul: band === "haul",
  };
}

function PlayerCard({
  live,
  pick,
  onOpen,
}: {
  live: LivePlayer | undefined;
  pick: PublicTeamPick;
  onOpen: (pick: PublicTeamPick) => void;
}) {
  const identity = pick.identity;
  const name = identity?.webName ?? `Element ${String(pick.elementId)}`;
  const club = identity?.teamShortName ?? null;
  const kit = kitForShortName(club);
  const projection = identity ? projectionFor(identity.code) : null;
  const expected = projection?.expectedPoints ?? null;

  if (!live) {
    return (
      <li className="live-card is-unread">
        <p className="live-card-name">{name}</p>
        <p className="live-card-note mono">no score published</p>
      </li>
    );
  }

  const scored = live.totalPoints * Math.max(1, pick.multiplier);
  const band = expected === null ? "met" : bandFor(scored, expected);
  const marks = lineFor(live, identity?.positionCode ?? "MID", band);

  return (
    <li className={`live-card is-${band}`}>
      <button onClick={() => onOpen(pick)} type="button">
        <span className="live-card-head">
          {kit ? (
            <CeefaxShirt className="live-card-shirt" kit={kit} label={null} />
          ) : null}
          <span className="live-card-name">{name}</span>
          {pick.isCaptain ? (
            <span className="live-card-armband" title="Captain">
              C
            </span>
          ) : null}
          {pick.isViceCaptain ? (
            <span className="live-card-armband" title="Vice-captain">
              V
            </span>
          ) : null}
        </span>
        <span className="live-card-score">
          <b>{scored}</b>
          <span className="live-card-expected">
            {expected === null ? "—" : oneDecimal.format(expected)} projected
          </span>
        </span>
        <ScoreMarks line={marks} />
        <span className="live-card-band mono">
          {BAND_WORDS[band]}
          {expected === null
            ? ""
            : ` ${scored - expected >= 0 ? "+" : "−"}${oneDecimal.format(
                Math.abs(scored - expected),
              )}`}
        </span>
      </button>
    </li>
  );
}

interface Read {
  event: number;
  week: LiveGameweek | null;
  failed: string | null;
}

export function LiveSquad({
  event,
  picks,
}: {
  event: number;
  picks: readonly PublicTeamPick[];
}) {
  // The result carries the gameweek it describes rather than being cleared when
  // the gameweek changes. Clearing it would be a synchronous write inside the
  // effect, which the hooks rules refuse; a result for the week before is
  // simply not read.
  const [read, setRead] = useState<Read | null>(null);
  const [selected, setSelected] = useState<DetailPlayer | null>(null);
  const current = read?.event === event ? read : null;
  const live = current?.week ?? null;
  const failed = current?.failed ?? null;

  function open(pick: PublicTeamPick) {
    const identity = pick.identity;
    if (!identity) return;
    setSelected({
      code: identity.code,
      name: identity.webName,
      position: identity.positionCode,
      club: identity.teamShortName,
      priceTenths: identity.priceTenths,
    });
  }

  useEffect(() => {
    const abort = new AbortController();
    fetchLiveGameweek(event, undefined, abort.signal)
      .then((week) => {
        setRead({ event, week, failed: null });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setRead({
          event,
          week: null,
          failed:
            error instanceof LiveGameweekError
              ? error.message
              : "the gameweek's scores could not be read",
        });
      });
    return () => {
      abort.abort();
    };
  }, [event]);

  const ordered = [...picks].sort(
    (left, right) => left.squadPosition - right.squadPosition,
  );
  const eleven = ordered.slice(0, 11);
  const bench = ordered.slice(11);
  const total = live
    ? eleven.reduce((sum, pick) => {
        const row = live.players.get(pick.elementId);
        return sum + (row ? row.totalPoints * Math.max(1, pick.multiplier) : 0);
      }, 0)
    : null;

  return (
    <section aria-labelledby="live-squad" className="live-squad">
      <h2 id="live-squad">
        Gameweek {event}, as it went
        <InfoMarker label="the projected column">
          His own projection for an average match, from the published record.
          Not this fixture: the season artifact drops a gameweek once it is
          finished, so the number that priced this one is gone by the time the
          week can be read. A soft fixture therefore reads as a beat and a hard
          one as a miss.
        </InfoMarker>
      </h2>

      {failed ? (
        // Polite, not assertive. The panel is beside a form whose validation
        // owns the alert role, and a reader mid-correction should not be
        // interrupted by a scoreboard that could not be read.
        <p className="live-squad-failed" role="status">
          {failed}
        </p>
      ) : null}

      {total === null ? null : (
        <p className="live-squad-total mono">
          <b>{total}</b> points on the field
        </p>
      )}

      <ul className="live-eleven">
        {eleven.map((pick) => (
          <PlayerCard
            key={pick.elementId}
            live={live?.players.get(pick.elementId)}
            onOpen={open}
            pick={pick}
          />
        ))}
      </ul>

      <p className="live-bench-label mono">Bench</p>
      <ul className="live-bench">
        {bench.map((pick) => (
          <PlayerCard
            key={pick.elementId}
            live={live?.players.get(pick.elementId)}
            onOpen={open}
            pick={pick}
          />
        ))}
      </ul>

      {selected ? (
        <PlayerDetail
          onClose={() => {
            setSelected(null);
          }}
          player={selected}
        />
      ) : null}
    </section>
  );
}
