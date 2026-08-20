import {
  solveQuickPlan,
  type QuickSolverInput,
} from "@fpl-andres/quick-solver";

import inputs from "../data/season-inputs.json";
import {
  requireArtifactVersion,
  SEASON_INPUTS_SCHEMA_VERSION,
} from "./artifact-version";

requireArtifactVersion(
  "season-inputs.json",
  inputs,
  SEASON_INPUTS_SCHEMA_VERSION,
);

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

/**
 * The rules, read rather than retyped.
 *
 * They were literals here with a prose citation and no timestamp, which is the
 * one thing this repository says it never does with a controlling FPL rule.
 * `publish_season_inputs.py` writes them beside the players, from the same
 * `RulesSnapshot` the Python solvers take.
 */
interface PublishedRules {
  weeklyFreeTransfers: number;
  maximumFreeTransfers: number;
  transferCostPoints: number;
  transferCap: number;
  squadSize: number;
  lineupSize: number;
  clubLimit: number;
  positions: {
    positionId: number;
    squadCount: number;
    lineupMinimum: number;
    lineupMaximum: number;
  }[];
  sourceReference: string;
  dataAvailableAt: string;
  playableStartRate: number;
  transferMarginPoints: number;
}

const RULES = inputs.rules as PublishedRules;

const WEEKLY_FREE_TRANSFERS = RULES.weeklyFreeTransfers;
const MAX_FREE_TRANSFERS = RULES.maximumFreeTransfers;
/**
 * The opening gameweek is squad selection, not a transfer window: there is
 * nothing to spend and nothing to roll, and the first award lands for gameweek
 * two. A plan starting at gameweek one must not reach gameweek two holding two.
 */
const SEASON_OPENER = 1;

type PositionCode = "GKP" | "DEF" | "MID" | "FWD";

const SQUAD_SHAPE = RULES.positions;

/**
 * The eight published routes, and what a fixture does to each.
 *
 * Partial: a route worth nothing is omitted from the artifact rather than
 * written as a zero, which is most of them for most players.
 */
/**
 * The published routes, and what a fixture does to each.
 *
 * Partial: a route worth nothing is omitted from the artifact rather than
 * written as a zero, which is most of them for most players.
 */
export type PlayerRoutes = Partial<{
  appearance: number;
  attacking: number;
  cleanSheet: number;
  bonus: number;
  saves: number;
  conceding: number;
  yellowCards: number;
  redCards: number;
  ownGoals: number;
  penaltiesMissed: number;
  defensiveContribution: number;
}>;

/** The same set, priced for one gameweek. A route worth nothing is a zero. */
export type EventRoutes = Required<PlayerRoutes>;

const NO_ROUTES: EventRoutes = {
  appearance: 0,
  attacking: 0,
  cleanSheet: 0,
  bonus: 0,
  saves: 0,
  conceding: 0,
  yellowCards: 0,
  redCards: 0,
  ownGoals: 0,
  penaltiesMissed: 0,
  defensiveContribution: 0,
};

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
  routes: PlayerRoutes;
  startRate: number;
  /** False where every number above is a prior for his role, not a measurement. */
  rated?: boolean;
  /** 1 is his club's most expensive player in this position. */
  depthRank?: number;
}

