import { useMemo, useState } from "react";

import { CeefaxShirt } from "./CeefaxShirt";
import { FixtureBreakdown } from "./FixtureBreakdown";
import { PlayerAvatar } from "./PlayerAvatar";
import { DEFCON_THRESHOLD, type AnalysisPlayer } from "../state/analysis-pool";
import { rateFixtureRun, type ScheduledFixture } from "../state/fixture-run";
import { kitForCode } from "../kit/team-kits";
import { comparePinned, type CompareRow } from "../state/scatter-compare";
import type { ScatterView } from "../state/scatter-view";

/**
 * Up to four players, side by side, for the comparison the chart sets up.
 *
 * The chart says two of them are near each other. This says whether that is the
 * same player twice or two different arguments that happen to land on the same
 * spot.
 *
 * Four because that is where the columns stop being readable, not because the
 * data runs out.
 */

const FIXTURE_WINDOW = 5;

export interface PinnedPlayersProps {
  players: readonly AnalysisPlayer[];
  pinned: readonly number[];
  clubCodeByTeamId: ReadonlyMap<number, number>;
  fixtures: readonly ScheduledFixture[];
  onUnpin: (code: number) => void;
  onClear: () => void;
  view: ScatterView;
}

export function PinnedPlayers({
  players,
  pinned,
  clubCodeByTeamId,
  fixtures,
  onUnpin,
  onClear,
  view,
}: PinnedPlayersProps) {
  const chosen = pinned
    .map((code) => players.find((player) => player.code === code))
    .filter((player): player is AnalysisPlayer => player !== undefined);

  const comparison = useMemo(
    () => comparePinned(chosen, players, view),
    [chosen, players, view],
  );
  const [breakdown, setBreakdown] = useState<AnalysisPlayer | null>(null);

  if (chosen.length === 0) {
    return (
      <div className="pinned-empty">
        <h3>Nobody pinned</h3>
        <p>
          Click a point to pin it. Four at a time, so you can put a shortlist
          beside each other rather than remembering the last one.
        </p>
      </div>
    );
  }

  return (
    <details className="scatter-controls pinned-panel">
      <summary className="scatter-controls-summary">
        <span>Compare players</span>
        <span className="scatter-controls-count mono">
          {chosen.length} of 4 pinned
        </span>
      </summary>
      <div className="scatter-controls-body">
        <div className="pinned-head">
          <button type="button" onClick={onClear} className="pinned-clear">
            Clear all
          </button>
        </div>

        <p className="pinned-order">
          Ordered by where they sit on the two axes you are plotting, best
          first. Rows are ordered by how far apart these players actually are,
          so the difference that decides it is at the top.
        </p>

        <div
          aria-label="Scrollable comparison of pinned players, side by side"
          className="squad-table-wrap pinned-scroller"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this comparison sideways.
          tabIndex={0}
        >
          <ul className="pinned-list">
            {comparison.players.map((player, column) => (
              <PinnedCard
                key={player.code}
                player={player}
                rows={comparison.rows}
                column={column}
                leading={column === 0 && comparison.players.length > 1}
                clubCodeByTeamId={clubCodeByTeamId}
                fixtures={fixtures}
                onFixtures={setBreakdown}
                onUnpin={onUnpin}
              />
            ))}
          </ul>
        </div>

        {breakdown ? (
          <FixtureBreakdown
            clubCodeByTeamId={clubCodeByTeamId}
            fixtures={fixtures}
            onClose={() => {
              setBreakdown(null);
            }}
            player={breakdown}
          />
        ) : null}
      </div>
    </details>
  );
}

