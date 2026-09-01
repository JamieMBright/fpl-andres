import { useRef, useState } from "react";

import { fineShare, integer, oneDecimal } from "../format";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import { InfoMarker } from "./InfoMarker";
import { PlayerAvatar } from "./PlayerAvatar";
import { PlayerDetail, type DetailPlayer } from "./PlayerDetail";

export type Fpl500Holding = {
  elementId: number;
  code?: number;
  name?: string;
  position?: "GKP" | "DEF" | "MID" | "FWD";
  club?: string;
  teamId?: number;
  priceTenths?: number;
  ownedShare: number;
  startedShare: number;
  captainedShare: number;
  effectiveOwnership: number;
  lastWeekPoints?: number;
  pointsSinceFirstCapture?: number;
  weightedContribution?: number;
};

export type HoldingMetric = "ownership" | "since" | "latest";
export type KeeperPairing = {
  starterElementId: number;
  benchElementId: number;
  count: number;
  share: number;
};

export type OutfieldTrio = {
  position: "DEF" | "MID" | "FWD";
  elementIds: readonly number[];
  count: number;
  share: number;
};

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
    priceTenths: holding.priceTenths ?? known?.priceTenths,
  };
}

function ownershipBand(share: number): "high" | "medium" | "low" {
  if (share >= 0.25) return "high";
  if (share >= 0.1) return "medium";
  return "low";
}

export function Fpl500Holdings({
  event,
  holdings,
  keeperPairings = [],
  outfieldTrios = [],
}: {
  event: number;
  holdings: readonly Fpl500Holding[];
  keeperPairings?: readonly KeeperPairing[] | undefined;
  outfieldTrios?: readonly OutfieldTrio[] | undefined;
}) {
  const [metric, setMetric] = useState<HoldingMetric>("ownership");
  const [selected, setSelected] = useState<DetailPlayer | null>(null);
  const [keeperView, setKeeperView] = useState<"players" | "pairings">(
    "players",
  );
  const playerTab = useRef<HTMLButtonElement>(null);
  const pairingTab = useRef<HTMLButtonElement>(null);

  function selectKeeperView(view: "players" | "pairings") {
    setKeeperView(view);
    (view === "players" ? playerTab : pairingTab).current?.focus();
  }

  function holdingRows(rows: readonly Fpl500Holding[], maximum: number) {
    return (
      <ol className="fpl500-holding-bars">
        {rows.map((holding) => {
          const player = holdingPlayer(holding);
          const value = metricValue(holding, metric);
          const canOpen =
            player.code !== undefined &&
            player.position !== undefined &&
            player.club !== undefined &&
            player.priceTenths !== undefined;
          return (
            <li
              className={`is-ownership-${ownershipBand(holding.ownedShare)}`}
              key={holding.elementId}
            >
              <span
                aria-hidden="true"
                className="fpl500-holding-fill"
                style={{ width: `${String((value / maximum) * 100)}%` }}
              />
              {canOpen ? (
                <button
                  className="fpl500-holding-name"
                  onClick={() =>
                    setSelected({
                      code: player.code!,
                      name: player.name,
                      position: player.position!,
                      club: player.club!,
                      priceTenths: player.priceTenths!,
                    })
                  }
                  type="button"
                >
                  {player.name}
                </button>
              ) : (
                <span className="fpl500-holding-name">{player.name}</span>
              )}
              <strong className="mono">{shownValue(holding, metric)}</strong>
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
    );
  }

  function positionPlayers(
    position: (typeof POSITIONS)[number],
    hero: ReturnType<typeof holdingPlayer> | undefined,
    mostOwned: Fpl500Holding | undefined,
    visible: readonly Fpl500Holding[],
    fringe: readonly Fpl500Holding[],
    maximum: number,
  ) {
    return (
      <>
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
        {holdingRows(visible, maximum)}
        {fringe.length > 0 ? (
          <details className="fpl500-position-fringe">
            <summary className="mono">
              {fringe.length} below 1% ownership
            </summary>
            {holdingRows(fringe, maximum)}
          </details>
        ) : null}
      </>
    );
  }

  function playerName(elementId: number) {
    const holding = holdings.find((entry) => entry.elementId === elementId);
    return holding
      ? holdingPlayer(holding).name
      : (PLAYERS_BY_ELEMENT_ID.get(elementId)?.name ??
          `Element ${String(elementId)}`);
  }

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
          const visible = rows.filter((holding) => holding.ownedShare >= 0.01);
          const fringe = rows.filter((holding) => holding.ownedShare < 0.01);
          const trio = outfieldTrios.find(
            (entry) => entry.position === position.code,
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
              {position.code === "GKP" ? (
                <div
                  aria-label="Goalkeeper views"
                  className="fpl500-keeper-tabs"
                  role="tablist"
                >
                  {(["players", "pairings"] as const).map((view) => (
                    <button
                      aria-controls={`fpl500-keepers-${view}`}
                      aria-selected={keeperView === view}
                      id={`fpl500-keepers-${view}-tab`}
                      key={view}
                      onClick={() => selectKeeperView(view)}
                      onKeyDown={(event) => {
                        if (event.key === "ArrowLeft" || event.key === "Home") {
                          event.preventDefault();
                          selectKeeperView("players");
                        }
                        if (event.key === "ArrowRight" || event.key === "End") {
                          event.preventDefault();
                          selectKeeperView("pairings");
                        }
                      }}
                      ref={view === "players" ? playerTab : pairingTab}
                      role="tab"
                      tabIndex={keeperView === view ? 0 : -1}
                      type="button"
                    >
                      {view === "players" ? "Players" : "Pairings"}
                    </button>
                  ))}
                </div>
              ) : null}
              {position.code === "GKP" ? (
                <>
                  <div
                    aria-labelledby="fpl500-keepers-players-tab"
                    hidden={keeperView !== "players"}
                    id="fpl500-keepers-players"
                    role="tabpanel"
                  >
                    {positionPlayers(
                      position,
                      hero,
                      mostOwned,
                      visible,
                      fringe,
                      maximum,
                    )}
                  </div>
                  <div
                    aria-labelledby="fpl500-keepers-pairings-tab"
                    hidden={keeperView !== "pairings"}
                    id="fpl500-keepers-pairings"
                    role="tabpanel"
                  >
                    <ol className="fpl500-pairs">
                      {keeperPairings.slice(0, 12).map((pair) => (
                        <li
                          key={`${pair.starterElementId}-${pair.benchElementId}`}
                        >
                          <span>
                            {playerName(pair.starterElementId)} +{" "}
                            {playerName(pair.benchElementId)}
                          </span>
                          <strong className="mono">
                            {fineShare.format(pair.share)} ·{" "}
                            {integer.format(pair.count)} squads
                          </strong>
                        </li>
                      ))}
                    </ol>
                  </div>
                </>
              ) : (
                <div>
                  {positionPlayers(
                    position,
                    hero,
                    mostOwned,
                    visible,
                    fringe,
                    maximum,
                  )}
                </div>
              )}
              {trio ? (
                <p className="fpl500-trio">
                  <span>Held together: </span>
                  <span>
                    {trio.elementIds.map((id) => playerName(id)).join(" + ")}
                  </span>
                  <strong className="mono">
                    {fineShare.format(trio.share)} ·{" "}
                    {integer.format(trio.count)} squads
                  </strong>
                </p>
              ) : null}
            </details>
          );
        })}
      </div>
      {selected ? (
        <PlayerDetail onClose={() => setSelected(null)} player={selected} />
      ) : null}
    </section>
  );
}