interface FixtureLadder {
  defensive: number[];
  attacking: number[];
  saves: number[];
  conceding: number[];
  defensiveContribution: number[];
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
const BONUS_OVERRIDES =
  (
    inputs as unknown as {
      bonusOverrides?: Record<string, Record<string, number>>;
    }
  ).bonusOverrides ?? {};

type MarketCarryValues = readonly [
  anchorIndex: number,
  baselineStartRate: number,
  participationRatio: number,
  baselineAttacking: number,
  baselineYellowCards: number,
  baselineRedCards: number,
];

const MARKET_CARRY = (
  inputs as unknown as {
    marketCarry: {
      halfLifeGameweeks: number;
      players: Record<string, MarketCarryValues>;
    };
  }
).marketCarry;

export function marketCarryWeight(
  eventIndex: number,
  anchorIndex: number,
  halfLifeGameweeks: number,
): number {
  if (eventIndex < anchorIndex) return 0;
  if (halfLifeGameweeks <= 0) return eventIndex === anchorIndex ? 1 : 0;
  return 0.5 ** ((eventIndex - anchorIndex) / halfLifeGameweeks);
}

export function marketValueAtEvent(
  quoted: number,
  baseline: number,
  eventIndex: number,
  anchorIndex: number,
  halfLifeGameweeks: number,
): number {
  const weight = marketCarryWeight(eventIndex, anchorIndex, halfLifeGameweeks);
  return baseline + (quoted - baseline) * weight;
}

function routesAtEvent(player: SolverPlayer, eventIndex: number): PlayerRoutes {
  const carry = MARKET_CARRY.players[String(player.id)];
  if (!carry) return player.routes;
  const [
    anchorIndex,
    _baselineStartRate,
    participationRatio,
    baselineAttacking,
    baselineYellowCards,
    baselineRedCards,
  ] = carry;
  const baselineFor = (route: keyof PlayerRoutes): number => {
    const current = player.routes[route] ?? 0;
    if (route === "attacking") return baselineAttacking;
    if (route === "yellowCards") return baselineYellowCards;
    if (route === "redCards") return baselineRedCards;
    return participationRatio > 0 ? current / participationRatio : current;
  };
  const carried = (route: keyof PlayerRoutes): number =>
    marketValueAtEvent(
      player.routes[route] ?? 0,
      baselineFor(route),
      eventIndex,
      anchorIndex,
      MARKET_CARRY.halfLifeGameweeks,
    );
  return {
    appearance: carried("appearance"),
    attacking: carried("attacking"),
    cleanSheet: carried("cleanSheet"),
    bonus: carried("bonus"),
    saves: carried("saves"),
    conceding: carried("conceding"),
    yellowCards: carried("yellowCards"),
    redCards: carried("redCards"),
    ownGoals: carried("ownGoals"),
    penaltiesMissed: carried("penaltiesMissed"),
    defensiveContribution: carried("defensiveContribution"),
  };
}

export function startRateAtEvent(
  player: SolverPlayer,
  eventIndex: number,
): number {
  const carry = MARKET_CARRY.players[String(player.id)];
  if (!carry) return player.startRate;
  const [anchorIndex, baselineStartRate] = carry;
  return marketValueAtEvent(
    player.startRate,
    baselineStartRate,
    eventIndex,
    anchorIndex,
    MARKET_CARRY.halfLifeGameweeks,
  );
}

/** A fixture BPS ranking replaces the historical bonus rate where available. */
export function bonusPointsAtEvent(
  historicalPerFixture: number,
  fixtures: number,
  override: number | undefined,
): number {
  return override ?? historicalPerFixture * fixtures;
}

/** Pressure moves the odds of clearing the DefCon bar, never the two-point cap. */
export function defconPointsAtEvent(
  historicalPerFixture: number,
  pressureTotal: number,
  fixtures: number,
): number {
  if (fixtures <= 0) return 0;
  const probability = Math.min(1, Math.max(0, historicalPerFixture / 2));
  if (probability === 0 || probability === 1) {
    return probability * 2 * fixtures;
  }
  const pressure = pressureTotal / fixtures;
  const adjusted =
    (probability * pressure) / (1 - probability + probability * pressure);
  return adjusted * 2 * fixtures;
}

/**
 * Each route bent by what this fixture does to it.
 *
 * One multiplier for the whole projection was wrong in both directions: a
 * defender's assists were priced by his side's defensive difficulty, and a
 * keeper's saves scaled as if they were clean sheets. Appearance points, bonus
 * and discipline do not move with the opponent at all.
 *
 * A blank gameweek is a zero rung, so every route collapses to nothing except
 * the ones that do not depend on a fixture -- and those are multiplied by the
 * fixture count, which is also zero.
 */
function splitAt(player: SolverPlayer, eventIndex: number): EventRoutes {
  const ladder = LADDER[player.club];
  const attacking = ladder?.attacking[eventIndex];
  const cleanSheet = ladder?.defensive[eventIndex];
  const saves = ladder?.saves[eventIndex];
  const conceding = ladder?.conceding[eventIndex];
  const defensiveContribution = ladder?.defensiveContribution[eventIndex];
  if (
    attacking === undefined ||
    cleanSheet === undefined ||
    saves === undefined ||
    conceding === undefined ||
    defensiveContribution === undefined
  ) {
    return NO_ROUTES;
  }
  // A rung is the sum over this gameweek's fixtures, so it doubles for a
  // double and is zero for a blank. The routes a fixture cannot bend have to
  // follow the same count, or a blank gameweek would still pay appearance.
  const fixtures = OPPONENTS[player.club]?.[eventIndex]?.length ?? 0;
  const event = EVENTS[eventIndex];
  const bonusOverride =
    event === undefined
      ? undefined
      : BONUS_OVERRIDES[String(event)]?.[String(player.id)];
  const routes = routesAtEvent(player, eventIndex);
  return {
    appearance: (routes.appearance ?? 0) * fixtures,
    bonus: bonusPointsAtEvent(routes.bonus ?? 0, fixtures, bonusOverride),
    yellowCards: (routes.yellowCards ?? 0) * fixtures,
    redCards: (routes.redCards ?? 0) * fixtures,
    ownGoals: (routes.ownGoals ?? 0) * fixtures,
    penaltiesMissed: (routes.penaltiesMissed ?? 0) * fixtures,
    attacking: (routes.attacking ?? 0) * attacking,
    cleanSheet: (routes.cleanSheet ?? 0) * cleanSheet,
    saves: (routes.saves ?? 0) * saves,
    // Conceding points are negative, so a leakier fixture makes them worse.
    conceding: (routes.conceding ?? 0) * conceding,
    defensiveContribution: defconPointsAtEvent(
      routes.defensiveContribution ?? 0,
      defensiveContribution,
      fixtures,
    ),
  };
}

function pointsAt(player: SolverPlayer, eventIndex: number): number {
  const split = splitAt(player, eventIndex);
  return (
    split.appearance +
    split.bonus +
    split.yellowCards +
    split.redCards +
    split.ownGoals +
    split.penaltiesMissed +
    split.attacking +
    split.cleanSheet +
    split.saves +
    split.conceding +
    split.defensiveContribution
  );
}

/**
 * What a player is worth from here, over the run the solver can see.
 *
 * `rebuildIndex` is a gameweek the squad is thrown away in, because the reader
 * has committed to a wildcard there. Nothing he holds before it is still his
 * afterwards, so the sum stops at it. Without this the solver happily pays a
 * hit in gameweek 1 for a player whose fixtures turn in gameweek 6, having
 * been told the squad is being rebuilt in gameweek 3.
 */
function lookaheadPoints(
  player: SolverPlayer,
  eventIndex: number,
  rebuildIndex = Number.POSITIVE_INFINITY,
): number {
  let total = 0;
  for (let ahead = 0; ahead < LOOKAHEAD; ahead += 1) {
    const index = eventIndex + ahead;
    if (index >= EVENTS.length) break;
    // Only binds before the rebuild. From the rebuild onwards the squad is new
    // and the full run ahead is its own again.
    if (eventIndex < rebuildIndex && index >= rebuildIndex) break;
    total += pointsAt(player, index) * LOOKAHEAD_DECAY ** ahead;
  }
  return total;
}

/**
 * Something the public source cannot say, which this solve assumed anyway.
 *
 * FPL publishes a manager's picks and his bank; it does not publish how many
 * free transfers he is holding, nor what he paid for anyone. Both are private
 * to the logged-in manager. Refusing to plan without them would make the page
 * useless for everyone who has not filled the corrections form, so the
 * assumption is made and named rather than made and hidden.
 */
export type SolveAssumption = "bank" | "free_transfers" | "selling_prices";

export interface SolveStart {
  /** Element ids currently held, and what they would sell for. */
  squad: { elementId: number; sellingPriceTenths: number }[];
  bankTenths: number;
  availableFreeTransfers: number;
  /** First gameweek to plan. Everything from here to 38 is solved. */
  fromEvent: number;
  /** Set when the reader has rejected the free pre-deadline changes. */
  lockOpening?: boolean;
  /**
   * A gameweek the reader has committed to wildcarding in.
   *
   * A wildcard resets the long-term view: a five-gameweek horizon is the right
   * yardstick for a squad you keep, and the wrong one for a squad you have
   * already decided to throw away. Only a wildcard does this. A Free Hit hands
   * the squad straight back, so it changes one week and nothing either side.
   */
  rebuildAtEvent?: number;
  /** A one-week temporary squad that is restored after this event. */
  freeHitAtEvent?: number;
  assumed: readonly SolveAssumption[];
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
  chip?: "Free Hit";
  revertsAfter?: boolean;
  revertsTo?: SolverPlayer[];
}

const BY_ID = new Map(PLAYERS.map((player) => [player.id, player]));

function look(elementId: number): SolverPlayer {
  const found = BY_ID.get(elementId);
  if (!found) throw new Error(`solver returned unknown element ${elementId}`);
  return found;
}

const SHEET_ORDER = ["GKP", "DEF", "MID", "FWD"];

/** Position ids come from the rules artifact; the codes are this app's. */
const POSITION_BY_ID: Record<number, string> = {
  1: "GKP",
  2: "DEF",
  3: "MID",
  4: "FWD",
};

export const EVENT_INDEX = new Map(
  EVENTS.map((event, index) => [event, index]),
);

export const SQUAD_SHAPE_BY_CODE: Record<string, number> = Object.fromEntries(
  SQUAD_SHAPE.map((slot) => [
    POSITION_BY_ID[slot.positionId] ?? String(slot.positionId),
    slot.squadCount,
  ]),
);

export const LINEUP_SHAPE: Record<string, { min: number; max: number }> =
  Object.fromEntries(
    SQUAD_SHAPE.map((slot) => [
      POSITION_BY_ID[slot.positionId] ?? String(slot.positionId),
      { min: slot.lineupMinimum, max: slot.lineupMaximum },
    ]),
  );

export const LINEUP_SIZE = RULES.lineupSize;
export { PLAYABLE_START_RATE };

/** One player's expected points for a single gameweek, fixture included. */
export function pointsAtEvent(
  player: SolverPlayer,
  eventIndex: number,
): number {
  return pointsAt(player, eventIndex);
}

/** One gameweek, told the way a reader asking "why that number" wants it. */
export interface EventFixture {
  event: number;
  /** As published: "COV (H)". Two entries in a double, none in a blank. */
  opponents: readonly string[];
  difficulty: number | null;
  points: number;
  routes: EventRoutes;
}

/** The same gameweek, split back into the routes that paid for it. */
export function fixtureAtEvent(
  player: SolverPlayer,
  eventIndex: number,
): EventFixture | null {
  const event = EVENTS[eventIndex];
  if (event === undefined) return null;
  const routes = splitAt(player, eventIndex);
  return {
    event,
    opponents: OPPONENTS[player.club]?.[eventIndex] ?? [],
    difficulty: DIFFICULTY[player.club]?.[eventIndex] ?? null,
    points: pointsAt(player, eventIndex),
    routes,
  };
}

/** The same, discounted over the next few gameweeks. */
export function lookaheadPointsFor(
  player: SolverPlayer,
  eventIndex: number,
  rebuildIndex?: number,
): number {
  return lookaheadPoints(player, eventIndex, rebuildIndex);
}

/**
 * The best legal eleven this fifteen can field, captain doubled.
 *
 * Both sides of a chip comparison are scored through here, so the captain
 * multiplier cancels out of the difference and cannot flatter either.
 */
export function bestElevenPoints(
  squad: readonly SolverPlayer[],
  eventIndex: number,
): number {
  const scored = squad
    .map((player) => ({ player, points: pointsAt(player, eventIndex) }))
    .sort((left, right) => right.points - left.points);

  const picked: typeof scored = [];
  const perPosition = new Map<string, number>();

  // Minimums first, or a keeper-less eleven scores better than a legal one.
  for (const [code, shape] of Object.entries(LINEUP_SHAPE)) {
    for (const entry of scored) {
      if ((perPosition.get(code) ?? 0) >= shape.min) break;
      if (entry.player.position !== code) continue;
      if (picked.includes(entry)) continue;
      picked.push(entry);
      perPosition.set(code, (perPosition.get(code) ?? 0) + 1);
    }
  }

  for (const entry of scored) {
    if (picked.length >= LINEUP_SIZE) break;
    if (picked.includes(entry)) continue;
    const code = entry.player.position;
    const shape = LINEUP_SHAPE[code];
    if (shape && (perPosition.get(code) ?? 0) >= shape.max) continue;
    picked.push(entry);
    perPosition.set(code, (perPosition.get(code) ?? 0) + 1);
  }

  const total = picked.reduce((sum, entry) => sum + entry.points, 0);
  const captain = picked.reduce(
    (best, entry) => Math.max(best, entry.points),
    0,
  );
  return total + captain;
}

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

/**
 * Below this the solver will not buy him.
 *
 * The same floor `planning/opening.py` applies, published beside the players
 * rather than retyped here: a man who does not start does not score, however
 * good his rate looks over the handful of appearances he made.
 */
const PLAYABLE_START_RATE = RULES.playableStartRate;

/**
 * What a transfer must clear before it is worth making. Same number and same
 * reason as `TransferPlanSettings.margin` on the Python side: a per-deadline
 * solver sees no value in an unused free transfer, so without this it spends
 * one on any gain at all and can never bank one for a two-move week.
 */
const TRANSFER_MARGIN_POINTS = RULES.transferMarginPoints;

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
  const rebuildIndex =
    start.rebuildAtEvent === undefined
      ? Number.POSITIVE_INFINITY
      : (() => {
          const at = EVENTS.indexOf(start.rebuildAtEvent);
          return at < 0 ? Number.POSITIVE_INFINITY : at;
        })();
  // Nothing is charged before the first deadline: a squad is still being
  // picked, not transferred. Starting at zero made the solver price a change
  // it should have taken for nothing, and the plan opened by advising a hit.
  let free =
    start.fromEvent === SEASON_OPENER
      ? MAX_FREE_TRANSFERS
      : start.availableFreeTransfers;
  const freeHitIndex =
    start.freeHitAtEvent === undefined
      ? -1
      : EVENTS.indexOf(start.freeHitAtEvent);

