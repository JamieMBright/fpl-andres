import { z } from "zod";

const sourceHashSchema = z.string().regex(/^sha256:[a-f0-9]{64}$/);
const sourceHashesSchema = z
  .array(sourceHashSchema)
  .min(1)
  .refine(
    (hashes) =>
      hashes.length === new Set(hashes).size &&
      hashes.every((hash, index) => hash === [...hashes].sort()[index]),
    "source hashes must be sorted and unique",
  );

const quickPlayerSchema = z
  .object({
    elementId: z.int().positive(),
    teamId: z.int().positive(),
    positionId: z.int().positive(),
    buyPriceTenths: z.int().nonnegative(),
    planningPoints: z.number().finite(),
    eventPoints: z.number().finite(),
    evidenceLevel: z.enum(["inferred", "experimental"]),
    dataAvailableAt: z.iso.datetime(),
    sourceHashes: sourceHashesSchema,
  })
  .strict();

const currentPlayerSchema = z
  .object({
    elementId: z.int().positive(),
    sellingPriceTenths: z.int().nonnegative(),
  })
  .strict();

const stateEvidenceSchema = z
  .object({
    publicStateAsOf: z.iso.datetime(),
    publicDataAvailableAt: z.iso.datetime(),
    overridesUpdatedAt: z.iso.datetime(),
    publicSourceHashes: sourceHashesSchema,
    managerOverridesHash: sourceHashSchema,
  })
  .strict()
  .superRefine((evidence, context) => {
    if (
      Date.parse(evidence.publicDataAvailableAt) <
      Date.parse(evidence.publicStateAsOf)
    ) {
      context.addIssue({
        code: "custom",
        message: "public data cannot predate public state",
      });
    }
    if (
      Date.parse(evidence.overridesUpdatedAt) <
      Date.parse(evidence.publicStateAsOf)
    ) {
      context.addIssue({
        code: "custom",
        message: "manager overrides cannot predate public state",
      });
    }
  });

const positionRuleSchema = z
  .object({
    positionId: z.int().positive(),
    squadCount: z.int().positive(),
    lineupMinimum: z.int().nonnegative(),
    lineupMaximum: z.int().nonnegative(),
  })
  .strict()
  .refine(
    ({ lineupMaximum, lineupMinimum, squadCount }) =>
      lineupMinimum <= lineupMaximum && lineupMaximum <= squadCount,
    "invalid position lineup bounds",
  );

const quickRulesSchema = z
  .object({
    squadSize: z.int().positive(),
    lineupSize: z.int().min(2),
    clubLimit: z.int().positive(),
    transferCap: z.int().positive(),
    transferCostPoints: z.int().positive(),
    weeklyFreeTransfers: z.int().positive(),
    maximumFreeTransfers: z.int().positive(),
    transferRulesSourceReference: z.string().trim().min(1),
    positions: z.array(positionRuleSchema).min(1),
    publishedRulesHash: sourceHashSchema,
    transferRulesHash: sourceHashSchema,
    dataAvailableAt: z.iso.datetime(),
  })
  .strict()
  .superRefine((rules, context) => {
    if (rules.maximumFreeTransfers < rules.weeklyFreeTransfers) {
      context.addIssue({
        code: "custom",
        message: "maximum free transfers cannot be below the weekly award",
      });
    }
    if (
      new Set(rules.positions.map(({ positionId }) => positionId)).size !==
      rules.positions.length
    ) {
      context.addIssue({
        code: "custom",
        message: "position IDs must be unique",
      });
    }
    if (
      rules.positions.reduce(
        (total, position) => total + position.squadCount,
        0,
      ) !== rules.squadSize
    ) {
      context.addIssue({
        code: "custom",
        message: "position counts must equal squad size",
      });
    }
    if (
      rules.positions.reduce(
        (total, position) => total + position.lineupMinimum,
        0,
      ) > rules.lineupSize ||
      rules.positions.reduce(
        (total, position) => total + position.lineupMaximum,
        0,
      ) < rules.lineupSize
    ) {
      context.addIssue({
        code: "custom",
        message: "position bounds cannot form a lineup",
      });
    }
  });

