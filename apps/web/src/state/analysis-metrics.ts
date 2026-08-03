import { DEFCON_THRESHOLD, type AnalysisPlayer } from "./analysis-pool";

/**
 * Every axis the scatter can plot, and what each one is worth knowing.
 *
 * A metric returns `null` rather than zero when a player has no route to it. A
 * goalkeeper's defensive contributions are not zero, they are not a thing, and
 * a keeper sitting on the origin next to a defender who never tackles would say
 * something false about both.
 */

export type MetricGroup =
  "Points" | "Attack" | "Shot quality" | "Defence" | "Market";

/**
 * Which season a number belongs to.
 *
 * `record` is the completed season the vintage guard identified. `market` is
 * today: what the game charges for him now and who owns him now. Mixing them on
 * one chart is the point — buying last season's record at this season's price
 * is the whole game — but the axis labels have to say which is which.
 */
export type MetricVintage = "record" | "market";

export interface Metric {
  id: string;
  label: string;
  group: MetricGroup;
  vintage: MetricVintage;
  /** One line, in the tooltip and beside the axis picker. */
  explains: string;
  value: (player: AnalysisPlayer) => number | null;
  format: (value: number) => string;
  /** False where a low number is the good one, so quadrant labels read right. */
  higherIsBetter: boolean;
  /** Log scale is offered only where the spread is genuinely multiplicative. */
  allowLog: boolean;
}

const one = (value: number) => value.toFixed(1);
const two = (value: number) => value.toFixed(2);
const whole = (value: number) => String(Math.round(value));
const percent = (value: number) => `${value.toFixed(1)}%`;

function per90(total: number, nineties: number): number | null {
  return nineties > 0 ? total / nineties : null;
}

