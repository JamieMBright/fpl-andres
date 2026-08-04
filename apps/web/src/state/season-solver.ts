import {
  solveQuickPlan,
  type QuickSolverInput,
} from "@fpl-andres/quick-solver";

import inputs from "../data/season-inputs.json";

/**
 * Solve a whole season in the browser, one gameweek at a time.
 *
 * ## Why here and not on a server
 *
 * The plan is unique to the manager: their squad, their bank, their free
 * transfers, their remaining chips. It cannot be precomputed. It also cannot be
 * computed on request — twelve chained MILP windows take about a minute against
 * a fifteen-second function budget, and the exact 38-event solve does not
 * return at all.
 *
 * A browser has no timeout and no per-request cost, and the private half of the
 * state — free transfers and chips, which FPL does not publish — is already
 * only in localStorage. Solving here means it never has to leave.
 *
 * ## What it gives up
 *
 * `solveQuickPlan` is a bounded beam search with measured regret against HiGHS,
 * not a proof of optimality. Chaining it gameweek by gameweek is a greedy walk,
 * so it is myopic where the MILP was not.
 *
 * The lookahead below is what buys most of that back: a player's value at
 * gameweek t is his fixture-adjusted points for t discounted-summed over the
 * next few gameweeks, so a transfer is judged on the run it opens rather than
 * on Saturday alone. The repository has already measured that a horizon ladder
 * beats repeating a one-week projection, and that the gain grows with distance.
 */

const LOOKAHEAD = 5;
const LOOKAHEAD_DECAY = 0.75;

const WEEKLY_FREE_TRANSFERS = 1;
const MAX_FREE_TRANSFERS = 5;
/**
 * The opening gameweek is squad selection, not a transfer window: there is
 * nothing to spend and nothing to roll, and the first award lands for gameweek
 * two. A plan starting at gameweek one must not reach gameweek two holding two.
 */
const SEASON_OPENER = 1;

type PositionCode = "GKP" | "DEF" | "MID" | "FWD";

const SQUAD_SHAPE = [
  { positionId: 1, squadCount: 2, lineupMinimum: 1, lineupMaximum: 1 },
  { positionId: 2, squadCount: 5, lineupMinimum: 3, lineupMaximum: 5 },
  { positionId: 3, squadCount: 5, lineupMinimum: 2, lineupMaximum: 5 },
  { positionId: 4, squadCount: 3, lineupMinimum: 1, lineupMaximum: 3 },
];

export interface SolverPlayer {
  id: number;
  code: number;
  name: string;
  position: PositionCode;
  positionId: number;
  club: string;
  teamId: number;
  priceTenths: number;
  basePoints: number;
  startRate: number;
}

interface FixtureLadder {
  defensive: number[];
  attacking: number[];
}

const LADDER = inputs.fixtureLadder as Record<string, FixtureLadder>;
const OPPONENTS = inputs.opponents as Record<string, string[][]>;
const DIFFICULTY = inputs.fixtureDifficulty as Record<
  string,
  (number | null)[]
>;
const PLAYERS = inputs.players as SolverPlayer[];
const EVENTS = inputs.events as number[];
const DEADLINES = inputs.deadlines as string[];

/**
 * A defender's return depends on the opponent's attack, an attacker's on their
 * defence, so the two read different rungs of the same ladder.
 */
function pointsAt(player: SolverPlayer, eventIndex: number): number {
  const ladder = LADDER[player.club];
  if (!ladder) return 0;
  const defensive = player.positionId === 1 || player.positionId === 2;
  const multiplier = defensive
    ? ladder.defensive[eventIndex]
    : ladder.attacking[eventIndex];
  return multiplier === undefined ? 0 : player.basePoints * multiplier;
}

function lookaheadPoints(player: SolverPlayer, eventIndex: number): number {
  let total = 0;
  for (let ahead = 0; ahead < LOOKAHEAD; ahead += 1) {
    const index = eventIndex + ahead;
    if (index >= EVENTS.length) break;
    total += pointsAt(player, index) * LOOKAHEAD_DECAY ** ahead;
  }
  return total;
}

export interface SolveStart {
  /** Element ids currently held, and what they would sell for. */
  squad: { elementId: number; sellingPriceTenths: number }[];
  bankTenths: number;
  availableFreeTransfers: number;
  /** First gameweek to plan. Everything from here to 38 is solved. */
  fromEvent: number;
}