export const quickSolverInputSchema = z
  .object({
    season: z.string().regex(/^20[0-9]{2}-[0-9]{2}$/),
    event: z.int().min(1).max(38),
    objective: z.literal("expected_value"),
    priceScenario: z.literal("current_prices"),
    chipScenario: z.enum(["none", "free_hit"]),
    predictionCutoff: z.iso.datetime(),
    players: z.array(quickPlayerSchema).min(1),
    currentSquad: z.array(currentPlayerSchema).min(1),
    priorityTransferOutElementIds: z.array(z.int().positive()).default([]),
    targetSquadElementIds: z.array(z.int().positive()).optional(),
    bankTenths: z.int().nonnegative(),
    availableFreeTransfers: z.int().nonnegative(),
    stateEvidence: stateEvidenceSchema,
    rules: quickRulesSchema,
  })
  .strict()
  .superRefine((input, context) => {
    if (
      Date.parse(input.rules.dataAvailableAt) >
      Date.parse(input.predictionCutoff)
    ) {
      context.addIssue({
        code: "custom",
        message: "rules became available after the prediction cutoff",
        path: ["rules", "dataAvailableAt"],
      });
    }
    if (
      Date.parse(input.stateEvidence.publicDataAvailableAt) >
      Date.parse(input.predictionCutoff)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "public team state became available after the prediction cutoff",
        path: ["stateEvidence", "publicDataAvailableAt"],
      });
    }
    if (
      Date.parse(input.stateEvidence.overridesUpdatedAt) >
      Date.parse(input.predictionCutoff)
    ) {
      context.addIssue({
        code: "custom",
        message: "manager state became available after the prediction cutoff",
        path: ["stateEvidence", "overridesUpdatedAt"],
      });
    }
    if (
      input.players.some(
        ({ dataAvailableAt }) =>
          Date.parse(dataAvailableAt) > Date.parse(input.predictionCutoff),
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "player evidence became available after the prediction cutoff",
        path: ["players"],
      });
    }
    if (input.players.length < input.rules.squadSize) {
      context.addIssue({
        code: "custom",
        message: "candidate pool is smaller than the squad",
      });
    }
    const playerIds = input.players.map(({ elementId }) => elementId);
    if (new Set(playerIds).size !== playerIds.length) {
      context.addIssue({
        code: "custom",
        message: "candidate element IDs must be unique",
      });
    }
    const currentIds = input.currentSquad.map(({ elementId }) => elementId);
    if (
      currentIds.length !== input.rules.squadSize ||
      new Set(currentIds).size !== currentIds.length
    ) {
      context.addIssue({
        code: "custom",
        message: "current squad must contain unique elements",
      });
    }
    if (input.targetSquadElementIds !== undefined) {
      if (input.chipScenario !== "free_hit") {
        context.addIssue({
          code: "custom",
          message:
            "a target squad is only valid for an unlimited-transfer chip",
          path: ["targetSquadElementIds"],
        });
      }
      if (
        input.targetSquadElementIds.length !== input.rules.squadSize ||
        new Set(input.targetSquadElementIds).size !==
          input.targetSquadElementIds.length ||
        input.targetSquadElementIds.some(
          (elementId) => !playerIds.includes(elementId),
        )
      ) {
        context.addIssue({
          code: "custom",
          message: "target squad must contain unique candidate elements",
          path: ["targetSquadElementIds"],
        });
      }
    }
    if (
      new Set(input.priorityTransferOutElementIds).size !==
        input.priorityTransferOutElementIds.length ||
      input.priorityTransferOutElementIds.some(
        (elementId) => !currentIds.includes(elementId),
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "priority transfer-outs must be unique current-squad elements",
        path: ["priorityTransferOutElementIds"],
      });
    }
    if (currentIds.some((elementId) => !playerIds.includes(elementId))) {
      context.addIssue({
        code: "custom",
        message: "current squad requires candidate forecasts",
      });
    }
    if (input.availableFreeTransfers > input.rules.maximumFreeTransfers) {
      context.addIssue({
        code: "custom",
        message: "free transfers exceed the sourced maximum",
      });
    }
    const positions = new Set(
      input.rules.positions.map(({ positionId }) => positionId),
    );
    if (input.players.some(({ positionId }) => !positions.has(positionId))) {
      context.addIssue({
        code: "custom",
        message: "candidate position is absent from rules",
      });
    }
    const players = new Map(
      input.players.map((player) => [player.elementId, player]),
    );
    if (
      currentIds.every((elementId) => players.has(elementId)) &&
      !isStructurallyValid(new Set(currentIds), players, input.rules)
    ) {
      context.addIssue({
        code: "custom",
        message: "current squad violates optimizer rules",
      });
    }
  });

