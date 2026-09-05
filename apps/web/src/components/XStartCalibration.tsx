import { useId, useLayoutEffect, useRef, useState } from "react";

import { CeefaxShirt } from "./CeefaxShirt";
import { InfoMarker } from "./InfoMarker";
import { clubMarker } from "../kit/club-markers";
import { kitForShortName } from "../kit/team-kits";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import {
  XSTART_VALIDATION,
  averageXStartHits,
  latestSettledWindow,
  latestXStartEvent,
  type XStartClubValidation,
  type XStartValidation,
  type XStartValidationEvent,
} from "../state/xstart-validation";

type PerformancePeriod = "average" | "last5" | number;
type PerformanceOrder = "club" | "easiest" | "hardest";

const LAST_FIVE_GAMEWEEKS = 5;

interface LineHover {
  club: string;
  event: number;
  eventIndex: number;
  hits: number;
  runningAverage: number;
}

function lineX(index: number, eventCount: number): number {
  return 44 + (eventCount === 1 ? 0 : (index * 552) / (eventCount - 1));
}

function lineY(hits: number): number {
  return 224 - (hits / 11) * 184;
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

function averageHitsThrough(
  events: readonly XStartValidationEvent[],
  club: string,
  throughEvent: number,
): number {
  return averageXStartHits(
    events.filter((event) => event.event <= throughEvent),
    club,
  );
}

function ClubAverageDetail({
  club,
  events,
}: {
  club: string;
  events: readonly XStartValidationEvent[];
}) {
  const rows = events.flatMap((event) => {
    const detail = clubAt(event, club);
    return detail ? [{ event: event.event, hits: detail.topElevenHits }] : [];
  });
  return (
    <>
      <span className="info-marker-line">
        {averageXStartHits(events, club).toFixed(1)}/11 average across{" "}
        {rows.length} settled gameweeks.
      </span>
      <span className="info-marker-line">
        {rows.map((row) => `GW${row.event} ${row.hits}/11`).join(" · ")}
      </span>
    </>
  );
}

export function XStartCalibration({
  validation = XSTART_VALIDATION,
}: {
  readonly validation?: XStartValidation;
}) {
  const latest = latestXStartEvent(validation);
  const lineTooltipId = useId();
  const chartRef = useRef<HTMLElement>(null);
  const chartSvgRef = useRef<SVGSVGElement>(null);
  const lineTooltipRef = useRef<HTMLParagraphElement>(null);
  const [period, setPeriod] = useState<PerformancePeriod>("average");
  const [order, setOrder] = useState<PerformanceOrder>("club");
  const [lineHover, setLineHover] = useState<LineHover | null>(null);
  const [lineTooltipPosition, setLineTooltipPosition] = useState<{
    left: number;
    top: number;
  } | null>(null);
  const [selectedClub, setSelectedClub] = useState<string | null>(null);
  const lastFiveEvents = latestSettledWindow(
    validation.events,
    LAST_FIVE_GAMEWEEKS,
  );
  const lastFiveReady = lastFiveEvents.length === LAST_FIVE_GAMEWEEKS;
  const selected =
    typeof period === "number"
      ? (validation.events.find((event) => event.event === period) ?? latest)
      : null;
  const clubs = [
    ...new Set(
      validation.events.flatMap((event) =>
        event.clubs.map((club) => club.club),
      ),
    ),
  ];
  const shownClubs = selectedClub === null ? clubs : [selectedClub];
  const eventCount = validation.events.length;
  const performanceRows = shownClubs
    .map((club) => ({
      club,
      score:
        period === "last5"
          ? averageXStartHits(lastFiveEvents, club)
          : selected === null
            ? averageXStartHits(validation.events, club)
            : (clubAt(selected, club)?.topElevenHits ?? 0),
      detail: selected === null ? null : clubAt(selected, club),
    }))
    .filter(({ detail }) => typeof period !== "number" || detail !== undefined)
    .sort((left, right) => {
      if (order === "easiest")
        return right.score - left.score || left.club.localeCompare(right.club);
      if (order === "hardest")
        return left.score - right.score || left.club.localeCompare(right.club);
      return left.club.localeCompare(right.club);
    });
  const linePoints = (club: string) =>
    validation.events
      .flatMap((event, index) => {
        if (!clubAt(event, club)) return [];
        return [
          `${lineX(index, eventCount)},${lineY(averageHitsThrough(validation.events, club, event.event))}`,
        ];
      })
      .join(" ");
  const showLinePoint = (club: string, eventIndex: number) => {
    const event = validation.events[eventIndex];
    if (!event) return;
    const detail = clubAt(event, club);
    if (!detail) return;
    setLineHover({
      club,
      event: event.event,
      eventIndex,
      hits: detail.topElevenHits,
      runningAverage: averageHitsThrough(validation.events, club, event.event),
    });
  };
  const showLinePointAtClientX = (
    club: string,
    hitArea: SVGPolylineElement,
    clientX: number,
  ) => {
    const svg = hitArea.ownerSVGElement;
    if (!svg) return;
    const box = svg.getBoundingClientRect();
    if (box.width <= 0) return;
    const svgX = ((clientX - box.left) / box.width) * 640;
    const rawIndex =
      eventCount === 1
        ? 0
        : Math.round(((svgX - 44) / (596 - 44)) * (eventCount - 1));
    showLinePoint(club, Math.max(0, Math.min(eventCount - 1, rawIndex)));
  };

  useLayoutEffect(() => {
    if (!lineHover) return;

    const positionTooltip = () => {
      const chart = chartRef.current;
      const svg = chartSvgRef.current;
      const tooltip = lineTooltipRef.current;
      if (!chart || !svg || !tooltip) return;

      const chartBox = chart.getBoundingClientRect();
      const svgBox = svg.getBoundingClientRect();
      const tooltipBox = tooltip.getBoundingClientRect();
      const chartWidth = chartBox.width || svgBox.width;
      const chartHeight = chartBox.height || svgBox.height;
      const pointLeft =
        svgBox.left -
        chartBox.left +
        (lineX(lineHover.eventIndex, eventCount) / 640) * svgBox.width;
      const pointTop =
        svgBox.top -
        chartBox.top +
        (lineY(lineHover.runningAverage) / 260) * svgBox.height;
      const padding = 8;
      const gap = 10;
      const left = Math.max(
        padding,
        Math.min(pointLeft + gap, chartWidth - tooltipBox.width - padding),
      );
      const above = pointTop - tooltipBox.height - gap;
      const preferredTop = above >= padding ? above : pointTop + gap;
      const top = Math.max(
        padding,
        Math.min(preferredTop, chartHeight - tooltipBox.height - padding),
      );
      setLineTooltipPosition({ left, top });
    };

    positionTooltip();
    window.addEventListener("resize", positionTooltip);
    return () => window.removeEventListener("resize", positionTooltip);
  }, [eventCount, lineHover]);

  return (
    <section
      aria-labelledby="xstart-calibration-title"
      className="xstart-calibration"
    >
      <p className="eyebrow">
        GW1-GW{latest.event} · {eventCount} evaluated checks
        {latest.complete === false ? " · current round is still live" : ""}
      </p>
      <h2 id="xstart-calibration-title">How close was the predicted XI?</h2>
      <p>
        One point when a predicted starter starts. Eleven per club per gameweek;
        the line tracks the season average through each settled check.
      </p>

      <fieldset className="xstart-club-filter">
        <legend>Filter by club</legend>
        <div className="xstart-club-filter-options">
          {clubs.map((club) => {
            const kit = kitForShortName(club);
            return (
              <button
                aria-pressed={selectedClub === club}
                key={club}
                onClick={() => {
                  setSelectedClub((current) =>
                    current === club ? null : club,
                  );
                  setLineHover(null);
                }}
                type="button"
              >
                {kit ? <CeefaxShirt kit={kit} label={null} /> : null}
                <span translate="no">{club}</span>
              </button>
            );
          })}
        </div>
      </fieldset>

      <figure
        className="xstart-cumulative-chart"
        data-hovering={lineHover !== null}
        ref={chartRef}
      >
        <figcaption>Running season-average XI hits by club</figcaption>
        <svg
          aria-label={`Season-to-date average xStart hits from GW1 to GW${latest.event}`}
          ref={chartSvgRef}
          role="img"
          viewBox="0 0 640 260"
        >
          <line className="xstart-axis" x1="44" x2="596" y1="224" y2="224" />
          <line className="xstart-axis" x1="44" x2="44" y1="40" y2="224" />
          <text className="xstart-axis-label is-y" x="36" y="228">
            0
          </text>
          <text className="xstart-axis-label is-y" x="36" y="44">
            11
          </text>
          {validation.events.map((event, index) => (
            <text
              className="xstart-axis-label"
              key={event.event}
              x={lineX(index, eventCount)}
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
              aria-label={`${club} season-to-date average xStart line`}
              className="xstart-cumulative-hit-area"
              data-club={club}
              fill="none"
              key={`hit-${club}`}
              onBlur={() => setLineHover(null)}
              onFocus={() => showLinePoint(club, eventCount - 1)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setLineHover(null);
              }}
              onPointerCancel={() => setLineHover(null)}
              onPointerDown={(pointerEvent) => {
                showLinePointAtClientX(
                  club,
                  pointerEvent.currentTarget,
                  pointerEvent.clientX,
                );
              }}
              onPointerLeave={() => setLineHover(null)}
              onPointerMove={(pointerEvent) => {
                showLinePointAtClientX(
                  club,
                  pointerEvent.currentTarget,
                  pointerEvent.clientX,
                );
              }}
              points={linePoints(club)}
              role="img"
              tabIndex={Number(0)}
            />
          ))}
          {lineHover ? (
            <g aria-hidden="true" className="xstart-line-hover-marker">
              <line
                x1={lineX(lineHover.eventIndex, eventCount)}
                x2={lineX(lineHover.eventIndex, eventCount)}
                y1="40"
                y2="224"
              />
              <circle
                cx={lineX(lineHover.eventIndex, eventCount)}
                cy={lineY(lineHover.runningAverage)}
                r="6"
              />
            </g>
          ) : null}
        </svg>
        {lineHover ? (
          <p
            className="xstart-line-tooltip"
            id={lineTooltipId}
            ref={lineTooltipRef}
            role="tooltip"
            style={{
              left: lineTooltipPosition?.left ?? 0,
              top: lineTooltipPosition?.top ?? 0,
              visibility: lineTooltipPosition ? "visible" : "hidden",
            }}
          >
            <strong translate="no">{lineHover.club}</strong> · GW
            {lineHover.event}
            <span>
              Season-to-date average {lineHover.runningAverage.toFixed(1)}/11
            </span>
            <span>
              GW{lineHover.event} score {lineHover.hits}/11
            </span>
          </p>
        ) : null}
      </figure>

      <div className="xstart-performance-controls">
        <label className="xstart-gw-choice">
          Performance period
          <select
            onChange={(event) =>
              setPeriod(
                event.target.value === "average" ||
                  event.target.value === "last5"
                  ? event.target.value
                  : Number(event.target.value),
              )
            }
            value={period}
          >
            <option value="average">Season average</option>
            <option disabled={!lastFiveReady} value="last5">
              Last 5GW average
            </option>
            {validation.events.map((event) => (
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
        {period === "last5"
          ? "Last 5GW average hits"
          : selected === null
            ? "Season average hits"
            : `GW${selected.event} hits`}
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
                {typeof period === "number" ? score : score.toFixed(1)}/11
              </span>
              <InfoMarker
                label={
                  period === "last5"
                    ? `${club} last 5GW average xStart detail`
                    : selected === null
                      ? `${club} season average xStart detail`
                      : `${club} GW${selected.event} xStart detail`
                }
              >
                {detail ? (
                  <ClubDetail club={detail} />
                ) : (
                  <ClubAverageDetail
                    club={club}
                    events={
                      period === "last5" ? lastFiveEvents : validation.events
                    }
                  />
                )}
              </InfoMarker>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