  for (let index = firstIndex; index < EVENTS.length; index += 1) {
    const event = EVENTS[index];
    const deadline = DEADLINES[index];
    if (event === undefined || deadline === undefined) break;

    const players = PLAYERS.filter(
      // Same floor the Python planner applies. Without it a fringe player with
      // a high per-appearance rate and almost no starts could win a transfer,
      // and the browser kept exactly the candidates Python drops.
      (player) =>
        startRateAtEvent(player, index) >= PLAYABLE_START_RATE ||
        squad.some((held) => held.elementId === player.id),
    ).map((player) => ({
      elementId: player.id,
      teamId: player.teamId,
      positionId: player.positionId,
      buyPriceTenths: player.priceTenths,
      planningPoints: lookaheadPoints(player, index, rebuildIndex),
      eventPoints: pointsAt(player, index),
      evidenceLevel: "inferred" as const,
      dataAvailableAt: deadline,
      sourceHashes: [HASH],
    }));

    const isFreeHit = index === freeHitIndex;
    const preChipSquad = squad.map((held) => ({ ...held }));
    const preChipBank = bank;
    const preChipFree = free;
    const input: QuickSolverInput = {
      season: "2026-27",
      event,
      objective: "expected_value",
      priceScenario: "current_prices",
      chipScenario: isFreeHit ? "free_hit" : "none",
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
        squadSize: RULES.squadSize,
        lineupSize: RULES.lineupSize,
        clubLimit: RULES.clubLimit,
        transferCap: RULES.transferCap,
        weeklyFreeTransfers: RULES.weeklyFreeTransfers,
        maximumFreeTransfers: RULES.maximumFreeTransfers,
        transferCostPoints: RULES.transferCostPoints,
        transferRulesSourceReference: RULES.sourceReference,
        positions: SQUAD_SHAPE,
        dataAvailableAt: RULES.dataAvailableAt,
        publishedRulesHash: HASH,
        transferRulesHash: HASH,
      },
    };

