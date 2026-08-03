import plan from "../data/season-plan.json";

/**
 * The published season plan.
 *
 * Static import, but only ever from a lazily-loaded route, so the 33 kB lands
 * in that route's chunk rather than the entry bundle.
 */

export type Confidence = "firm" | "projected" | "provisional";

export interface PlanPlayer {
  code: number;
  name: string;
  position: string;
  club: string;
  priceTenths: number;
}

export interface PlanGameweek {
  event: number;
  deadline: string;
  confidence: Confidence;
  starters: readonly PlanPlayer[];
  bench: readonly PlanPlayer[];
  captain: PlanPlayer;
  viceCaptain: PlanPlayer;
  transfersIn: readonly PlanPlayer[];
  transfersOut: readonly PlanPlayer[];
  freeTransfersBefore: number;
  paidTransfers: number;
  transferCostPoints: number;
  projectedPoints: number;
  netExpectedPoints: number;
  bankAfterTenths: number;
}

export interface SeasonPlan {
  season: string;
  recordSeason: string;
  generatedAt: string;
  basis: string;
  rulesReference: string;
  weeklyFreeTransfers: number;
  transferCostPoints: number;
  poolSize: number;
  windowsSolved: number;
  netExpectedPoints: number;
  chipWindows: readonly number[];
  gameweeks: readonly PlanGameweek[];
}

const PLAYERS = plan.players as Record<
  string,
  { name: string; position: string; club: string; priceTenths: number }
>;

function resolve(code: number): PlanPlayer {
  const found = PLAYERS[String(code)];
  if (!found) {
    // The artifact is generated with the table and the references in one pass,
    // so a miss means the file was hand-edited or truncated.
    throw new Error(`season plan references player ${code} with no entry`);
  }
  return { code, ...found };
}

function resolveAll(codes: readonly number[]): PlanPlayer[] {
  return codes.map(resolve);
}

const SHEET_ORDER = ["GKP", "DEF", "MID", "FWD"];

/** Team-sheet order. The solver returns element id order, which reads as noise. */
function inSheetOrder(players: PlanPlayer[]): PlanPlayer[] {
  return [...players].sort(
    (left, right) =>
      SHEET_ORDER.indexOf(left.position) -
        SHEET_ORDER.indexOf(right.position) ||
      left.name.localeCompare(right.name),
  );
}

export function readSeasonPlan(): SeasonPlan {
  return {
    season: plan.season,
    recordSeason: plan.recordSeason,
    generatedAt: plan.generatedAt,
    basis: plan.basis,
    rulesReference: plan.rulesReference,
    weeklyFreeTransfers: plan.weeklyFreeTransfers,
    transferCostPoints: plan.transferCostPoints,
    poolSize: plan.poolSize,
    windowsSolved: plan.windowsSolved,
    netExpectedPoints: plan.netExpectedPoints,
    chipWindows: plan.chipWindows,
    gameweeks: plan.gameweeks.map((week) => ({
      event: week.event,
      deadline: week.deadline,
      confidence: week.confidence as Confidence,
      starters: inSheetOrder(resolveAll(week.starters)),
      // Kept as published: the solver orders the bench by expected points, so
      // position one is the likeliest to earn. Sorting it would destroy that.
      bench: resolveAll(week.bench),
      captain: resolve(week.captain),
      viceCaptain: resolve(week.viceCaptain),
      transfersIn: resolveAll(week.transfersIn),
      transfersOut: resolveAll(week.transfersOut),
      freeTransfersBefore: week.freeTransfersBefore,
      paidTransfers: week.paidTransfers,
      transferCostPoints: week.transferCostPoints,
      projectedPoints: week.projectedPoints,
      netExpectedPoints: week.netExpectedPoints,
      bankAfterTenths: week.bankAfterTenths,
    })),
  };
}

/** What each band means, in one line, shown beside the plan rather than buried. */
export const CONFIDENCE_NOTE: Record<Confidence, string> = {
  firm: "Prices, availability and fixtures all observed. Only the points are projected.",
  projected:
    "Inside the horizon where a multi-week projection has been measured to beat a one-week one.",
  provisional:
    "Fixtures are known; the squad by then is not. Read the shape, not the specific name.",
};
