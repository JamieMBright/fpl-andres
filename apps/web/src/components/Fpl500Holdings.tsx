import { useState } from "react";

import { fineShare, integer, oneDecimal } from "../format";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import { InfoMarker } from "./InfoMarker";
import { PlayerAvatar } from "./PlayerAvatar";

export type Fpl500Holding = {
  elementId: number;
  code?: number;
  name?: string;
  position?: "GKP" | "DEF" | "MID" | "FWD";
  club?: string;
  ownedShare: number;
  startedShare: number;
  captainedShare: number;
  effectiveOwnership: number;
  lastWeekPoints?: number;
  pointsSinceFirstCapture?: number;
  weightedContribution?: number;
};

export type HoldingMetric = "ownership" | "since" | "latest";

const POSITIONS = [
  { code: "GKP", label: "Goalkeepers" },
  { code: "DEF", label: "Defenders" },
  { code: "MID", label: "Midfielders" },
  { code: "FWD", label: "Forwards" },
] as const;

function metricValue(holding: Fpl500Holding, metric: HoldingMetric): number {
  if (metric === "ownership") return holding.ownedShare;
  if (metric === "since") return holding.pointsSinceFirstCapture ?? 0;
  return holding.lastWeekPoints ?? 0;
}

function shownValue(holding: Fpl500Holding, metric: HoldingMetric): string {
  if (metric === "ownership") return fineShare.format(holding.ownedShare);
  return `${integer.format(metricValue(holding, metric))} pts`;
}

function holdingPlayer(holding: Fpl500Holding) {
  const known = PLAYERS_BY_ELEMENT_ID.get(holding.elementId);
  return {
    code: holding.code ?? known?.code,
    name: holding.name ?? known?.name ?? `Element ${holding.elementId}`,
    position: holding.position ?? known?.position,
    club: holding.club ?? known?.club,
  };
}

export function Fpl500Holdings({
  event,
  holdings,
}: {
  event: number;
  holdings: readonly Fpl500Holding[];
}) {
  const [metric, setMetric] = useState<HoldingMetric>("ownership");

  return (
    <section
      className="fpl500-holdings"
      aria-labelledby="fpl500-holdings-title"
    >
      <h3 id="fpl500-holdings-title">
        Who they own, by position
        <InfoMarker label="FPL500 player measures">
          Ownership is the share of captured squads holding the player. Returns
          are raw FPL points. Weighted contribution multiplies raw points by
          ownership. EO adds captaincy to started share; no deadline-time field
          EO was captured, so I do not invent a comparison.
        </InfoMarker>
      </h3>
      <fieldset className="fpl500-metric-choice">
        <legend>Player measure</legend>
        {(
          [
            ["ownership", "Ownership"],
            ["since", "Returns since GW1"],
            ["latest", `GW${event} returns`],
          ] as const
        ).map(([value, label]) => (
          <label key={value}>
            <input
              checked={metric === value}
              name="fpl500-player-measure"
              onChange={() => setMetric(value)}
              type="radio"
              value={value}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
      {event === 1 && metric !== "ownership" ? (
        <p className="mono fpl500-measure-note">
          One round captured. Since GW1 and GW1 returns are the same today.
        </p>
      ) : null}
      <div className="fpl500-position-list">
        {POSITIONS.map((position, index) => {
          const rows = holdings
            .filter(
              (holding) => holdingPlayer(holding).position === position.code,
            )
            .sort(
              (left, right) =>
                metricValue(right, metric) - metricValue(left, metric) ||
                right.ownedShare - left.ownedShare,
            );
          const mostOwned = [...rows].sort(
            (left, right) => right.ownedShare - left.ownedShare,
          )[0];
          const hero = mostOwned ? holdingPlayer(mostOwned) : undefined;
          const maximum = Math.max(
            1,
            ...rows.map((holding) => metricValue(holding, metric)),
          );
          return (
            <details
              className="fpl500-position"
              data-position={position.code}
              key={position.code}
              open={index === 0}
            >
              <summary>
                <h4>{position.label}</h4>
                <span className="mono">{rows.length} selected</span>
              </summary>
              {hero && mostOwned ? (
                <div className="fpl500-position-hero">
                  <PlayerAvatar
                    className="fpl500-position-photo"
                    club={hero.club ?? null}
                    name={hero.name}
                    playerCode={hero.code}
                  />
                  <p>
                    <strong>{hero.name}</strong>
                    <span>Most owned {position.code.toLowerCase()}</span>
                    <span className="mono">
                      {fineShare.format(mostOwned.ownedShare)} of squads
                    </span>
                  </p>
                </div>
              ) : null}
              <ol className="fpl500-holding-bars">
                {rows.map((holding) => {
                  const player = holdingPlayer(holding);
                  const value = metricValue(holding, metric);
                  return (
                    <li key={holding.elementId}>
                      <span
                        aria-hidden="true"
                        className="fpl500-holding-fill"
                        style={{ width: `${String((value / maximum) * 100)}%` }}
                      />
                      <span className="fpl500-holding-name">{player.name}</span>
                      <strong className="mono">
                        {shownValue(holding, metric)}
                      </strong>
                      <small className="mono">
                        EO {fineShare.format(holding.effectiveOwnership)}
                        {holding.weightedContribution === undefined
                          ? ""
                          : ` · weighted ${oneDecimal.format(holding.weightedContribution)} pts`}
                      </small>
                    </li>
                  );
                })}
              </ol>
            </details>
          );
        })}
      </div>
    </section>
  );
}
