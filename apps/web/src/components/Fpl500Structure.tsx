import { useState } from "react";

import { fineShare, money } from "../format";
import { kitForShortName } from "../kit/team-kits";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import { CeefaxShirt } from "./CeefaxShirt";
import type { Fpl500Holding } from "./Fpl500Holdings";
import { PlayerDetail, type DetailPlayer } from "./PlayerDetail";

type DistributionSummary = {
  mean: number;
  median: number;
  p10: number;
  p90: number;
  minimum: number;
  maximum: number;
};

export type PortfolioStructure = {
  keeperPairings: {
    starterElementId: number;
    benchElementId: number;
    count: number;
    share: number;
  }[];
  outfieldTrios?: {
    position: "DEF" | "MID" | "FWD";
    elementIds: number[];
    count: number;
    share: number;
  }[];
  commonStartingXi: {
    method: string;
    formation: number[];
    elementIds: number[];
  };
  popularitySquad?: {
    method: string;
    squad: number[];
    starters: number[];
    bench: number[];
    formation: number[];
    spentTenths: number;
    xiSpentTenths: number;
    bankTenths: number;
    meanOwnership: number;
    meanStartedShare: number;
    rawGameweekPoints?: number;
  };
  positionalSpend: Record<"GKP" | "DEF" | "MID" | "FWD", DistributionSummary>;
};

function positionOf(elementId: number, holdings: readonly Fpl500Holding[]) {
  return (
    holdings.find((holding) => holding.elementId === elementId)?.position ??
    PLAYERS_BY_ELEMENT_ID.get(elementId)?.position ??
    "MID"
  );
}

function playerOf(elementId: number, holdings: readonly Fpl500Holding[]) {
  const holding = holdings.find((entry) => entry.elementId === elementId);
  const known = PLAYERS_BY_ELEMENT_ID.get(elementId);
  return {
    elementId,
    code: holding?.code ?? known?.code,
    name: holding?.name ?? known?.name ?? `Element ${String(elementId)}`,
    position: holding?.position ?? known?.position ?? "MID",
    club: holding?.club ?? known?.club ?? "UNK",
    priceTenths: holding?.priceTenths ?? known?.priceTenths,
    ownedShare: holding?.ownedShare ?? 0,
    startedShare: holding?.startedShare ?? 0,
    points: holding?.lastWeekPoints,
  };
}

