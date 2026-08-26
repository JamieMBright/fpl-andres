import { useState } from "react";

import { oneDecimal, twoDecimal } from "../format";
import { kitForShortName } from "../kit/team-kits";
import type {
  Gw1Review,
  Gw1ReviewBand,
  Gw1ReviewPick,
} from "../state/gw1-review";
import { GW1_REVIEW } from "../state/gw1-review";
import { CeefaxShirt } from "./CeefaxShirt";
import { ScoreMarks, type ScoreLine } from "./ScoreMarks";

const POSITION_ROWS = [
  { code: "GKP", label: "Goalkeeper" },
  { code: "DEF", label: "Defenders" },
  { code: "MID", label: "Midfielders" },
  { code: "FWD", label: "Forwards" },
] as const;

const DEFENSIVE_BAR: Record<string, number> = { DEF: 10, MID: 12, FWD: 12 };

const BAND_WORDS: Record<Gw1ReviewBand, string> = {
  below: "below",
  as_projected: "as projected",
  above: "above",
  haul: "haul",
};

function scoreLine(pick: Gw1ReviewPick): ScoreLine {
  const actual = pick.actual;
  const bar = DEFENSIVE_BAR[pick.identity.position];
  const defensive =
    pick.identity.position === "GKP" || pick.identity.position === "DEF";
  return {
    goals: actual.goals,
    assists: actual.assists,
    cleanSheets: actual.minutes >= 60 ? actual.cleanSheets : 0,
    defensiveContribution:
      bar !== undefined && actual.defensiveContribution >= bar,
    goalsConceded: defensive ? actual.goalsConceded : 0,
    ownGoals: actual.ownGoals,
    penaltiesMissed: actual.penaltiesMissed,
    penaltiesSaved: actual.penaltiesSaved,
    redCards: actual.redCards,
    saves: actual.saves,
    yellowCards: actual.yellowCards,
    bonus: actual.bonus,
    haul: pick.band === "haul",
  };
}

function ReviewCard({
  onOpen,
  pick,
}: {
  readonly onOpen: (pick: Gw1ReviewPick) => void;
  readonly pick: Gw1ReviewPick;
}) {
  const kit = kitForShortName(pick.identity.club);
  const role = pick.isCaptain
    ? "captain"
    : pick.isViceCaptain
      ? "vice-captain"
      : null;
  const band = BAND_WORDS[pick.band];
  return (
    <button
      aria-label={`${pick.identity.name}${role ? `, ${role}` : ""}, ${String(
        pick.actualPoints,
      )} actual points, ${oneDecimal.format(pick.frozenXpts)} expected points, ${band}`}
      className="gw1-review-card"
      data-band={pick.band}
      onClick={() => onOpen(pick)}
      type="button"
    >
      <span className="gw1-review-shirt-wrap">
        {kit ? (
          <CeefaxShirt className="gw1-review-shirt" kit={kit} label={null} />
        ) : null}
        {role ? (
          <span className="gw1-review-armband" title={role}>
            {pick.isCaptain ? "C" : "V"}
          </span>
        ) : null}
      </span>
      <span className="gw1-review-name" translate="no">
        {pick.identity.name}
      </span>
      <span className="gw1-review-score mono">
        <b>{pick.actualPoints}</b>
        <span>{oneDecimal.format(pick.frozenXpts)} xPts</span>
      </span>
      <ScoreMarks line={scoreLine(pick)} />
      <span className="gw1-review-band mono">{band}</span>
    </button>
  );
}