export interface SolvedGameweek {
  event: number;
  deadline: string;
  confidence: "firm" | "projected" | "provisional";
  starters: SolverPlayer[];
  bench: SolverPlayer[];
  captain: SolverPlayer;
  viceCaptain: SolverPlayer;
  transfersIn: SolverPlayer[];
  transfersOut: SolverPlayer[];
  opponents: Record<string, string[]>;
  difficulty: Record<string, number | null>;
  expected: Record<string, number>;
  paidTransfers: number;
  transferCostPoints: number;
  projectedPoints: number;
  netExpectedPoints: number;
  bankAfterTenths: number;
  freeTransfersBefore: number;
}

const BY_ID = new Map(PLAYERS.map((player) => [player.id, player]));

function look(elementId: number): SolverPlayer {
  const found = BY_ID.get(elementId);
  if (!found) throw new Error(`solver returned unknown element ${elementId}`);
  return found;
}

const SHEET_ORDER = ["GKP", "DEF", "MID", "FWD"];

function inSheetOrder(players: SolverPlayer[]): SolverPlayer[] {
  return [...players].sort(
    (left, right) =>
      SHEET_ORDER.indexOf(left.position) -
        SHEET_ORDER.indexOf(right.position) ||
      left.name.localeCompare(right.name),
  );
}

function confidenceFor(ahead: number): SolvedGameweek["confidence"] {
  if (ahead < 1) return "firm";
  if (ahead < 8) return "projected";
  return "provisional";
}

const HASH = `sha256:${"0".repeat(64)}`;

/** FPL publishes neither the weekly award nor the hit, so both are cited. */
const RULES_REFERENCE = "FPL rules page, Transfers section, read 2026-08-03";

/**
 * Solves gameweek by gameweek, yielding each as it lands.
 *
 * A generator rather than an array because the whole point is that the first
 * gameweek is on screen before the last one has been thought about.
 */
