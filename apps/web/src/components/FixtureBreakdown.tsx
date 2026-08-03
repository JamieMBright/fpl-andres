import { useEffect, useRef } from "react";

import { rateFixtureRun, type ScheduledFixture } from "../state/fixture-run";
import type { AnalysisPlayer } from "../state/analysis-pool";

/**
 * Every fixture ahead, and what he did last season, in one place.
 *
 * The comparison shows one rated number for the next five. That number is a
 * mean, and a mean of five fixtures hides whether it is five even ties or two
 * gifts and three horrors. This is the working.
 */

const AHEAD = 12;

export interface FixtureBreakdownProps {
  clubCodeByTeamId: ReadonlyMap<number, number>;
  fixtures: readonly ScheduledFixture[];
  onClose: () => void;
  player: AnalysisPlayer;
}

export function FixtureBreakdown({
  clubCodeByTeamId,
  fixtures,
  onClose,
  player,
}: FixtureBreakdownProps) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
  }, []);

  const run = rateFixtureRun(
    clubCodeByTeamId,
    fixtures,
    player.teamId,
    player.position,
    AHEAD,
  );
  const defensive = player.position === "GKP" || player.position === "DEF";

  const ahead = fixtures
    .filter(
      (fixture) =>
        fixture.event !== null &&
        (fixture.team_h === player.teamId || fixture.team_a === player.teamId),
    )
    .sort((left, right) => (left.event ?? 0) - (right.event ?? 0))
    .slice(0, AHEAD);

  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/click-events-have-key-events -- The rule does not know `dialog` is interactive. Opened with `showModal`, Escape and the Close button both dismiss it; this only adds click-outside for a mouse.
    <dialog
      aria-labelledby="fixture-breakdown-name"
      className="player-detail"
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
      onClose={onClose}
      ref={dialog}
    >
      <div className="player-detail-card">
        <button className="player-detail-close" onClick={onClose} type="button">
          Close
        </button>

        <h2 id="fixture-breakdown-name" translate="no">
          {player.name}
        </h2>
        <p className="mono">
          {player.position} · <span translate="no">{player.club}</span>
        </p>

        <section className="fixture-breakdown">
          <h3>The next {AHEAD}</h3>
          {ahead.length === 0 ? (
            <p>FPL has published no fixtures for his club yet.</p>
          ) : (
            <ol className="fixture-breakdown-list mono">
              {ahead.map((fixture, index) => {
                const home = fixture.team_h === player.teamId;
                const opponent = home ? fixture.team_a : fixture.team_h;
                return (
                  <li key={`${String(fixture.event)}-${String(index)}`}>
                    <span>GW{fixture.event}</span>
                    <span>{home ? "H" : "A"}</span>
                    <span translate="no">
                      {clubCodeByTeamId.get(opponent) ?? "?"}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
          {run.rating === null ? (
            <p>
              None of these opponents has a measured record, so there is no
              rating rather than a guess.
            </p>
          ) : (
            <p>
              Rated {run.rating.toFixed(2)} on what these opponents{" "}
              {defensive ? "score" : "concede"} against an average side, over
              the {run.rated} of {run.fixtures} that could be rated. One is an
              average opponent.
            </p>
          )}
        </section>

        <section className="fixture-breakdown">
          <h3>Last season</h3>
          <dl className="fixture-breakdown-record mono">
            <div>
              <dt>Minutes</dt>
              <dd>{player.minutes}</dd>
            </div>
            <div>
              <dt>Points</dt>
              <dd>{player.totalPoints}</dd>
            </div>
            <div>
              <dt>Bonus</dt>
              <dd>{player.bonus}</dd>
            </div>
            <div>
              <dt>xG</dt>
              <dd>{player.expectedGoals.toFixed(2)}</dd>
            </div>
            <div>
              <dt>xA</dt>
              <dd>{player.expectedAssists.toFixed(2)}</dd>
            </div>
            <div>
              <dt>xGI</dt>
              <dd>{player.expectedGoalInvolvements.toFixed(2)}</dd>
            </div>
          </dl>
          <p>
            Totals across the whole of last season. A gameweek-by-gameweek line
            would need per-match history, which the analysis pool does not carry
            — it holds season aggregates, and inventing a shape from a total
            would be drawing a curve through one point.
          </p>
        </section>
      </div>
    </dialog>
  );
}