const quickSolverLimitsSchema = z
  .object({
    beamWidth: z.int().min(1).max(500),
    candidateLimitPerPosition: z.int().min(1).max(50),
    maxTransfers: z.int().min(0).max(15),
    /**
     * What a transfer must clear, per transfer, on top of its cost.
     *
     * Without it a free transfer is spent on any gain at all, however small,
     * because a per-deadline solver sees no value in an unused one. Holding it
     * is worth something the objective cannot express: next week it can be a
     * second move, and churn has costs the model cannot see -- price changes,
     * and being wrong. Same number and same reason as the Python planner's
     * `TransferPlanSettings.margin`.
     */
    transferMarginPoints: z.number().nonnegative().default(0),
  })
  .strict();

export type QuickSolverInput = z.infer<typeof quickSolverInputSchema>;
export type QuickSolverLimits = z.infer<typeof quickSolverLimitsSchema>;
type QuickPlayer = QuickSolverInput["players"][number];
type QuickRules = QuickSolverInput["rules"];
const FREE_HIT_ENABLERS_PER_POSITION = 4;

export function isCaptainEligiblePositionId(positionId: number): boolean {
  if (positionId === 1 || positionId === 2) return false;
  if (positionId === 3 || positionId === 4) return true;
  throw new Error(
    `position ID ${String(positionId)} is not an FPL player position`,
  );
}

export interface QuickSolverResult {
  solver: "quick-beam";
  solverStatus: "bounded";
  objective: "expected_value";
  priceScenario: "current_prices";
  chipScenario: "none" | "free_hit";
  squadElementIds: number[];
  starterElementIds: number[];
  benchElementIds: number[];
  captainElementId: number;
  viceCaptainElementId: number;
  transfersIn: number[];
  transfersOut: number[];
  paidTransfers: number;
  transferCostPoints: number;
  projectedPointsBeforeCost: number;
  netExpectedPoints: number;
  planningPointsBeforeCost: number;
  netPlanningPoints: number;
  bankAfterTenths: number;
  evidenceLevel: "inferred" | "experimental";
  dataAvailableAt: string;
  sourceHashes: string[];
  reasonCodes: string[];
  diagnostics: {
    beamWidth: number;
    candidateLimitPerPosition: number;
    maxTransfers: number;
    candidatePoolSize: number;
    statesEvaluated: number;
    maximumFrontierSize: number;
    deepestTransferCount: number;
    truncated: boolean;
  };
}

interface EvaluatedState {
  squadElementIds: number[];
  starterElementIds: number[];
  benchElementIds: number[];
  captainElementId: number;
  viceCaptainElementId: number;
  transfersIn: number[];
  transfersOut: number[];
  paidTransfers: number;
  transferCostPoints: number;
  projectedPointsBeforeCost: number;
  netExpectedPoints: number;
  planningPointsBeforeCost: number;
  netPlanningPoints: number;
  bankAfterTenths: number;
  squadQuality: number;
  chipScenario: "none" | "free_hit";
}

interface LineupEvaluation {
  elementIds: number[];
  captainElementId: number;
  viceCaptainElementId: number;
  projectedPoints: number;
}