export const METRICS: Metric[] = [
  {
    id: "totalPoints",
    label: "Total points",
    group: "Points",
    vintage: "record",
    explains: "Everything he scored, appearance points and all.",
    value: (player) => player.totalPoints,
    format: whole,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "pointsPer90",
    label: "Points per 90",
    group: "Points",
    vintage: "record",
    explains: "His rate, so a squad player is judged beside an ever-present.",
    value: (player) => per90(player.totalPoints, player.ninetiesPlayed),
    format: two,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "pointsPerMillion",
    label: "Points per \u00a31m",
    group: "Points",
    vintage: "market",
    explains: "Last season's points at this season's price. The cheap route.",
    value: (player) => player.totalPoints / (player.priceTenths / 10),
    format: one,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "bonus",
    label: "Bonus points",
    group: "Points",
    vintage: "record",
    explains: "The BPS reward. Tracks who the algorithm already likes.",
    value: (player) => player.bonus,
    format: whole,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "minutes",
    label: "Minutes played",
    group: "Points",
    vintage: "record",
    explains: "The one that decides all the others. No minutes, no points.",
    value: (player) => player.minutes,
    format: whole,
    higherIsBetter: true,
    allowLog: false,
  },

  {
    id: "xGI",
    label: "xGI",
    group: "Attack",
    vintage: "record",
    explains:
      "Expected goals and assists together. What the chances were worth.",
    value: (player) => player.expectedGoalInvolvements,
    format: two,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "xGIPer90",
    label: "xGI per 90",
    group: "Attack",
    vintage: "record",
    explains: "Expected involvement per match played, not per season survived.",
    value: (player) =>
      per90(player.expectedGoalInvolvements, player.ninetiesPlayed),
    format: two,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "xG",
    label: "xG",
    group: "Attack",
    vintage: "record",
    explains: "Expected goals, penalties included.",
    value: (player) => player.expectedGoals,
    format: two,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "xA",
    label: "xA",
    group: "Attack",
    vintage: "record",
    explains: "Expected assists. Credits the pass, not the finish.",
    value: (player) => player.expectedAssists,
    format: two,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "ictIndex",
    label: "ICT index",
    group: "Attack",
    vintage: "record",
    explains: "FPL's own composite of influence, creativity and threat.",
    value: (player) => player.ictIndex,
    format: one,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "threat",
    label: "Threat",
    group: "Attack",
    vintage: "record",
    explains: "Goal-scoring danger, weighted by where he shoots from.",
    value: (player) => player.threat,
    format: one,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "creativity",
    label: "Creativity",
    group: "Attack",
    vintage: "record",
    explains: "Chance creation, weighted by how good the chance was.",
    value: (player) => player.creativity,
    format: one,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "influence",
    label: "Influence",
    group: "Attack",
    vintage: "record",
    explains:
      "Match-affecting actions. Defenders score better here than you expect.",
    value: (player) => player.influence,
    format: one,
    higherIsBetter: true,
    allowLog: false,
  },

  /*
   * Understat, joined on FPL code. These are the columns FPL does not publish,
   * and they answer questions its own expected-goals number cannot.
   */
  {
    id: "npxGPer90",
    label: "Non-penalty xG per 90",
    group: "Shot quality",
    vintage: "record",
    explains:
      "His expected goals with the penalties taken out. Open-play danger.",
    value: (player) =>
      player.understat
        ? per90(player.understat.nonPenaltyExpectedGoals, player.ninetiesPlayed)
        : null,
    format: two,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "penaltyShare",
    label: "Penalty share of xG",
    group: "Shot quality",
    vintage: "record",
    explains:
      "How much of his expected goals came from the spot. High means you are buying a job, not a player.",
    value: (player) => player.understat?.penaltyShare ?? null,
    format: (value) => `${(value * 100).toFixed(0)}%`,
    higherIsBetter: false,
    allowLog: false,
  },
  {
    id: "xGAtRiskPer90",
    label: "Penalty xG at risk per 90",
    group: "Shot quality",
    vintage: "record",
    explains: "What he loses per match if someone else takes the penalties.",
    value: (player) => player.understat?.expectedGoalsAtRiskPer90 ?? null,
    format: two,
    higherIsBetter: false,
    allowLog: false,
  },
  {
    id: "shotsPer90",
    label: "Shots per 90",
    group: "Shot quality",
    vintage: "record",
    explains: "Volume. Survives a cold spell better than conversion does.",
    value: (player) => player.understat?.shotsPer90 ?? null,
    format: two,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "xGPerShot",
    label: "xG per shot",
    group: "Shot quality",
    vintage: "record",
    explains:
      "Where he shoots from. High volume plus low quality is a hopeful.",
    value: (player) => player.understat?.expectedGoalsPerShot ?? null,
    format: (value) => value.toFixed(3),
    higherIsBetter: true,
    allowLog: false,
  },

  /*
   * Defensive contributions. Two points a match, on a threshold, and worth 7.5%
   * of everything FPL paid out last season -- more than assists. The market
   * still prices these players as if they were only defenders.
   */
  {
    id: "defconPer90",
    label: "DefCon per 90",
    group: "Defence",
    vintage: "record",
    explains:
      "Clearances, blocks, interceptions and tackles per match, plus recoveries outside defence.",
    value: (player) =>
      player.defconBarRatio === null ? null : player.defensiveContributionPer90,
    format: two,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "defconBarRatio",
    label: "DefCon share of the bar",
    group: "Defence",
    vintage: "record",
    explains:
      "His per-90 count against the threshold he needs. One means he averages the bar; it is not a claim he clears it weekly.",
    value: (player) => player.defconBarRatio,
    format: two,
    higherIsBetter: true,
    allowLog: false,
  },
  {
    id: "defconTotal",
    label: "DefCon actions",
    group: "Defence",
    vintage: "record",
    explains: "The raw season count, before any threshold is applied.",
    value: (player) =>
      player.defconBarRatio === null ? null : player.defensiveContribution,
    format: whole,
    higherIsBetter: true,
    allowLog: false,
  },

  {
    id: "price",
    label: "Price",
    group: "Market",
    vintage: "market",
    explains: "What the game charges for him today.",
    value: (player) => player.priceTenths / 10,
    format: (value) => `\u00a3${value.toFixed(1)}m`,
    higherIsBetter: false,
    allowLog: true,
  },
  {
    id: "ownership",
    label: "Ownership",
    group: "Market",
    vintage: "market",
    explains: "Share of squads picking him right now.",
    value: (player) => player.ownership,
    format: percent,
    higherIsBetter: false,
    allowLog: true,
  },
];

const BY_ID = new Map(METRICS.map((metric) => [metric.id, metric]));

export function metric(id: string): Metric | null {
  return BY_ID.get(id) ?? null;
}

/** The default view: the case the page exists to make. */
export const DEFAULT_X_METRIC = "defconPer90";
export const DEFAULT_Y_METRIC = "xGIPer90";
export const DEFAULT_SIZE_METRIC = "ownership";

/**
 * The bar a position has to clear, for the reference line on a DefCon axis.
 *
 * Returned per position rather than as one number because there is no single
 * DefCon threshold: a defender needs ten, everyone else twelve, and a keeper
 * has no route to them.
 */
export function defconThresholdFor(
  metricId: string,
  position: string,
): number | null {
  if (metricId === "defconPer90") return DEFCON_THRESHOLD[position] ?? null;
  if (metricId === "defconBarRatio") {
    return DEFCON_THRESHOLD[position] === undefined ? null : 1;
  }
  return null;
}
