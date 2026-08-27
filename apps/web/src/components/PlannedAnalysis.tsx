import { InfoMarker } from "./InfoMarker";

/**
 * What will be on this page once a deadline has passed, drawn empty.
 *
 * "No data yet" tells a reader nothing about whether the thing is worth coming
 * back for. An axis with the right labels and no series on it tells them
 * exactly what they will get, and it is honest about having nothing: the frame
 * is real, the series is absent, and neither is pretending.
 *
 * Nothing here can be backfilled. FPL serves picks for the current season
 * only, so every one of these starts at the first deadline and fills forward.
 */

interface Planned {
  title: string;
  /** One line: what the chart answers. */
  answers: string;
  /** The technical note, behind a marker rather than on the page. */
  detail: string;
  /** Axis labels, so the empty frame is the real frame. */
  x: string;
  y: string;
  kind: "line" | "bars" | "stack";
}

const PLANNED: Planned[] = [
  {
    title: "Chips, cumulatively",
    answers: "How much of the cohort has spent each chip by now.",
    detail:
      "Four lines, one per chip, each the share of the cohort that has played it at least once. A chip is a once-a-season resource, so the interesting moment is the week a line jumps: that is the cohort agreeing on a wildcard window or a double gameweek, and it is visible before the week is scored.",
    x: "Gameweek",
    y: "Share of the cohort",
    kind: "line",
  },
  {
    title: "The armband, week by week",
    answers: "Who the cohort captained, and how much they agreed.",
    detail:
      "The plurality captain each week and the share who chose him. A week where ninety percent pick the same player separates no two strategies; the weeks worth reading are the contested ones, so those are marked. If almost every week is uncontested, the honest conclusion is that the armband is not where this cohort's edge lives.",
    x: "Gameweek",
    y: "Share on the plurality pick",
    kind: "bars",
  },
  {
    title: "Effective ownership against the field",
    answers: "What the cohort is exposed to that everyone else is not.",
    detail:
      "Ownership plus captaincy, minus the same figure for the whole game. Sixty percent owned and forty captained is a completely different exposure from sixty and two, which is why this is the number a transfer is decided on rather than raw ownership.",
    x: "Player",
    y: "Cohort EO minus field EO",
    kind: "bars",
  },
  {
    title: "In and out",
    answers: "Who the cohort bought and sold this week.",
    detail:
      "Net movement across the cohort between one deadline and the next, read from the squads rather than from FPL's transfer counters, so it is the cohort's own flow and not the game's.",
    x: "Player",
    y: "Net managers",
    kind: "bars",
  },
  {
    title: "Where the money goes",
    answers: "How the cohort splits a hundred million across the pitch.",
    detail:
      "Squad value by position, as a share. The shape of a template is mostly a budget decision, and this is the budget decision made visible before the picks are.",
    x: "Gameweek",
    y: "Share of squad value",
    kind: "stack",
  },
  {
    title: "Bench strength",
    answers: "How much the cohort leaves on the bench.",
    detail:
      "Points left unplayed each week, per manager. A cohort that benches little is playing a strong fifteen rather than a strong eleven, which is what makes Bench Boost worth a week rather than worth nothing.",
    x: "Gameweek",
    y: "Points on the bench",
    kind: "line",
  },
  {
    title: "Hits taken",
    answers: "How willing the cohort is to pay four points.",
    detail:
      "Share of the cohort taking at least one hit, and the mean cost. Consistently taking hits is a strategy, and knowing whether the people who finish well do it is worth more than any single week's transfer.",
    x: "Gameweek",
    y: "Share taking a hit",
    kind: "line",
  },
  {
    title: "How template they are",
    answers: "How much of the cohort's squad is the same squad.",
    detail:
      "The count of players held by more than half the cohort. A rising line is convergence, and convergence is the thing that makes a differential cheap.",
    x: "Gameweek",
    y: "Players held by over half",
    kind: "line",
  },
];

function Frame({ event, plan }: { event: number; plan: Planned }) {
  return (
    <figure className="planned-chart">
      <figcaption>
        {plan.title}
        <InfoMarker label={plan.title.toLowerCase()}>{plan.detail}</InfoMarker>
      </figcaption>
      <p className="planned-answers">{plan.answers}</p>
      <svg
        aria-hidden="true"
        className={`planned-frame is-${plan.kind}`}
        viewBox="0 0 240 96"
      >
        <line className="planned-axis" x1="30" x2="30" y1="6" y2="74" />
        <line className="planned-axis" x1="30" x2="232" y1="74" y2="74" />
        {[0, 1, 2, 3].map((step) => (
          <line
            className="planned-grid"
            key={step}
            x1="30"
            x2="232"
            y1={74 - step * 17}
            y2={74 - step * 17}
          />
        ))}
        <text className="planned-empty" x="131" y="44">
          awaiting gameweek {event}
        </text>
      </svg>
      <p className="planned-axes">
        <span className="mono">x</span> {plan.x} ·{" "}
        <span className="mono">y</span> {plan.y}
      </p>
    </figure>
  );
}

export function PlannedAnalysis({
  event,
  only,
}: {
  event: number;
  only?: readonly string[];
}) {
  const plans = only
    ? PLANNED.filter((plan) => only.includes(plan.title))
    : PLANNED;
  return (
    <div className="planned-grid-wrap">
      {plans.map((plan) => (
        <Frame event={event} key={plan.title} plan={plan} />
      ))}
    </div>
  );
}
