import type { PublicTeamPick } from "@fpl-andres/contracts";

import { projectionFor } from "../state/squad-projection";
import { money as sharedMoney } from "../format";

const POSITION_ROWS = [
  { code: "GKP", label: "Goalkeeper" },
  { code: "DEF", label: "Defenders" },
  { code: "MID", label: "Midfielders" },
  { code: "FWD", label: "Forwards" },
] as const;

type PositionCode = (typeof POSITION_ROWS)[number]["code"];

function money(valueTenths: number): string {
  return `${sharedMoney.format(valueTenths / 10)}m`;
}

/** Ceefax block shirt. Colour keys position, not club: I have no kit source. */
function Jersey({ position }: { position: PositionCode | null }) {
  return (
    <svg
      aria-hidden="true"
      className={`jersey jersey-${(position ?? "unknown").toLowerCase()}`}
      viewBox="0 0 32 32"
      focusable="false"
    >
      <path className="jersey-sleeve" d="M0 8h8v8H0z" />
      <path className="jersey-sleeve" d="M24 8h8v8h-8z" />
      <path className="jersey-body" d="M8 4h16v24H8z" />
      <path className="jersey-collar" d="M12 4h8v4h-8z" />
    </svg>
  );
}

function PlayerChip({ pick }: { pick: PublicTeamPick }) {
  const { identity } = pick;
  const armband = pick.isCaptain ? "C" : pick.isViceCaptain ? "V" : null;
  const projection = projectionFor(identity?.code);
  return (
    <div className="pitch-chip">
      <div className="pitch-chip-shirt">
        <Jersey position={identity ? identity.positionCode : null} />
        {armband ? (
          <span className="pitch-armband" aria-hidden="true">
            {armband}
          </span>
        ) : null}
      </div>
      <p className="pitch-chip-name" translate="no">
        {identity ? identity.webName : `#${pick.elementId}`}
      </p>
      <p className="pitch-chip-meta mono">
        <span translate="no">{identity ? identity.teamShortName : "—"}</span>
        <span aria-hidden="true"> · </span>
        <span>{identity ? money(identity.priceTenths) : "—"}</span>
      </p>
      <p className="pitch-chip-points mono">
        {projection ? (
          <>
            <span aria-hidden="true">
              {projection.expectedPoints.toFixed(1)}
            </span>
            <span className="visually-hidden">
              {projection.expectedPoints.toFixed(1)} points per match last
              season
            </span>
          </>
        ) : (
          <span className="pitch-chip-unknown">no record</span>
        )}
      </p>
      {armband ? (
        <p className="pitch-chip-role">
          {pick.isCaptain ? `Captain, ${pick.multiplier}×` : "Vice-captain"}
        </p>
      ) : null}
    </div>
  );
}

function formationOf(starters: PublicTeamPick[]): string {
  return POSITION_ROWS.slice(1)
    .map(
      ({ code }) =>
        starters.filter((pick) => pick.identity?.positionCode === code).length,
    )
    .join("-");
}

export function PitchView({ picks }: { picks: readonly PublicTeamPick[] }) {
  const ordered = [...picks].sort((a, b) => a.squadPosition - b.squadPosition);
  const starters = ordered.filter((pick) => pick.multiplier > 0);
  const bench = ordered.filter((pick) => pick.multiplier === 0);
  const resolved = starters.every((pick) => pick.identity !== null);
  const formation = formationOf(starters);

  return (
    <div className="pitch-view">
      <div className="pitch-caption">
        <p className="eyebrow">On the park</p>
        <p className="mono pitch-formation">
          {resolved ? formation : "formation unavailable"}
        </p>
      </div>
      <p className="pitch-legend">
        The figure on each shirt is that player&rsquo;s points per match last
        season, against an average opponent. It is a record, not a forecast for
        a fixture nobody has played.
      </p>

      <div className="pitch">
        {POSITION_ROWS.map(({ code, label }) => {
          const row = starters.filter(
            (pick) => pick.identity?.positionCode === code,
          );
          if (row.length === 0) return null;
          return (
            <ul className="pitch-row" key={code} aria-label={label}>
              {row.map((pick) => (
                <li key={pick.squadPosition}>
                  <PlayerChip pick={pick} />
                </li>
              ))}
            </ul>
          );
        })}
        {resolved ? null : (
          <ul className="pitch-row" aria-label="Unresolved starters">
            {starters
              .filter((pick) => pick.identity === null)
              .map((pick) => (
                <li key={pick.squadPosition}>
                  <PlayerChip pick={pick} />
                </li>
              ))}
          </ul>
        )}
      </div>

      <div className="pitch-bench-wrap">
        <p className="eyebrow">Bench, in order</p>
        <ul className="pitch-bench" aria-label="Substitutes in order">
          {bench.map((pick, index) => (
            <li key={pick.squadPosition}>
              <span className="pitch-bench-order mono" aria-hidden="true">
                {index + 1}
              </span>
              <PlayerChip pick={pick} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
