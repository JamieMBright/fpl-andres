import squad from "../data/opening-squad.json";
import { useState } from "react";

import { CeefaxShirt } from "./CeefaxShirt";
import { money as sharedMoney } from "../format";
import { kitForShortName } from "../kit/team-kits";
import { saveDeclaredSquad } from "../state/declared-squad";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import {
  OPENING_SQUAD_SCHEMA_VERSION,
  requireArtifactVersion,
} from "../state/artifact-version";

requireArtifactVersion(
  "opening-squad.json",
  squad,
  OPENING_SQUAD_SCHEMA_VERSION,
);

interface Pick {
  code: number;
  name: string;
  position: string;
  club: string;
  priceTenths: number;
  record: number;
  adjusted: number;
  startRate: number;
  starter: boolean;
  run: number | null;
  ratedFixtures: number;
  fixtures: number;
}

interface OpeningSquad {
  generatedAt: string;
  basis: string;
  budgetTenths: number;
  spentTenths: number;
  expectedPoints: number;
  consideredPlayers: number;
  withoutRecord: number;
  unavailable: number;
  bitPart: number;
  startRateFloor: number;
  picks: Pick[];
}

const opening = squad as OpeningSquad;
const ORDER = ["GKP", "DEF", "MID", "FWD"];

function money(valueTenths: number): string {
  return `${sharedMoney.format(valueTenths / 10)}m`;
}

/**
 * The squad the evidence supports for gameweek one.
 *
 * The same for every manager, because between seasons every manager genuinely
 * has the same thing: a hundred million and no squad. A team ID says who you
 * are, not what you own, until the first deadline passes.
 */