export function solveQuickPlan(
  inputValue: unknown,
  limitsValue: unknown,
): QuickSolverResult {
  const input = quickSolverInputSchema.parse(inputValue);
  const limits = quickSolverLimitsSchema.parse(limitsValue);
  const players = new Map(
    [...input.players]
      .sort((left, right) => left.elementId - right.elementId)
      .map((player) => [player.elementId, player]),
  );
  const current = new Map(
    input.currentSquad.map((player) => [player.elementId, player]),
  );
  const currentIds = new Set(current.keys());
  const { candidateIds, omittedCandidates } = boundedCandidates(
    input,
    currentIds,
    players,
    limits,
  );
  const maximumTransfers = Math.min(
    limits.maxTransfers,
    input.rules.transferCap,
  );
  const priorityIds = new Set(input.priorityTransferOutElementIds);
  const requiredPriorityTransfers = Math.min(
    priorityIds.size,
    input.availableFreeTransfers,
    maximumTransfers,
  );
  let truncated =
    omittedCandidates || maximumTransfers < input.rules.transferCap;
  let statesEvaluated = 0;
  let maximumFrontierSize = 1;
  let deepestTransferCount = 0;

  const initial = evaluateSquad(new Set(currentIds), input, players, current);
  if (initial === null) {
    throw new Error("current squad cannot produce a valid lineup");
  }
  statesEvaluated += 1;
  const planned = input.targetSquadElementIds
    ? evaluateSquad(
        new Set(input.targetSquadElementIds),
        input,
        players,
        current,
      )
    : null;
  if (
    input.targetSquadElementIds &&
    (planned === null || planned.transfersIn.length > maximumTransfers)
  ) {
    throw new Error("planned chip squad violates optimizer rules or budget");
  }
  if (planned) statesEvaluated += 1;
  let best = planned ?? initial;
  let priorityBest: EvaluatedState | null = null;
  let frontier = planned ? [] : [initial];
  if (planned) deepestTransferCount = planned.transfersIn.length;

  for (let depth = 1; depth <= maximumTransfers; depth += 1) {
    const expanded = new Map<string, EvaluatedState>();
    for (const state of frontier) {
      const selected = new Set(state.squadElementIds);
      for (const outgoing of state.squadElementIds.filter((elementId) =>
        currentIds.has(elementId),
      )) {
        const outgoingPlayer = requiredPlayer(players, outgoing);
        for (const incoming of candidateIds) {
          if (selected.has(incoming) || currentIds.has(incoming)) continue;
          const incomingPlayer = requiredPlayer(players, incoming);
          if (incomingPlayer.positionId !== outgoingPlayer.positionId) continue;
          const next = new Set(selected);
          next.delete(outgoing);
          next.add(incoming);
          const key = [...next].sort((left, right) => left - right).join(",");
          if (expanded.has(key)) continue;
          const evaluated = evaluateSquad(next, input, players, current);
          statesEvaluated += 1;
          if (evaluated !== null && evaluated.transfersIn.length === depth) {
            expanded.set(key, evaluated);
            const priorityTransfers = evaluated.transfersOut.filter(
              (elementId) => priorityIds.has(elementId),
            ).length;
            if (
              evaluated.paidTransfers === 0 &&
              priorityTransfers >= requiredPriorityTransfers &&
              requiredPriorityTransfers > 0 &&
              (priorityBest === null ||
                compareStates(evaluated, priorityBest) < 0)
            ) {
              priorityBest = evaluated;
            }
          }
        }
      }
    }
    const ordered = [...expanded.values()].sort(compareStates);
    if (ordered.length > limits.beamWidth) truncated = true;
    frontier = ordered.slice(0, limits.beamWidth);
    maximumFrontierSize = Math.max(maximumFrontierSize, frontier.length);
    if (frontier.length === 0) break;
    deepestTransferCount = depth;
    if (compareStates(frontier[0]!, best) < 0) best = frontier[0]!;
  }

  // A move has to be worth making, not merely positive. Applied after the
  // search rather than inside it so the frontier still explores moves that
  // only pay off two transfers deep.
  const usedPriority = priorityBest !== null;
  if (priorityBest !== null) {
    best = priorityBest;
  } else if (
    input.chipScenario !== "free_hit" &&
    best !== initial &&
    best.netPlanningPoints - initial.netPlanningPoints <=
      limits.transferMarginPoints * best.transfersIn.length
  ) {
    best = initial;
  }

  const sourceHashes = [
    input.rules.publishedRulesHash,
    input.rules.transferRulesHash,
    input.stateEvidence.managerOverridesHash,
    ...input.stateEvidence.publicSourceHashes,
    ...input.players.flatMap(({ sourceHashes }) => sourceHashes),
  ];
  const dataAvailableAt = [
    input.rules.dataAvailableAt,
    input.stateEvidence.publicDataAvailableAt,
    input.stateEvidence.overridesUpdatedAt,
    ...input.players.map(({ dataAvailableAt }) => dataAvailableAt),
  ]
    .sort((left, right) => Date.parse(left) - Date.parse(right))
    .at(-1)!;
  const reasonCodes = ["quick_beam_plan"];
  if (planned) reasonCodes.push("planned_chip_squad");
  if (truncated) reasonCodes.push("bounded_search_truncated");
  if (usedPriority) reasonCodes.push("ruled_out_replacement");

  return {
    solver: "quick-beam",
    solverStatus: "bounded",
    objective: input.objective,
    priceScenario: input.priceScenario,
    chipScenario: input.chipScenario,
    squadElementIds: best.squadElementIds,
    starterElementIds: best.starterElementIds,
    benchElementIds: best.benchElementIds,
    captainElementId: best.captainElementId,
    viceCaptainElementId: best.viceCaptainElementId,
    transfersIn: best.transfersIn,
    transfersOut: best.transfersOut,
    paidTransfers: best.paidTransfers,
    transferCostPoints: best.transferCostPoints,
    projectedPointsBeforeCost: best.projectedPointsBeforeCost,
    netExpectedPoints: best.netExpectedPoints,
    planningPointsBeforeCost: best.planningPointsBeforeCost,
    netPlanningPoints: best.netPlanningPoints,
    bankAfterTenths: best.bankAfterTenths,
    evidenceLevel: input.players.some(
      ({ evidenceLevel }) => evidenceLevel === "experimental",
    )
      ? "experimental"
      : "inferred",
    dataAvailableAt,
    sourceHashes: [...new Set(sourceHashes)].sort(),
    reasonCodes,
    diagnostics: {
      beamWidth: limits.beamWidth,
      candidateLimitPerPosition: limits.candidateLimitPerPosition,
      maxTransfers: maximumTransfers,
      candidatePoolSize: candidateIds.length,
      statesEvaluated,
      maximumFrontierSize,
      deepestTransferCount,
      truncated,
    },
  };
}

