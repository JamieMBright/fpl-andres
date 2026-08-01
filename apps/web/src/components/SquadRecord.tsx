import type { PublicTeamPick } from "@fpl-andres/contracts";

import { money as sharedMoney } from "../format";
import {
  projectionSeason,
  squadProjection,
  type PlayerProjection,
} from "../state/squad-projection";

function money(valueTenths: number | null): string {
  return valueTenths === null
    ? "—"
    : `${sharedMoney.format(valueTenths / 10)}m`;
}

function percentage(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

/** Points per pound, at the price the player finished the season on. */
function perMillion(player: PlayerProjection): string {
  if (!player.priceTenths) return "—";
  return (player.expectedPoints / (player.priceTenths / 10)).toFixed(2);
}

/**
 * What the players in this squad actually did, last season.
 *
 * Presented as a record rather than a projection. Between seasons there is no
 * fixture, no form and no confirmed squad, so a number labelled "expected
 * points for Gameweek 1" would be dressing up last year's evidence as this
 * year's forecast.
 */
export function SquadRecord({ picks }: { picks: readonly PublicTeamPick[] }) {
  const members = picks.map((pick) => ({
    name: pick.identity?.webName ?? `FPL element ${pick.elementId}`,
    code: pick.identity?.code,
  }));
  const { covered, missing, strongestEleven } = squadProjection(members);

  return (
    <section className="squad-record" aria-labelledby="squad-record-title">
      <div className="dossier-heading dossier-heading-compact">
        <div>
          <p className="eyebrow">Decision input · measured</p>
          <h2 id="squad-record-title">What these players did last season</h2>
        </div>
        <span className="mono">{projectionSeason}</span>
      </div>

      <p className="squad-record-basis">
        Points per match against an average opponent, reconstructed from all
        fourteen scoring routes across {projectionSeason}. No fixture is applied
        and no form is measured, because neither exists yet.
      </p>

      {strongestEleven === null ? null : (
        <p className="squad-record-total mono">
          Strongest eleven: {strongestEleven.toFixed(1)} points per gameweek
        </p>
      )}

      {covered.length === 0 ? (
        <p className="squad-record-empty">
          I hold no Premier League record for anyone in this squad.
        </p>
      ) : (
        <div
          aria-label="Scrollable squad record"
          className="squad-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
          tabIndex={0}
        >
          <table aria-label="Last season record by player">
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">Pos</th>
                <th scope="col">Price</th>
                <th scope="col">Pts / match</th>
                <th scope="col">Per £1m</th>
                <th scope="col">Floor</th>
                <th scope="col">Ceiling</th>
                <th scope="col">Returned</th>
                <th scope="col">Blanked</th>
                <th scope="col">Apps</th>
              </tr>
            </thead>
            <tbody>
              {covered.map((player) => (
                <tr key={player.code}>
                  <th scope="row" translate="no">
                    {player.name}
                  </th>
                  <td className="mono">{player.position}</td>
                  <td className="mono">{money(player.priceTenths)}</td>
                  <td className="mono">{player.expectedPoints.toFixed(2)}</td>
                  <td className="mono">{perMillion(player)}</td>
                  <td className="mono">{player.floor ?? "—"}</td>
                  <td className="mono">{player.ceiling ?? "—"}</td>
                  <td className="mono">{percentage(player.returnRate)}</td>
                  <td className="mono">{percentage(player.blankRate)}</td>
                  <td className="mono">{player.appearances}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {missing.length > 0 ? (
        <p className="squad-record-missing">
          <strong>No record for {missing.length}:</strong>{" "}
          <span translate="no">{missing.join(", ")}</span>. Either they played
          no Premier League minutes in {projectionSeason}, or they played too
          few for anything I say about them to be worth reading. I would rather
          leave the row empty than fill it with a positional average.
        </p>
      ) : null}

      <p className="squad-record-footnote">
        &ldquo;Returned&rdquo; is a gameweek of five points or more.
        &ldquo;Blanked&rdquo; is two or fewer. Both count only the gameweeks the
        player appeared in, so a fit player who returns a third of the time is
        not flattered by the weeks he was injured.
      </p>
    </section>
  );
}