export function OpeningSquad({ entryId }: { entryId?: number }) {
  const byPosition = ORDER.map((position) => ({
    position,
    picks: opening.picks.filter((pick) => pick.position === position),
  })).filter((group) => group.picks.length > 0);

  const [taken, setTaken] = useState(false);

  /** Drop the whole recommended fifteen into the builder above. */
  const adoptAll = () => {
    if (entryId === undefined) return;
    // The artifact carries FPL player codes, which are stable across seasons;
    // the declared squad is keyed by this season's element ids.
    const idByCode = new Map(
      [...PLAYERS_BY_ELEMENT_ID.values()].map((player) => [
        player.code,
        player.id,
      ]),
    );
    const elementIds = opening.picks
      .map((pick) => idByCode.get(pick.code))
      .filter((id): id is number => id !== undefined);
    if (elementIds.length !== opening.picks.length) return;
    saveDeclaredSquad(window.localStorage, entryId, 1, elementIds);
    setTaken(true);
    // The builder reads storage once, on mount, so it has to be remounted.
    window.location.reload();
  };

  return (
    // Folded away by default. It sits inside the reader's own squad section,
    // and a full fifteen they did not pick, open beside the one they did, reads
    // as the page arguing with itself.
    <details className="opening-squad-fold">
      <summary className="opening-squad-summary">
        <span>What I would buy today</span>
        <span className="mono">
          {money(opening.spentTenths)} of {money(opening.budgetTenths)}
        </span>
      </summary>
      <section className="opening-squad" aria-labelledby="opening-title">
        <div className="dossier-heading dossier-heading-compact">
          <div>
            <p className="eyebrow">Gameweek 1 · the evidence</p>
            <h2 id="opening-title">What I would buy today</h2>
          </div>
          <span className="mono">
            {money(opening.spentTenths)} of {money(opening.budgetTenths)}
          </span>
        </div>

        <p className="opening-basis">
          Fifteen players inside the real rules — one hundred million, two
          goalkeepers, five defenders, five midfielders, three forwards, no more
          than three from a club. Chosen to maximise the{" "}
          <em>starting eleven</em>, because that is all that scores, with a
          bench that can actually play so an absence does not cost you a
          transfer.
        </p>
        <p className="opening-basis mono">
          Best eleven: {opening.expectedPoints.toFixed(1)} points a gameweek,
          before the captain.
        </p>
        <p className="opening-basis">
          <strong>Started</strong> is how often he began a match in{" "}
          {opening.basis}. <strong>Next 5</strong> rates his next five opponents
          against one: for a keeper or defender it is what they score, so below
          one is good; for a midfielder or forward it is what they concede, so
          above one is good.
        </p>

        {entryId === undefined ? null : (
          <p className="opening-adopt">
            <button
              className="primary-command"
              disabled={taken}
              onClick={adoptAll}
              type="button"
            >
              {taken ? "Copied into your fifteen" : "Use these as my fifteen"}
            </button>
          </p>
        )}

        <div className="squad-pitch opening-pitch">
          {byPosition.map((group) => (
            <div className="squad-pitch-row" key={group.position}>
              {group.picks.map((pick) => {
                const kit = kitForShortName(pick.club);
                return (
                  <div
                    className={
                      pick.starter ? "squad-slot" : "squad-slot is-bench-slot"
                    }
                    key={pick.code}
                  >
                    <span className="squad-slot-price mono">
                      {money(pick.priceTenths)}
                    </span>
                    {kit ? <CeefaxShirt kit={kit} label={null} /> : null}
                    <span className="squad-slot-name" translate="no">
                      {pick.name}
                    </span>
                    <span className="squad-slot-club mono">
                      {pick.club} · {pick.record.toFixed(2)}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        <div
          aria-label="Scrollable recommended squad"
          className="squad-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
          tabIndex={0}
        >
          <table aria-label="Recommended opening squad">
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">Pos</th>
                <th scope="col">Club</th>
                <th scope="col">Price</th>
                <th scope="col">Pts / match</th>
                <th scope="col">Started</th>
                <th scope="col">Next 5</th>
              </tr>
            </thead>
            <tbody>
              {byPosition.flatMap((group) =>
                group.picks.map((pick) => (
                  <tr
                    key={pick.code}
                    className={pick.starter ? undefined : "is-bench"}
                  >
                    <th scope="row" translate="no">
                      {pick.name}
                      {pick.starter ? null : (
                        <span className="pool-partial"> bench</span>
                      )}
                    </th>
                    <td className="mono">{pick.position}</td>
                    <td className="mono" translate="no">
                      {pick.club}
                    </td>
                    <td className="mono">{money(pick.priceTenths)}</td>
                    <td className="mono">{pick.record.toFixed(2)}</td>
                    <td className="mono">
                      {Math.round(pick.startRate * 100)}%
                    </td>
                    <td className="mono">
                      {pick.run === null ? "—" : pick.run.toFixed(2)}
                      {pick.ratedFixtures < pick.fixtures ? (
                        <span className="pool-partial">
                          {" "}
                          {pick.ratedFixtures}/{pick.fixtures}
                        </span>
                      ) : null}
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>

        <h3>What this cannot see</h3>
        <ul className="opening-caveats">
          <li>
            <strong>
              Only {opening.consideredPlayers} of the game&rsquo;s players were
              eligible.
            </strong>{" "}
            {opening.withoutRecord} have no Premier League record,{" "}
            {opening.unavailable} are flagged injured or unavailable by FPL, and{" "}
            {opening.bitPart} have under a{" "}
            {Math.round(opening.startRateFloor * 100)}% chance of starting,
            judged on how the season <em>ended</em> rather than what it
            averaged. Some of those will be excellent this year. This is the
            best of what is <em>measurable</em>, which is not the same as the
            best.
          </li>
          <li>
            <strong>It knows a player started, not why.</strong> A stand-in for
            an injured first choice reads exactly like a man who won his place.
            That cuts both ways, and nothing here separates them.
          </li>
          <li>
            <strong>
              Last season&rsquo;s minutes are not this season&rsquo;s role.
            </strong>{" "}
            A summer signing, a new manager or a change of system moves a player
            off his record entirely, and none of that is modelled here.
          </li>
          <li>
            <strong>No form, because none exists.</strong> Once gameweeks are
            played the projection blends the record with recent scoring and this
            list will change.
          </li>
        </ul>
      </section>
    </details>
  );
}
