import { useId, useState } from "react";

import { InfoMarker } from "./InfoMarker";
import { clubMarker } from "../kit/club-markers";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import {
  XSTART_VALIDATION,
  latestXStartEvent,
  type XStartClubValidation,
  type XStartValidationEvent,
} from "../state/xstart-validation";

type PerformancePeriod = "average" | number;
type PerformanceOrder = "club" | "easiest" | "hardest";

interface LineHover {
  club: string;
  event: number;
  eventIndex: number;
  hits: number;
}

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

function averageHits(club: string): number {
  const scores = XSTART_VALIDATION.events.flatMap((event) => {
    const row = clubAt(event, club);
    return row ? [row.topElevenHits] : [];
  });
  return scores.length === 0
    ? 0
    : scores.reduce((total, score) => total + score, 0) / scores.length;
}

function ClubAverageDetail({ club }: { club: string }) {
  const rows = XSTART_VALIDATION.events.flatMap((event) => {
    const detail = clubAt(event, club);
    return detail ? [{ event: event.event, hits: detail.topElevenHits }] : [];
  });
  return (
    <>
      <span className="info-marker-line">
        {averageHits(club).toFixed(1)}/11 average across {rows.length} settled
        gameweeks.
      </span>
      <span className="info-marker-line">
        {rows.map((row) => `GW${row.event} ${row.hits}/11`).join(" · ")}
      </span>
    </>
  );
}

export function XStartCalibration() {
  const latest = latestXStartEvent(XSTART_VALIDATION);
  const lineTooltipId = useId();
  const [period, setPeriod] = useState<PerformancePeriod>("average");
  const [order, setOrder] = useState<PerformanceOrder>("club");
  const [lineHover, setLineHover] = useState<LineHover | null>(null);
  const [hiddenClubs, setHiddenClubs] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const selected =
    typeof period === "number"
      ? (XSTART_VALIDATION.events.find((event) => event.event === period) ??
        latest)
      : null;
  const clubs = latest.clubs.map((club) => club.club);
  const shownClubs = clubs.filter((club) => !hiddenClubs.has(club));
  const eventCount = XSTART_VALIDATION.events.length;
  const performanceRows = shownClubs
    .map((club) => ({
      club,
      score:
        selected === null
          ? averageHits(club)
          : (clubAt(selected, club)?.topElevenHits ?? 0),
      detail: selected === null ? null : clubAt(selected, club),
    }))
    .sort((left, right) => {
      if (order === "easiest")
        return right.score - left.score || left.club.localeCompare(right.club);
      if (order === "hardest")
        return left.score - right.score || left.club.localeCompare(right.club);
      return left.club.localeCompare(right.club);
    });
  const lineX = (index: number) =>
    44 + (eventCount === 1 ? 0 : (index * 552) / (eventCount - 1));
  const lineY = (hits: number) => 224 - (hits / (11 * eventCount)) * 184;
  const linePoints = (club: string) =>
    XSTART_VALIDATION.events
      .map(
        (event, index) =>
          `${lineX(index)},${lineY(cumulativeHits(club, event.event))}`,
      )
      .join(" ");
  const showLinePoint = (club: string, eventIndex: number) => {
    const event = XSTART_VALIDATION.events[eventIndex];
    if (!event) return;
    const detail = clubAt(event, club);
    if (!detail) return;
    setLineHover({
      club,
      event: event.event,
      eventIndex,
      hits: detail.topElevenHits,
    });
  };

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

      <figure
        className="xstart-cumulative-chart"
        data-hovering={lineHover !== null}
      >
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
            return (
              <polyline
                className={`xstart-cumulative-line${lineHover?.club === club ? " is-active" : ""}`}
                data-club={club}
                fill="none"
                key={club}
                points={linePoints(club)}
                stroke={marker?.fill}
                strokeDasharray={marker?.dash ?? undefined}
              />
            );
          })}
          {shownClubs.map((club) => (
            <polyline
              aria-describedby={
                lineHover?.club === club ? lineTooltipId : undefined
              }
              aria-label={`${club} cumulative xStart line`}
              className="xstart-cumulative-hit-area"
              data-club={club}
              fill="none"
              key={`hit-${club}`}
              onPointerLeave={() => setLineHover(null)}
              onPointerMove={(pointerEvent) => {
                const svg = pointerEvent.currentTarget.ownerSVGElement;
                if (!svg) return;
                const box = svg.getBoundingClientRect();
                if (box.width <= 0) return;
                const svgX =
                  ((pointerEvent.clientX - box.left) / box.width) * 640;
                const rawIndex =
                  eventCount === 1
                    ? 0
                    : Math.round(((svgX - 44) / (596 - 44)) * (eventCount - 1));
                showLinePoint(
                  club,
                  Math.max(0, Math.min(eventCount - 1, rawIndex)),
                );
              }}
              points={linePoints(club)}
              role="img"
            />
          ))}
          {lineHover ? (
            <g aria-hidden="true" className="xstart-line-hover-marker">
              <line
                x1={lineX(lineHover.eventIndex)}
                x2={lineX(lineHover.eventIndex)}
                y1="40"
                y2="224"
              />
              <circle
                cx={lineX(lineHover.eventIndex)}
                cy={lineY(cumulativeHits(lineHover.club, lineHover.event))}
                r="6"
              />
            </g>
          ) : null}
        </svg>
        {lineHover ? (
          <p className="xstart-line-tooltip" id={lineTooltipId} role="tooltip">
            <strong translate="no">{lineHover.club}</strong> · GW
            {lineHover.event} · {lineHover.hits}/11
          </p>
        ) : null}
      </figure>

      <div className="xstart-performance-controls">
        <label className="xstart-gw-choice">
          Performance period
          <select
            onChange={(event) =>
              setPeriod(
                event.target.value === "average"
                  ? "average"
                  : Number(event.target.value),
              )
            }
            value={period}
          >
            <option value="average">Season average</option>
            {XSTART_VALIDATION.events.map((event) => (
              <option key={event.event} value={event.event}>
                GW{event.event}
              </option>
            ))}
          </select>
        </label>
        <label className="xstart-gw-choice">
          Sort performance
          <select
            onChange={(event) =>
              setOrder(event.target.value as PerformanceOrder)
            }
            value={order}
          >
            <option value="club">Club</option>
            <option value="easiest">Easiest to predict</option>
            <option value="hardest">Hardest to predict</option>
          </select>
        </label>
      </div>

      <h3>
        {selected === null ? "Season average hits" : `GW${selected.event} hits`}
      </h3>
      <ol
        aria-label="xStart performance by club"
        className="xstart-score-bars xstart-performance-bars"
      >
        {performanceRows.map(({ club, score, detail }) => {
          const marker = clubMarker(club);
          return (
            <li data-score={score} key={club}>
              <span className="xstart-score-bar-label" translate="no">
                {club}
              </span>
              <span className="xstart-score-bar-track">
                <span
                  className="xstart-score-bar-fill"
                  style={{
                    width: `${String((score / 11) * 100)}%`,
                    background: marker?.fill,
                    borderColor: marker?.stroke ?? undefined,
                  }}
                />
              </span>
              <span className="mono xstart-score-bar-value">
                {selected === null ? score.toFixed(1) : score}/11
              </span>
              <InfoMarker
                label={
                  selected === null
                    ? `${club} season average xStart detail`
                    : `${club} GW${selected.event} xStart detail`
                }
              >
                {detail ? (
                  <ClubDetail club={detail} />
                ) : (
                  <ClubAverageDetail club={club} />
                )}
              </InfoMarker>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