function boundedCandidates(
  input: QuickSolverInput,
  currentIds: Set<number>,
  players: Map<number, QuickPlayer>,
  limits: QuickSolverLimits,
): { candidateIds: number[]; omittedCandidates: boolean } {
  const selected = new Set(currentIds);
  const current = new Map(
    input.currentSquad.map((player) => [player.elementId, player]),
  );
  let omittedCandidates = false;
  for (const position of input.rules.positions) {
    const candidates = [...players.values()]
      .filter(
        ({ elementId, positionId }) =>
          positionId === position.positionId && !currentIds.has(elementId),
      )
      .sort(
        (left, right) =>
          bestOneTransferValue(right, currentIds, input, players, current) -
            bestOneTransferValue(left, currentIds, input, players, current) ||
          right.planningPoints - left.planningPoints ||
          left.buyPriceTenths - right.buyPriceTenths ||
          left.elementId - right.elementId,
      );
    if (candidates.length > limits.candidateLimitPerPosition)
      omittedCandidates = true;
    const shortlisted = candidates.slice(0, limits.candidateLimitPerPosition);
    if (input.chipScenario === "free_hit") {
      shortlisted.push(
        ...[...candidates]
          .sort(
            (left, right) =>
              left.buyPriceTenths - right.buyPriceTenths ||
              right.planningPoints - left.planningPoints ||
              left.elementId - right.elementId,
          )
          .slice(0, FREE_HIT_ENABLERS_PER_POSITION),
      );
    }
    for (const player of shortlisted) {
      selected.add(player.elementId);
    }
  }
  return {
    candidateIds: [...selected].sort((left, right) => left - right),
    omittedCandidates,
  };
}

function bestOneTransferValue(
  incoming: QuickPlayer,
  currentIds: Set<number>,
  input: QuickSolverInput,
  players: Map<number, QuickPlayer>,
  current: Map<number, QuickSolverInput["currentSquad"][number]>,
): number {
  let best = Number.NEGATIVE_INFINITY;
  for (const outgoing of currentIds) {
    if (requiredPlayer(players, outgoing).positionId !== incoming.positionId)
      continue;
    const squad = new Set(currentIds);
    squad.delete(outgoing);
    squad.add(incoming.elementId);
    const evaluated = evaluateSquad(squad, input, players, current);
    if (evaluated !== null) best = Math.max(best, evaluated.netPlanningPoints);
  }
  return best;
}

