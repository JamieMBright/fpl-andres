import { useState } from "react";

import { kitForShortName } from "../kit/team-kits";
import type { Gw1Review, Gw1ReviewPick } from "../state/gw1-review";
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
    haul: false,
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
  return (
    <button
      aria-label={`${pick.identity.name}${role ? `, ${role}` : ""}, ${String(pick.actualPoints)} actual points`}
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
        <span>actual points</span>
      </span>
      <ScoreMarks line={scoreLine(pick)} />
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
      <p>{pick.actualPoints} actual points in the submitted team.</p>
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
  const recommendationCodes = new Set(
    review.recommendation.picks.map((pick) => pick.code),
  );
  const observedCodes = new Set(review.picks.map((pick) => pick.identity.code));
  const kept = [...recommendationCodes].filter((code) =>
    observedCodes.has(code),
  );
  const notSubmitted = review.recommendation.picks.filter(
    (pick) => !observedCodes.has(pick.code),
  );
  const notRecommended = review.picks.filter(
    (pick) => !recommendationCodes.has(pick.identity.code),
  );
  const recommendedCaptain = review.recommendation.picks.find(
    (pick) => pick.code === review.recommendation.captain,
  );

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
        Your submitted GW1 team, compared with the recommendation saved before
        the deadline. This record is historical and is not regenerated from
        today&rsquo;s model.
      </p>
      <div className="gw1-review-recommendation">
        <p className="eyebrow">What Andres recommended then</p>
        <p>
          You kept {kept.length} of 15 recommended players. The saved captain
          was {recommendedCaptain?.name ?? "unavailable"}.
        </p>
        {notSubmitted.length > 0 || notRecommended.length > 0 ? (
          <dl>
            <div>
              <dt>Recommended, not submitted</dt>
              <dd>{notSubmitted.map((pick) => pick.name).join(", ")}</dd>
            </div>
            <div>
              <dt>Submitted, not recommended</dt>
              <dd>
                {notRecommended.map((pick) => pick.identity.name).join(", ")}
              </dd>
            </div>
          </dl>
        ) : (
          <p>You submitted the recommended fifteen.</p>
        )}
      </div>
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
                <th scope="col">Recommendation</th>
              </tr>
            </thead>
            <tbody>
              {review.picks.map((pick) => (
                <tr key={pick.elementId}>
                  <th scope="row" translate="no">
                    {pick.identity.name}
                  </th>
                  <td className="mono">{pick.actualPoints}</td>
                  <td>
                    {recommendationCodes.has(pick.identity.code)
                      ? "recommended"
                      : "different"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <details className="gw1-review-source">
        <summary>Source trail</summary>
        <p>
          Recommendation frozen {review.canonicalFrozenAt}. Settled FPL scores
          captured {review.evidence.liveCapturedAt}. Both sources are immutable
          and hashed in the review artifact.
        </p>
      </details>
    </section>
  );
}
