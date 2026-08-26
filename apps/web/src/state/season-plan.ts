import plan from "../data/season-plan.json";
import {
  requireArtifactVersion,
  SEASON_PLAN_SCHEMA_VERSION,
} from "./artifact-version";
import {
  fixtureEvidenceForClubs,
  type FixtureEvidence,
} from "./fixture-evidence";

requireArtifactVersion("season-plan.json", plan, SEASON_PLAN_SCHEMA_VERSION);

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
  /** Club short name to who they play, as "HUL (A)". Empty on a blank. */
  opponents: Readonly<Record<string, readonly string[]>>;
  /** Club short name to how hard the week is, one to five. Null on a blank. */
  difficulty: Readonly<Record<string, number | null>>;
  fixtureEvidence: Readonly<Record<string, readonly FixtureEvidence[]>>;
  /** Player code to what he is worth this gameweek. */
  expected: Readonly<Record<string, number>>;
  /** The same week on his best afternoon. */
  ceiling: Readonly<Record<string, number>>;
  freeTransfersBefore: number;
  paidTransfers: number;
  transferCostPoints: number;
  projectedPoints: number;
  netExpectedPoints: number;
  bankAfterTenths: number;
  /** Set when a chip rewrote this week's fifteen. */
  chip?: string | undefined;
  /** True when the squad is handed back afterwards, as on a Free Hit. */
  revertsAfter?: boolean | undefined;
  /** The fifteen the plan resumes from once a reverting chip has been played. */
  revertsTo?: readonly PlanPlayer[] | undefined;
}

export interface ChipCall {
  /** Null when nothing in the season justifies playing it. */
  event: number | null;
  chip: string;
  /** Which half of the season this copy belongs to. Every chip comes twice. */
  half: string;
  /** Expected points playing it adds, over not playing it. */
  gain: number;
  note: string;
}

export interface DataGaps {
  clubsWithoutRecord: readonly string[];
  clubsInPool: number;
  clubsInLeague: number;
}

export interface SeasonPlan {
  modelVersion: string;
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
  chips: readonly ChipCall[];
  dataGaps: DataGaps;
  gameweeks: readonly PlanGameweek[];
}

const PLAYERS = plan.players as Record<
  string,
  {
    name: string;
    position: string;
    club: string;
    priceTenths: number;
    squadNumber: number | null;
  }
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

export interface PlanSwap {
  out: PlanPlayer;
  in: PlanPlayer;
}

/**
 * Pair the week's outgoing and incoming players by position.
 *
 * FPL records a week's moves as two independent lists, and pairing them by
 * index reads a goalkeeper out against a defender in whenever the solver
 * happens to order them differently. A legal squad keeps its position counts,
 * so the two lists always match as a multiset and every move can be shown as
 * the like-for-like swap it actually was.
 */
export function pairTransfers(
  outgoing: readonly PlanPlayer[],
  incoming: readonly PlanPlayer[],
): PlanSwap[] {
  const available = [...incoming];
  const swaps: PlanSwap[] = [];
  const unmatched: PlanPlayer[] = [];
  for (const out of outgoing) {
    const index = available.findIndex(
      (candidate) => candidate.position === out.position,
    );
    if (index === -1) {
      unmatched.push(out);
      continue;
    }
    swaps.push({ out, in: available.splice(index, 1)[0]! });
  }
  // Only reachable if the plan ever broke its own squad shape. Pair what is
  // left in order rather than dropping a move off the page.
  for (const out of unmatched) {
    const next = available.shift();
    if (next) swaps.push({ out, in: next });
  }
  return swaps;
}

export function readSeasonPlan(): SeasonPlan {
  return {
    modelVersion: (plan as unknown as { modelVersion: string }).modelVersion,
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
    chips: plan.chips,
    dataGaps: plan.dataGaps,
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
      opponents: week.opponents,
      difficulty: week.difficulty,
      fixtureEvidence: fixtureEvidenceForClubs(
        Object.keys(week.opponents),
        week.event,
      ),
      expected: week.expected,
      ceiling: week.ceiling,
      freeTransfersBefore: week.freeTransfersBefore,
      paidTransfers: week.paidTransfers,
      transferCostPoints: week.transferCostPoints,
      projectedPoints: week.projectedPoints,
      netExpectedPoints: week.netExpectedPoints,
      bankAfterTenths: week.bankAfterTenths,
      chip: week.chip,
      revertsAfter: week.revertsAfter,
      revertsTo: week.revertsTo ? resolveAll(week.revertsTo) : undefined,
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