function evaluateSquad(
  squad: Set<number>,
  input: QuickSolverInput,
  players: Map<number, QuickPlayer>,
  current: Map<number, QuickSolverInput["currentSquad"][number]>,
): EvaluatedState | null {
  if (!isStructurallyValid(squad, players, input.rules)) return null;
  const currentIds = new Set(current.keys());
  const transfersIn = [...squad]
    .filter((elementId) => !currentIds.has(elementId))
    .sort((left, right) => left - right);
  const transfersOut = [...currentIds]
    .filter((elementId) => !squad.has(elementId))
    .sort((left, right) => left - right);
  if (transfersIn.length > input.rules.transferCap) return null;
  const bankAfterTenths =
    input.bankTenths +
    transfersOut.reduce(
      (total, elementId) =>
        total + requiredCurrent(current, elementId).sellingPriceTenths,
      0,
    ) -
    transfersIn.reduce(
      (total, elementId) =>
        total + requiredPlayer(players, elementId).buyPriceTenths,
      0,
    );
  if (bankAfterTenths < 0) return null;

  const squadElementIds = [...squad].sort((left, right) => left - right);
  const eventLineup = bestLineup(
    squadElementIds,
    players,
    input.rules,
    "eventPoints",
    true,
  );
  const planningLineup = bestLineup(
    squadElementIds,
    players,
    input.rules,
    "planningPoints",
    false,
  );
  if (eventLineup === null || planningLineup === null) return null;
  const paidTransfers =
    input.chipScenario === "free_hit"
      ? 0
      : Math.max(0, transfersIn.length - input.availableFreeTransfers);
  const transferCostPoints = paidTransfers * input.rules.transferCostPoints;
  const starterSet = new Set(eventLineup.elementIds);
  const planningPointsBeforeCost =
    planningLineup.projectedPoints +
    requiredPlayer(players, eventLineup.captainElementId).eventPoints;
  return {
    squadElementIds,
    starterElementIds: eventLineup.elementIds,
    benchElementIds: squadElementIds
      .filter((elementId) => !starterSet.has(elementId))
      .sort(
        (left, right) =>
          requiredPlayer(players, right).eventPoints -
            requiredPlayer(players, left).eventPoints || left - right,
      ),
    captainElementId: eventLineup.captainElementId,
    viceCaptainElementId: eventLineup.viceCaptainElementId,
    transfersIn,
    transfersOut,
    paidTransfers,
    transferCostPoints,
    projectedPointsBeforeCost: eventLineup.projectedPoints,
    netExpectedPoints: eventLineup.projectedPoints - transferCostPoints,
    planningPointsBeforeCost,
    netPlanningPoints: planningPointsBeforeCost - transferCostPoints,
    bankAfterTenths,
    squadQuality: squadElementIds.reduce(
      (total, elementId) =>
        total + requiredPlayer(players, elementId).planningPoints,
      0,
    ),
    chipScenario: input.chipScenario,
  };
}

function isStructurallyValid(
  squad: Set<number>,
  players: Map<number, QuickPlayer>,
  rules: QuickRules,
): boolean {
  if (squad.size !== rules.squadSize) return false;
  for (const position of rules.positions) {
    if (
      [...squad].filter(
        (elementId) =>
          requiredPlayer(players, elementId).positionId === position.positionId,
      ).length !== position.squadCount
    ) {
      return false;
    }
  }
  const clubs = new Map<number, number>();
  for (const elementId of squad) {
    const teamId = requiredPlayer(players, elementId).teamId;
    clubs.set(teamId, (clubs.get(teamId) ?? 0) + 1);
  }
  return [...clubs.values()].every((count) => count <= rules.clubLimit);
}