function ReviewDetail({ pick }: { readonly pick: Gw1ReviewPick }) {
  const actual = pick.actual;
  const entries = [
    ["Minutes", actual.minutes],
    ["Started", actual.starts ? "yes" : "no"],
    ["Goals", actual.goals],
    ["Assists", actual.assists],
    ["Clean sheets", actual.cleanSheets],
    ["Saves", actual.saves],
    ["Goals conceded", actual.goalsConceded],
    ["Defensive actions", actual.defensiveContribution],
    ["Bonus", actual.bonus],
    ["Yellow cards", actual.yellowCards],
    ["Red cards", actual.redCards],
    ["Own goals", actual.ownGoals],
    ["Penalties saved", actual.penaltiesSaved],
    ["Penalties missed", actual.penaltiesMissed],
  ] as const;
  return (
    <div className="gw1-review-detail">
      <p className="eyebrow">{pick.identity.club} · settled line</p>
      <h3 id="gw1-review-detail-title" translate="no">
        {pick.identity.name}
      </h3>
      <dl>
        {entries.map(([term, value]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd className="mono">{value}</dd>
          </div>
        ))}
      </dl>
      <p>
        {twoDecimal.format(pick.frozenXpts)} frozen xPts. The shipped start
        field was P(60+): {Math.round(pick.startRateAsShipped * 100)}%.
      </p>
    </div>
  );
}

export function Gw1ReviewPitch({
  review = GW1_REVIEW,
}: {
  readonly review?: Gw1Review;
}) {
  const [selected, setSelected] = useState<Gw1ReviewPick | null>(null);
  const starters = review.picks.filter((pick) => pick.squadPosition <= 11);
  const bench = review.picks.filter((pick) => pick.squadPosition > 11);

  return (
    <section aria-labelledby="gw1-review-title" className="gw1-review">
      <div className="gw1-review-heading">
        <div>
          <p className="eyebrow">The freeze against the whistle</p>
          <h2 id="gw1-review-title">Gameweek 1, reviewed</h2>
        </div>
        <p className="gw1-review-total mono">
          <b>{review.team.points}</b>
          <span>points · {review.team.benchPoints} left on the bench</span>
        </p>
      </div>
      <p className="gw1-review-lede">
        Raw player points against the exact xPts frozen before the deadline.
        Raya&rsquo;s armband counts in the team total, not in his grade.
      </p>

      <div className="gw1-review-pitch">
        {POSITION_ROWS.map(({ code, label }) => {
          const row = starters.filter(
            (pick) => pick.identity.position === code,
          );
          if (row.length === 0) return null;
          return (
            <ul aria-label={label} className="gw1-review-row" key={code}>
              {row.map((pick) => (
                <li key={pick.elementId}>
                  <ReviewCard onOpen={setSelected} pick={pick} />
                </li>
              ))}
            </ul>
          );
        })}
      </div>

      <div className="gw1-review-bench">
        <p className="eyebrow">Bench, in order</p>
        <ul aria-label="Substitutes in order">
          {bench.map((pick, index) => (
            <li key={pick.elementId}>
              <span aria-hidden="true" className="gw1-review-bench-order mono">
                {index + 1}
              </span>
              <ReviewCard onOpen={setSelected} pick={pick} />
            </li>
          ))}
        </ul>
      </div>

      {selected ? (
        <section
          aria-labelledby="gw1-review-detail-title"
          className="gw1-review-detail-wrap"
        >
          <ReviewDetail pick={selected} />
          <button
            aria-label="Close player detail"
            onClick={() => setSelected(null)}
            type="button"
          >
            Close
          </button>
        </section>
      ) : null}

      <details className="gw1-review-table">
        <summary>Review as a table</summary>
        <div
          aria-label="Scrollable GW1 review table"
          className="squad-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users need to scroll the wide comparison table.
          tabIndex={0}
        >
          <table aria-label="GW1 review">
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">Actual</th>
                <th scope="col">Frozen xPts</th>
                <th scope="col">Grade</th>
              </tr>
            </thead>
            <tbody>
              {review.picks.map((pick) => (
                <tr key={pick.elementId}>
                  <th scope="row" translate="no">
                    {pick.identity.name}
                  </th>
                  <td className="mono">{pick.actualPoints}</td>
                  <td className="mono">{twoDecimal.format(pick.frozenXpts)}</td>
                  <td>{BAND_WORDS[pick.band]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <details className="gw1-review-source">
        <summary>Source trail</summary>
        <p>
          Model {review.canonicalModelVersion}, frozen{" "}
          {review.canonicalFrozenAt}. Settled FPL scores captured{" "}
          {review.evidence.liveCapturedAt}. Both sources are immutable and
          hashed in the review artifact.
        </p>
      </details>
    </section>
  );
}