function PinnedCard({
  player,
  rows,
  column,
  leading,
  clubCodeByTeamId,
  fixtures,
  onFixtures,
  onUnpin,
}: {
  player: AnalysisPlayer;
  rows: readonly CompareRow[];
  column: number;
  leading: boolean;
  clubCodeByTeamId: ReadonlyMap<number, number>;
  fixtures: readonly ScheduledFixture[];
  onFixtures: (player: AnalysisPlayer) => void;
  onUnpin: (code: number) => void;
}) {
  const run = rateFixtureRun(
    clubCodeByTeamId,
    fixtures,
    player.teamId,
    player.position,
    FIXTURE_WINDOW,
  );
  const threshold = DEFCON_THRESHOLD[player.position];
  const kit = kitForCode(clubCodeByTeamId.get(player.teamId));

  return (
    <li className={leading ? "pinned-card pinned-card-leading" : "pinned-card"}>
      {/* Always rendered, so the banner on the leader does not push its rows
          out of line with everyone else's. */}
      <p
        aria-hidden={leading ? undefined : "true"}
        className={
          leading ? "pinned-verdict" : "pinned-verdict pinned-verdict-blank"
        }
      >
        {leading ? "Best on these axes" : ""}
      </p>

      <div className="pinned-identity">
        <PlayerAvatar
          playerCode={player.code}
          name={player.name}
          club={player.club}
        />
        <div>
          <strong translate="no">{player.name}</strong>
          <span className="pinned-club">
            {/* The club is named right here, so the shirt stays silent. */}
            {kit ? (
              <CeefaxShirt kit={kit} label={null} className="pinned-shirt" />
            ) : null}
            <span translate="no">{player.club}</span> &middot; {player.position}
          </span>
          <span className="pinned-price">
            &pound;{(player.priceTenths / 10).toFixed(1)}m &middot;{" "}
            {player.ownership.toFixed(1)}% owned
          </span>
        </div>
        <button
          type="button"
          className="pinned-remove"
          onClick={() => onUnpin(player.code)}
        >
          Unpin<span className="visually-hidden"> {player.name}</span>
        </button>
      </div>

      <dl className="pinned-stats">
        {rows.map((row) => (
          <div
            className={row.leader === column ? "pinned-row-best" : undefined}
            key={row.id}
          >
            <dt title={row.explains}>{row.label}</dt>
            <dd>
              {row.formatted[column]}
              {row.leader === column ? (
                <span className="visually-hidden"> — best of those pinned</span>
              ) : null}
            </dd>
          </div>
        ))}
        <div>
          <dt
            title={`His next ${String(FIXTURE_WINDOW)} fixtures, rated on the route that matters for his position: what those opponents score if he defends, what they concede if he attacks. One is an average opponent, so above one is a soft run for an attacker and below one is a soft run for a defender.`}
          >
            Next {FIXTURE_WINDOW}
          </dt>
          <dd>
            {run.rating === null ? (
              <span
                className="pinned-unrated"
                title="No Premier League measurement for this club"
              >
                unrated
              </span>
            ) : (
              <button
                className="pinned-fixtures-open"
                onClick={() => {
                  onFixtures(player);
                }}
                title="Show every fixture and last season's match-by-match record"
                type="button"
              >
                {run.rating.toFixed(2)}
              </button>
            )}
          </dd>
        </div>
      </dl>

      {threshold === undefined ? (
        <p className="pinned-defcon pinned-defcon-none">
          No defensive-contribution route for a goalkeeper.
        </p>
      ) : (
        <p className="pinned-defcon">
          <span className="pinned-defcon-figure">
            {player.defensiveContributionPer90.toFixed(1)}
          </span>{" "}
          DefCon per 90 against a bar of {threshold}.{" "}
          {player.defconBarRatio !== null && player.defconBarRatio >= 1
            ? "He averages above it."
            : "He averages below it."}
        </p>
      )}

      {player.understat ? (
        <p className="pinned-understat">
          {(player.understat.penaltyShare * 100).toFixed(0)}% of his expected
          goals came from the spot, off {player.understat.shotsPer90.toFixed(1)}{" "}
          shots per 90.
        </p>
      ) : (
        <p className="pinned-understat pinned-unrated">
          No Understat match, so no shot breakdown.
        </p>
      )}
    </li>
  );
}