function bestLineup(
  squad: number[],
  players: Map<number, QuickPlayer>,
  rules: QuickRules,
  pointsField: "planningPoints" | "eventPoints",
  includeCaptain: boolean,
): LineupEvaluation | null {
  const positions = [...rules.positions].sort(
    (left, right) => left.positionId - right.positionId,
  );
  const byPosition = new Map(
    positions.map((position) => [
      position.positionId,
      squad
        .filter(
          (elementId) =>
            requiredPlayer(players, elementId).positionId ===
            position.positionId,
        )
        .sort(
          (left, right) =>
            requiredPlayer(players, right)[pointsField] -
              requiredPlayer(players, left)[pointsField] || left - right,
        ),
    ]),
  );
  let best: LineupEvaluation | null = null;
  const selected: number[] = [];

  const visit = (positionIndex: number, remaining: number): void => {
    if (positionIndex === positions.length) {
      if (remaining !== 0) return;
      const scored = scoreLineup(
        selected,
        players,
        pointsField,
        includeCaptain,
      );
      if (scored === null) return;
      if (
        best === null ||
        scored.projectedPoints > best.projectedPoints + 1e-10 ||
        (Math.abs(scored.projectedPoints - best.projectedPoints) <= 1e-10 &&
          compareIds(scored.elementIds, best.elementIds) < 0)
      ) {
        best = scored;
      }
      return;
    }
    const position = positions[positionIndex]!;
    const candidates = byPosition.get(position.positionId)!;
    const following = positions.slice(positionIndex + 1);
    const followingMinimum = following.reduce(
      (total, rule) => total + rule.lineupMinimum,
      0,
    );
    const followingMaximum = following.reduce(
      (total, rule) => total + rule.lineupMaximum,
      0,
    );
    const minimum = Math.max(
      position.lineupMinimum,
      remaining - followingMaximum,
    );
    const maximum = Math.min(
      position.lineupMaximum,
      candidates.length,
      remaining - followingMinimum,
    );
    for (let count = minimum; count <= maximum; count += 1) {
      selected.push(...candidates.slice(0, count));
      visit(positionIndex + 1, remaining - count);
      selected.splice(selected.length - count, count);
    }
  };

  visit(0, rules.lineupSize);
  return best;
}

function scoreLineup(
  lineup: number[],
  players: Map<number, QuickPlayer>,
  pointsField: "planningPoints" | "eventPoints",
  includeCaptain: boolean,
): LineupEvaluation | null {
  const ranked = lineup
    .filter((elementId) =>
      isCaptainEligiblePositionId(
        requiredPlayer(players, elementId).positionId,
      ),
    )
    .sort(
      (left, right) =>
        requiredPlayer(players, right)[pointsField] -
          requiredPlayer(players, left)[pointsField] || left - right,
    );
  if (ranked.length < 2) return null;
  const captainElementId = ranked[0]!;
  return {
    elementIds: [...lineup].sort((left, right) => left - right),
    captainElementId,
    viceCaptainElementId: ranked[1]!,
    projectedPoints:
      lineup.reduce(
        (total, elementId) =>
          total + requiredPlayer(players, elementId)[pointsField],
        0,
      ) +
      (includeCaptain
        ? requiredPlayer(players, captainElementId)[pointsField]
        : 0),
  };
}

function compareStates(left: EvaluatedState, right: EvaluatedState): number {
  if (left.chipScenario === "free_hit" && right.chipScenario === "free_hit") {
    return (
      right.netPlanningPoints - left.netPlanningPoints ||
      right.bankAfterTenths - left.bankAfterTenths ||
      compareIds(left.squadElementIds, right.squadElementIds)
    );
  }
  return (
    right.netPlanningPoints - left.netPlanningPoints ||
    left.transfersIn.length - right.transfersIn.length ||
    right.squadQuality - left.squadQuality ||
    compareIds(left.squadElementIds, right.squadElementIds)
  );
}

function compareIds(left: number[], right: number[]): number {
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    const difference = left[index]! - right[index]!;
    if (difference !== 0) return difference;
  }
  return left.length - right.length;
}

function requiredPlayer(
  players: Map<number, QuickPlayer>,
  elementId: number,
): QuickPlayer {
  const player = players.get(elementId);
  if (player === undefined)
    throw new Error(`missing candidate forecast for element ${elementId}`);
  return player;
}

function requiredCurrent(
  current: Map<number, QuickSolverInput["currentSquad"][number]>,
  elementId: number,
): QuickSolverInput["currentSquad"][number] {
  const player = current.get(elementId);
  if (player === undefined)
    throw new Error(`missing current squad price for element ${elementId}`);
  return player;
}