export function* solveSeason(
  start: SolveStart,
): Generator<SolvedGameweek, void, undefined> {
  const firstIndex = EVENTS.indexOf(start.fromEvent);
  if (firstIndex < 0) {
    throw new Error(
      `gameweek ${start.fromEvent} is not in the published season`,
    );
  }

  let squad = start.squad.map((held) => ({ ...held }));
  let bank = start.bankTenths;
  let free =
    start.fromEvent === SEASON_OPENER ? 0 : start.availableFreeTransfers;

  for (let index = firstIndex; index < EVENTS.length; index += 1) {
    const event = EVENTS[index];
    const deadline = DEADLINES[index];
    if (event === undefined || deadline === undefined) break;

    const players = PLAYERS.map((player) => ({
      elementId: player.id,
      teamId: player.teamId,
      positionId: player.positionId,
      buyPriceTenths: player.priceTenths,
      expectedPoints: lookaheadPoints(player, index),
      evidenceLevel: "inferred" as const,
      dataAvailableAt: deadline,
      sourceHashes: [HASH],
    }));

    const input: QuickSolverInput = {
      season: "2026-27",
      event,
      objective: "expected_value",
      priceScenario: "current_prices",
      chipScenario: "none",
      predictionCutoff: deadline,
      players,
      currentSquad: squad,
      bankTenths: bank,
      availableFreeTransfers: free,
      stateEvidence: {
        publicStateAsOf: deadline,
        publicDataAvailableAt: deadline,
        overridesUpdatedAt: deadline,
        publicSourceHashes: [HASH],
        managerOverridesHash: HASH,
      },
      rules: {
        squadSize: 15,
        lineupSize: 11,
        clubLimit: 3,
        transferCap: 15,
        weeklyFreeTransfers: 1,
        maximumFreeTransfers: 5,
        transferCostPoints: 4,
        transferRulesSourceReference: RULES_REFERENCE,
        positions: SQUAD_SHAPE,
        dataAvailableAt: deadline,
        publishedRulesHash: HASH,
        transferRulesHash: HASH,
      },
    };

    const solved = solveQuickPlan(input, {
      beamWidth: 12,
      candidateLimitPerPosition: 8,
      maxTransfers: 2,
    });

    const freeBefore = free;
    // The published points are the lookahead sum, which is not what this
    // gameweek is worth. Rescore the chosen eleven on the gameweek itself.
    const starters = solved.starterElementIds.map(look);
    const captain = look(solved.captainElementId);
    const gameweekPoints =
      starters.reduce((total, player) => total + pointsAt(player, index), 0) +
      pointsAt(captain, index);

    const squadNow = solved.squadElementIds.map(look);
    const opponents: Record<string, string[]> = {};
    const difficulty: Record<string, number | null> = {};
    const expected: Record<string, number> = {};
    for (const player of squadNow) {
      opponents[player.club] ??= OPPONENTS[player.club]?.[index] ?? [];
      difficulty[player.club] ??= DIFFICULTY[player.club]?.[index] ?? null;
      expected[String(player.code)] =
        Math.round(pointsAt(player, index) * 100) / 100;
    }

    yield {
      event,
      deadline,
      confidence: confidenceFor(index - firstIndex),
      starters: inSheetOrder(starters),
      bench: solved.benchElementIds.map(look),
      captain,
      viceCaptain: look(solved.viceCaptainElementId),
      transfersIn: solved.transfersIn.map(look),
      transfersOut: solved.transfersOut.map(look),
      opponents,
      difficulty,
      expected,
      paidTransfers: solved.paidTransfers,
      transferCostPoints: solved.transferCostPoints,
      projectedPoints: Math.round(gameweekPoints * 100) / 100,
      netExpectedPoints:
        Math.round((gameweekPoints - solved.transferCostPoints) * 100) / 100,
      bankAfterTenths: solved.bankAfterTenths,
      freeTransfersBefore: freeBefore,
    };

    const priceOf = new Map(
      PLAYERS.map((player) => [player.id, player.priceTenths]),
    );
    squad = solved.squadElementIds.map((elementId) => ({
      elementId,
      sellingPriceTenths: priceOf.get(elementId) ?? 0,
    }));
    bank = solved.bankAfterTenths;
    // Gameweek 1 is squad selection, not a transfer window: FPL charges nothing
    // for it and awards the first free transfer for gameweek 2. Carrying the
    // opening allowance forward would hand the plan free transfers it never
    // earned.
    free =
      event === SEASON_OPENER
        ? WEEKLY_FREE_TRANSFERS
        : Math.min(
            MAX_FREE_TRANSFERS,
            Math.max(0, free - solved.transfersIn.length) +
              WEEKLY_FREE_TRANSFERS,
          );
  }
}

export const SEASON_EVENTS = EVENTS;
export const SEASON_PLAYERS = PLAYERS;

const BY_CODE = new Map(PLAYERS.map((player) => [player.code, player]));

/**
 * Build a starting state from player codes.
 *
 * Codes are what the published artifacts carry, because FPL reissues element
 * ids every season; the solver works in element ids because that is what the
 * solver contract takes. Passing one where the other is meant produces an empty
 * squad and a solve that never yields, which is exactly what it did.
 */
export function startFromCodes(
  codes: readonly number[],
  options: {
    bankTenths: number;
    availableFreeTransfers: number;
    fromEvent: number;
  },
): SolveStart | null {
  const squad = codes
    .map((code) => BY_CODE.get(code))
    .filter((player): player is SolverPlayer => player !== undefined)
    .map((player) => ({
      elementId: player.id,
      sellingPriceTenths: player.priceTenths,
    }));

  return squad.length === codes.length ? { ...options, squad } : null;
}

const BY_ELEMENT_ID = new Map(PLAYERS.map((player) => [player.id, player]));

/**
 * The same, from a manager's own squad.
 *
 * FPL's team endpoint returns element ids, not codes, so this is the door a
 * real manager comes through. A squad the solver does not recognise in full
 * yields null rather than a solve for fourteen players.
 */
export function startFromElementIds(
  elementIds: readonly number[],
  options: {
    bankTenths: number;
    availableFreeTransfers: number;
    fromEvent: number;
  },
): SolveStart | null {
  const squad = elementIds
    .map((elementId) => BY_ELEMENT_ID.get(elementId))
    .filter((player): player is SolverPlayer => player !== undefined)
    .map((player) => ({
      elementId: player.id,
      sellingPriceTenths: player.priceTenths,
    }));

  return squad.length === elementIds.length ? { ...options, squad } : null;
}
