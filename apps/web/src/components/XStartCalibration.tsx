import { useState } from "react";

import { InfoMarker } from "./InfoMarker";
import { clubMarker } from "../kit/club-markers";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import {
  XSTART_VALIDATION,
  latestXStartEvent,
  type XStartClubValidation,
  type XStartValidationEvent,
} from "../state/xstart-validation";

function playerName(elementId: number): string {
  return (
    PLAYERS_BY_ELEMENT_ID.get(elementId)?.name ?? `Element ${String(elementId)}`
  );
}

function ClubDetail({ club }: { club: XStartClubValidation }) {
  const misses = club.selected
    .filter((row) => !row.started)
    .map((row) => playerName(row.elementId));
  const omitted = club.missedStarters.map((row) => playerName(row.elementId));
  return (
    <>
      <span className="info-marker-line">
        {club.count} predictions · {club.actualStarters} actual starters ·{" "}
        {club.topElevenHits}/11 hits.
      </span>
      <span className="info-marker-line">
        Predicted but missed: {misses.join(", ") || "none"}.
      </span>
      <span className="info-marker-line">
        Starters left out: {omitted.join(", ") || "none"}.
      </span>
    </>
  );
}

function clubAt(event: XStartValidationEvent, club: string) {
  return event.clubs.find((row) => row.club === club);
}

function cumulativeHits(club: string, throughEvent: number): number {
  return XSTART_VALIDATION.events
    .filter((event) => event.event <= throughEvent)
    .reduce(
      (total, event) => total + (clubAt(event, club)?.topElevenHits ?? 0),
      0,
    );
}

export function XStartCalibration() {
  const latest = latestXStartEvent(XSTART_VALIDATION);
  const [selectedEvent, setSelectedEvent] = useState(latest.event);
  const [hiddenClubs, setHiddenClubs] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const selected =
    XSTART_VALIDATION.events.find((event) => event.event === selectedEvent) ??
    latest;
  const clubs = latest.clubs.map((club) => club.club);
  const shownClubs = clubs.filter((club) => !hiddenClubs.has(club));
  const eventCount = XSTART_VALIDATION.events.length;
  const cumulative = shownClubs
    .map((club) => ({
      club,
      hits: cumulativeHits(club, selectedEvent),
      detail: clubAt(selected, club),
    }))
    .sort(
      (left, right) =>
        right.hits - left.hits || left.club.localeCompare(right.club),
    );
  const lineX = (index: number) =>
    44 + (eventCount === 1 ? 0 : (index * 552) / (eventCount - 1));
  const lineY = (hits: number) => 224 - (hits / (11 * eventCount)) * 184;

  return (
    <section
      aria-labelledby="xstart-calibration-title"
      className="xstart-calibration"
    >
      <p className="eyebrow">
        GW1-GW{latest.event} · {eventCount} settled checks
      </p>
      <h2 id="xstart-calibration-title">How close was the predicted XI?</h2>
      <p>
        One point when a predicted starter starts. Eleven per club per gameweek;
        the line adds those hits across every settled check.
      </p>

      <fieldset className="xstart-club-filter">
        <legend>Filter by club</legend>
        {clubs.map((club) => (
          <label key={club}>
            <input
              checked={!hiddenClubs.has(club)}
              onChange={(event) => {
                setHiddenClubs((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.delete(club);
                  else next.add(club);
                  return next;
                });
              }}
              type="checkbox"
            />
            <span translate="no">{club}</span>
          </label>
        ))}
      </fieldset>

      <figure className="xstart-cumulative-chart">
        <figcaption>Cumulative XI hits by club</figcaption>
        <svg
          aria-label={`Cumulative xStart hits from GW1 to GW${latest.event}`}
          role="img"
          viewBox="0 0 640 260"
        >
          <line className="xstart-axis" x1="44" x2="596" y1="224" y2="224" />
          <line className="xstart-axis" x1="44" x2="44" y1="40" y2="224" />
          <text className="xstart-axis-label is-y" x="36" y="228">
            0
          </text>
          <text className="xstart-axis-label is-y" x="36" y="44">
            {11 * eventCount}
          </text>
          {XSTART_VALIDATION.events.map((event, index) => (
            <text
              className="xstart-axis-label"
              key={event.event}
              x={lineX(index)}
              y="246"
            >
              GW{event.event}
            </text>
          ))}
          {shownClubs.map((club) => {
            const marker = clubMarker(club);
            const points = XSTART_VALIDATION.events
              .map(
                (event, index) =>
                  `${lineX(index)},${lineY(cumulativeHits(club, event.event))}`,
              )
              .join(" ");
            return (
              <polyline
                className="xstart-cumulative-line"
                data-club={club}
                fill="none"
                key={club}
                points={points}
                stroke={marker?.fill}
                strokeDasharray={marker?.dash ?? undefined}
              />
            );
          })}
        </svg>
      </figure>

      <label className="xstart-gw-choice">
        Gameweek
        <select
          onChange={(event) => setSelectedEvent(Number(event.target.value))}
          value={selectedEvent}
        >
          {XSTART_VALIDATION.events.map((event) => (
            <option key={event.event} value={event.event}>
              GW{event.event}
            </option>
          ))}
        </select>
      </label>

      <h3>GW{selected.event} hits</h3>
      <ol className="xstart-score-bars">
        {selected.clubs
          .filter((club) => !hiddenClubs.has(club.club))
          .map((club) => {
            const marker = clubMarker(club.club);
            return (
              <li key={club.club}>
                <span className="xstart-score-bar-label" translate="no">
                  {club.club}
                </span>
                <span className="xstart-score-bar-track">
                  <span
                    className="xstart-score-bar-fill"
                    style={{
                      width: `${String((club.topElevenHits / 11) * 100)}%`,
                      background: marker?.fill,
                      borderColor: marker?.stroke ?? undefined,
                    }}
                  />
                </span>
                <span className="mono xstart-score-bar-value">
                  {club.topElevenHits}/11
                </span>
                <InfoMarker
                  label={`${club.club} GW${selected.event} xStart detail`}
                >
                  <ClubDetail club={club} />
                </InfoMarker>
              </li>
            );
          })}
      </ol>

      <h3>Cumulative, easiest to predict first</h3>
      <ol className="xstart-rank-bars">
        {cumulative.map(({ club, hits, detail }) => {
          const marker = clubMarker(club);
          return (
            <li key={club}>
              <span className="xstart-rank-label" translate="no">
                {club}
              </span>
              <span className="xstart-rank-track">
                <span
                  className="xstart-rank-fill"
                  style={{
                    width: `${String((hits / (11 * eventCount)) * 100)}%`,
                    background: marker?.fill,
                    borderColor: marker?.stroke ?? undefined,
                  }}
                />
              </span>
              <span className="mono xstart-rank-value">{hits}</span>
              {detail ? (
                <InfoMarker label={`${club} cumulative xStart detail`}>
                  <ClubDetail club={detail} />
                </InfoMarker>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
