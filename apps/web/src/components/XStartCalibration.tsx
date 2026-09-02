import { useState } from "react";

import { clubMarker } from "../kit/club-markers";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import { percent } from "../format";
import {
  XSTART_VALIDATION,
  type XStartClubValidation,
} from "../state/xstart-validation";

/**
 * How many of the eleven you would have started actually started, out of
 * eleven, one bar per club.
 *
 * A Brier score and a reliability table are the right evidence for a model
 * card; they are the wrong thing to hand someone deciding whether to trust
 * this week's team sheet. A 0-11 count is the same evidence read the way a
 * manager already reads a scoreline.
 *
 * Only one gameweek is frozen and scored today, so this draws one bar per
 * club rather than a line across gameweeks. The shape is built to take more
 * gameweeks the moment a second one is scored, without a rewrite: each score
 * is already keyed by club, so a future multi-gameweek artifact only adds
 * another entry per club rather than changing what this reads.
 */

function playerName(elementId: number): string {
  return (
    PLAYERS_BY_ELEMENT_ID.get(elementId)?.name ?? `Element ${String(elementId)}`
  );
}

function actualEleven(club: XStartClubValidation): string[] {
  const started = club.selected
    .filter((row) => row.started)
    .map((row) => playerName(row.elementId));
  const missed = club.missedStarters.map((row) => playerName(row.elementId));
  return [...started, ...missed];
}

function predictedEleven(club: XStartClubValidation): string[] {
  return club.selected.map((row) => playerName(row.elementId));
}

function ScorePopup({
  club,
  onClose,
}: {
  club: XStartClubValidation;
  onClose: () => void;
}) {
  return (
    <div
      aria-label={`${club.club} xStart check`}
      className="xstart-score-popup"
      role="dialog"
    >
      <div className="xstart-score-popup-columns">
        <button
          className="xstart-score-popup-close"
          onClick={onClose}
          type="button"
        >
          Close
        </button>
        <h4 className="xstart-score-popup-title" translate="no">
          {club.club} · {club.topElevenHits}/{club.actualStarters}
        </h4>
        <div>
          <h5>Predicted XI</h5>
          <ol className="mono">
            {predictedEleven(club).map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ol>
        </div>
        <div>
          <h5>Actual XI</h5>
          <ol className="mono">
            {actualEleven(club).map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}

export function XStartCalibration() {
  const validation = XSTART_VALIDATION;
  const [hiddenClubs, setHiddenClubs] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [opened, setOpened] = useState<XStartClubValidation | null>(null);

  const shown = validation.clubs.filter((club) => !hiddenClubs.has(club.club));
  const cumulative = [...shown].sort(
    (left, right) => right.topElevenHits - left.topElevenHits,
  );
  const perfect = 11;
  const axisMax = Math.max(
    perfect,
    ...cumulative.map((club) => club.topElevenHits),
  );
  const clippedMax = Math.min(axisMax, perfect);

  return (
    <section
      aria-labelledby="xstart-calibration-title"
      className="xstart-calibration"
    >
      <p className="eyebrow">
        GW{validation.event} · model {validation.modelVersion}
      </p>
      <h2 id="xstart-calibration-title">How close was the predicted XI?</h2>
      <p>
        Out of the eleven I would have started, how many actually started.
        Eleven is a perfect week; anything scored under it is where the model or
        the market missed.
      </p>

      <fieldset className="xstart-club-filter">
        <legend>Filter by club</legend>
        {validation.clubs.map((club) => (
          <label key={club.club}>
            <input
              checked={!hiddenClubs.has(club.club)}
              onChange={(event) => {
                setHiddenClubs((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.delete(club.club);
                  else next.add(club.club);
                  return next;
                });
              }}
              type="checkbox"
            />
            <span translate="no">{club.club}</span>
          </label>
        ))}
      </fieldset>

      <ol className="xstart-score-bars">
        {shown.map((club) => {
          const marker = clubMarker(club.club);
          const pct = (club.topElevenHits / 11) * 100;
          return (
            <li key={club.club}>
              <button
                className="xstart-score-bar-open"
                onClick={() => {
                  setOpened(club);
                }}
                type="button"
              >
                <span className="xstart-score-bar-label" translate="no">
                  {club.club}
                </span>
                <span className="xstart-score-bar-track">
                  <span
                    className="xstart-score-bar-fill"
                    style={{
                      width: `${String(pct)}%`,
                      background: marker?.fill,
                      borderColor: marker?.stroke ?? undefined,
                    }}
                  />
                </span>
                <span className="mono xstart-score-bar-value">
                  {club.topElevenHits}/11
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      <h3>Ranked, easiest to predict first</h3>
      <p>
        The same scores, sorted. A perfect week for every club would put all
        twenty at the dashed line.
      </p>
      <div className="xstart-rank-chart">
        <ol className="xstart-rank-bars">
          {cumulative.map((club) => {
            const marker = clubMarker(club.club);
            const pct = (club.topElevenHits / clippedMax) * 100;
            return (
              <li key={club.club}>
                <span className="xstart-rank-label" translate="no">
                  {club.club}
                </span>
                <span className="xstart-rank-track">
                  <span
                    className="xstart-rank-fill"
                    style={{
                      width: `${String(Math.min(100, pct))}%`,
                      background: marker?.fill,
                      borderColor: marker?.stroke ?? undefined,
                    }}
                  />
                </span>
                <span className="mono xstart-rank-value">
                  {club.topElevenHits}
                </span>
              </li>
            );
          })}
        </ol>
        {axisMax > clippedMax ? (
          <p className="mono xstart-rank-note">
            Perfect ({perfect}) is off this axis; every bar here is clipped to
            what clubs actually scored.
          </p>
        ) : (
          <p className="mono xstart-rank-note">
            The dashed line at {perfect} is a perfect week.
          </p>
        )}
      </div>

      <div className="xstart-reliability" role="list">
        {validation.reliability.map((band) => (
          <div
            className="xstart-reliability-row"
            key={band.label}
            role="listitem"
          >
            <span className="mono">{band.label}</span>
            <span className="xstart-reliability-track" aria-hidden="true">
              <span
                className="is-forecast"
                style={{ width: `${String(band.meanForecast * 100)}%` }}
              />
              <span
                className="is-actual"
                style={{ width: `${String(band.actualStartRate * 100)}%` }}
              />
            </span>
            <span className="mono">
              {percent.format(band.meanForecast)} /{" "}
              {percent.format(band.actualStartRate)}
            </span>
            <span className="mono">n={band.count}</span>
          </div>
        ))}
      </div>
      <p className="xstart-reliability-key">
        <span className="is-forecast" aria-hidden="true" /> Forecast
        <span className="is-actual" aria-hidden="true" /> Actual starts
      </p>

      {opened ? (
        <ScorePopup
          club={opened}
          onClose={() => {
            setOpened(null);
          }}
        />
      ) : null}
    </section>
  );
}
