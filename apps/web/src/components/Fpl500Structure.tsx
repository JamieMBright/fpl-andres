import { fineShare, money } from "../format";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import type { Fpl500Holding } from "./Fpl500Holdings";

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
  commonStartingXi: {
    method: string;
    formation: number[];
    elementIds: number[];
  };
  positionalSpend: Record<"GKP" | "DEF" | "MID" | "FWD", DistributionSummary>;
};

function nameOf(elementId: number, holdings: readonly Fpl500Holding[]) {
  return (
    holdings.find((holding) => holding.elementId === elementId)?.name ??
    PLAYERS_BY_ELEMENT_ID.get(elementId)?.name ??
    `Element ${String(elementId)}`
  );
}

function positionOf(elementId: number, holdings: readonly Fpl500Holding[]) {
  return (
    holdings.find((holding) => holding.elementId === elementId)?.position ??
    PLAYERS_BY_ELEMENT_ID.get(elementId)?.position ??
    "MID"
  );
}

export function Fpl500Structure({
  holdings,
  structure,
}: {
  holdings: readonly Fpl500Holding[];
  structure: PortfolioStructure;
}) {
  const positions = ["GKP", "DEF", "MID", "FWD"] as const;
  const maximumSpend = Math.max(
    ...positions.map((position) => structure.positionalSpend[position].mean),
  );
  return (
    <section
      className="fpl500-structure"
      aria-labelledby="fpl500-structure-title"
    >
      <h3 id="fpl500-structure-title">Most common XI</h3>
      <p className="mono">
        Modal formation {structure.commonStartingXi.formation.join("-")} · the
        most-started player in each slot. It is a cohort composite, not one
        manager&rsquo;s team.
      </p>
      <div className="fpl500-common-pitch">
        {positions.map((position) => (
          <div className={`is-${position.toLowerCase()}`} key={position}>
            {structure.commonStartingXi.elementIds
              .filter(
                (elementId) => positionOf(elementId, holdings) === position,
              )
              .map((elementId) => (
                <span key={elementId}>{nameOf(elementId, holdings)}</span>
              ))}
          </div>
        ))}
      </div>

      <div className="fpl500-structure-grid">
        <section aria-labelledby="fpl500-pairs-title">
          <h4 id="fpl500-pairs-title">Goalkeeper pairs</h4>
          <ol className="fpl500-pairs">
            {structure.keeperPairings.slice(0, 8).map((pair) => (
              <li key={`${pair.starterElementId}-${pair.benchElementId}`}>
                <span>
                  {nameOf(pair.starterElementId, holdings)} +{" "}
                  {nameOf(pair.benchElementId, holdings)}
                </span>
                <strong className="mono">{fineShare.format(pair.share)}</strong>
              </li>
            ))}
          </ol>
        </section>
        <section aria-labelledby="fpl500-spend-title">
          <h4 id="fpl500-spend-title">Average squad spend</h4>
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
    </section>
  );
}