    let solved = solveQuickPlan(input, {
      beamWidth: 12,
      candidateLimitPerPosition: 8,
      // Squad selection, not a transfer window: the opening week gets the
      // solver's full move budget because none of those moves costs anything.
      maxTransfers: isFreeHit
        ? 15
        : event === SEASON_OPENER
          ? start.lockOpening
            ? 0
            : MAX_FREE_TRANSFERS
          : 2,
      transferMarginPoints: TRANSFER_MARGIN_POINTS,
    });

    // A Free Hit is only a chip when it materially rebuilds the fifteen. If
    // the best temporary squad moves fewer than five players, keep the normal
    // transfer solve and leave the chip available.
    if (isFreeHit && solved.transfersIn.length < 5) {
      solved = solveQuickPlan(
        { ...input, chipScenario: "none" },
        {
          beamWidth: 12,
          candidateLimitPerPosition: 8,
          maxTransfers:
            event === SEASON_OPENER
              ? start.lockOpening
                ? 0
                : MAX_FREE_TRANSFERS
              : 2,
          transferMarginPoints: TRANSFER_MARGIN_POINTS,
        },
      );
    }

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
      ...(isFreeHit && solved.transfersIn.length >= 5
        ? {
            chip: "Free Hit" as const,
            revertsAfter: true,
            revertsTo: preChipSquad.map((held) => look(held.elementId)),
          }
        : {}),
    };

    if (isFreeHit && solved.transfersIn.length >= 5) {
      squad = preChipSquad;
      bank = preChipBank;
      free = Math.min(MAX_FREE_TRANSFERS, preChipFree + WEEKLY_FREE_TRANSFERS);
      continue;
    }

    // A player already held keeps the selling price he came in with; one just
    // bought sells for what was paid for him this minute. Rebuilding every
    // price from the list threw away the manager's real purchase prices one
    // gameweek after they were read.
    const heldPrice = new Map(
      squad.map((held) => [held.elementId, held.sellingPriceTenths]),
    );
    const listPrice = new Map(
      PLAYERS.map((player) => [player.id, player.priceTenths]),
    );
    squad = solved.squadElementIds.map((elementId) => ({
      elementId,
      sellingPriceTenths:
        heldPrice.get(elementId) ?? listPrice.get(elementId) ?? 0,
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
export const SEASON_DEADLINES = DEADLINES;

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

  // Nobody owns this squad, so nothing was assumed about an owner.
  return squad.length === codes.length
    ? { ...options, squad, assumed: [] }
    : null;
}

/** Element id to player, for anything that has to name a squad FPL published. */
export const PLAYERS_BY_ELEMENT_ID = new Map(
  PLAYERS.map((player) => [player.id, player]),
);
const BY_ELEMENT_ID = PLAYERS_BY_ELEMENT_ID;

/**
 * The same, from a manager's own squad.
 *
 * FPL's team endpoint returns element ids, not codes, so this is the door a
 * real manager comes through. A squad the solver does not recognise in full
 * yields null rather than a solve for fourteen players.
 *
 * `sellingPrices` is what he actually paid, plus half of any rise, which is
 * the only number he can really transfer against. Without it the list price is
 * used and `selling_prices` is named in `assumed`: an appreciated player is
 * then worth more on paper than he is in the bank, and a plan built on that
 * can propose a transfer the manager cannot fund.
 */
export function startFromElementIds(
  elementIds: readonly number[],
  options: {
    bankTenths: number;
    availableFreeTransfers: number;
    fromEvent: number;
    sellingPrices?: ReadonlyMap<number, number>;
    assumed?: readonly SolveAssumption[];
  },
): SolveStart | null {
  const { sellingPrices, assumed = [], ...rest } = options;
  const squad = elementIds
    .map((elementId) => BY_ELEMENT_ID.get(elementId))
    .filter((player): player is SolverPlayer => player !== undefined)
    .map((player) => ({
      elementId: player.id,
      sellingPriceTenths: sellingPrices?.get(player.id) ?? player.priceTenths,
    }));

  const missing = elementIds.some(
    (elementId) => sellingPrices?.get(elementId) === undefined,
  );

  return squad.length === elementIds.length
    ? {
        ...rest,
        squad,
        assumed: missing ? [...assumed, "selling_prices"] : assumed,
      }
    : null;
}