export function Fpl500Structure({
  holdings,
  structure,
}: {
  holdings: readonly Fpl500Holding[];
  structure: PortfolioStructure;
}) {
  const [selected, setSelected] = useState<DetailPlayer | null>(null);
  const positions = ["GKP", "DEF", "MID", "FWD"] as const;
  const popularity = structure.popularitySquad;
  const starters =
    popularity?.starters ?? structure.commonStartingXi.elementIds;
  const bench = popularity?.bench ?? [];
  const formation =
    popularity?.formation ?? structure.commonStartingXi.formation;
  const maximumSpend = Math.max(
    ...positions.map((position) => structure.positionalSpend[position].mean),
  );
  return (
    <section
      className="fpl500-structure"
      aria-labelledby="fpl500-structure-title"
    >
      <h3 className="fpl500-section-band is-squad" id="fpl500-structure-title">
        {popularity ? "The FPL500 popularity squad" : "Most common XI"}
      </h3>
      <p className="mono">
        {popularity
          ? `A legal £100m squad built from exact ownership and starts · ${formation.join("-")}.`
          : `Cohort composite · ${formation.join("-")} · awaiting the legal squad capture.`}
      </p>
      {popularity ? (
        <dl className="fpl500-team-ledger">
          <div>
            <dt>Squad</dt>
            <dd>{money.format(popularity.spentTenths / 10)}m</dd>
          </div>
          <div>
            <dt>Starting XI</dt>
            <dd>{money.format(popularity.xiSpentTenths / 10)}m</dd>
          </div>
          <div>
            <dt>Bank</dt>
            <dd>{money.format(popularity.bankTenths / 10)}m</dd>
          </div>
          <div>
            <dt>Mean ownership</dt>
            <dd>{fineShare.format(popularity.meanOwnership)}</dd>
          </div>
          <div>
            <dt>Mean started</dt>
            <dd>{fineShare.format(popularity.meanStartedShare)}</dd>
          </div>
          <div>
            <dt>GW points</dt>
            <dd>{popularity.rawGameweekPoints ?? "—"} raw</dd>
          </div>
        </dl>
      ) : null}
      <div className="fpl500-common-pitch">
        {positions.map((position) => (
          <div className={`is-${position.toLowerCase()}`} key={position}>
            {starters
              .filter(
                (elementId) => positionOf(elementId, holdings) === position,
              )
              .map((elementId) => {
                const player = playerOf(elementId, holdings);
                const kit = kitForShortName(player.club);
                const canOpen =
                  player.code !== undefined && player.priceTenths !== undefined;
                return (
                  <button
                    className="fpl500-player-tile"
                    disabled={!canOpen}
                    key={elementId}
                    onClick={() => {
                      if (!canOpen) return;
                      setSelected({
                        code: player.code!,
                        name: player.name,
                        position: player.position,
                        club: player.club,
                        priceTenths: player.priceTenths!,
                      });
                    }}
                    type="button"
                  >
                    {kit ? <CeefaxShirt kit={kit} label={null} /> : null}
                    <strong>{player.name}</strong>
                    <span className="mono">
                      {fineShare.format(player.ownedShare)} owned ·{" "}
                      {fineShare.format(player.startedShare)} XI
                    </span>
                    <span className="mono">
                      {player.priceTenths === undefined
                        ? "—"
                        : `${money.format(player.priceTenths / 10)}m`}{" "}
                      · GW {player.points ?? "—"}
                    </span>
                  </button>
                );
              })}
          </div>
        ))}
      </div>

      {bench.length > 0 ? (
        <section
          className="fpl500-popularity-bench"
          aria-labelledby="fpl500-bench-title"
        >
          <h4 id="fpl500-bench-title">Bench</h4>
          <div>
            {bench.map((elementId) => {
              const player = playerOf(elementId, holdings);
              const kit = kitForShortName(player.club);
              const canOpen =
                player.code !== undefined && player.priceTenths !== undefined;
              return (
                <button
                  disabled={!canOpen}
                  key={elementId}
                  onClick={() => {
                    if (!canOpen) return;
                    setSelected({
                      code: player.code!,
                      name: player.name,
                      position: player.position,
                      club: player.club,
                      priceTenths: player.priceTenths!,
                    });
                  }}
                  type="button"
                >
                  {kit ? <CeefaxShirt kit={kit} label={null} /> : null}
                  <strong>{player.name}</strong>
                  <small className="mono">
                    {fineShare.format(player.ownedShare)} owned ·{" "}
                    {fineShare.format(player.startedShare)} XI
                  </small>
                  <small className="mono">
                    {player.priceTenths === undefined
                      ? "—"
                      : `${money.format(player.priceTenths / 10)}m`}{" "}
                    · GW {player.points ?? "—"}
                  </small>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      <div className="fpl500-structure-grid">
        <section aria-labelledby="fpl500-spend-title">
          <h4 className="fpl500-section-band is-value" id="fpl500-spend-title">
            Average squad spend
          </h4>
          <ul className="fpl500-spend">
            {positions.map((position) => {
              const spend = structure.positionalSpend[position];
              const mean = spend.mean;
              return (
                <li key={position}>
                  <span
                    aria-hidden="true"
                    className={`fpl500-spend-fill is-${position.toLowerCase()}`}
                    style={{ width: `${String((mean / maximumSpend) * 100)}%` }}
                  />
                  <span>{position}</span>
                  <span className="fpl500-spend-values">
                    <strong>{money.format(mean / 10)}m</strong>
                    <small className="mono">
                      {money.format(spend.p10 / 10)}–
                      {money.format(spend.p90 / 10)}m
                    </small>
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
      {selected ? (
        <PlayerDetail onClose={() => setSelected(null)} player={selected} />
      ) : null}
    </section>
  );
}
