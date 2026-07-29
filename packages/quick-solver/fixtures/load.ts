import fullSquadCase from "./full-squad-regret-case.json";
import smallCases from "./regret-cases.json";
import { quickSolverInputSchema, type QuickSolverInput } from "../src/index";
import { z } from "zod";

export interface RegretCase {
  name: string;
  input: QuickSolverInput;
  highsOptimalNetPoints: number;
  maxAllowedRegret: number;
}

const fullSquadInput = quickSolverInputSchema.parse({
  season: fullSquadCase.season,
  event: fullSquadCase.event,
  objective: fullSquadCase.objective,
  priceScenario: fullSquadCase.priceScenario,
  chipScenario: fullSquadCase.chipScenario,
  predictionCutoff: fullSquadCase.predictionCutoff,
  players: z
    .array(
      z.tuple([
        z.int().positive(),
        z.int().positive(),
        z.int().positive(),
        z.number(),
      ]),
    )
    .parse(fullSquadCase.playerRows)
    .map(([elementId, teamId, positionId, expectedPoints]) => ({
      elementId,
      teamId,
      positionId,
      buyPriceTenths: fullSquadCase.buyPriceTenths,
      expectedPoints,
      evidenceLevel: fullSquadCase.evidenceLevel,
      dataAvailableAt: fullSquadCase.dataAvailableAt,
      sourceHashes: [`sha256:${elementId.toString(16).padStart(64, "0")}`],
    })),
  currentSquad: fullSquadCase.currentElementIds.map((elementId) => ({
    elementId,
    sellingPriceTenths: fullSquadCase.sellingPriceTenths,
  })),
  bankTenths: fullSquadCase.bankTenths,
  availableFreeTransfers: fullSquadCase.availableFreeTransfers,
  stateEvidence: fullSquadCase.stateEvidence,
  rules: fullSquadCase.rules,
});

export const regretCases: RegretCase[] = [
  ...smallCases.cases.map((fixture) => ({
    ...fixture,
    input: quickSolverInputSchema.parse(fixture.input),
  })),
  {
    name: fullSquadCase.name,
    input: fullSquadInput,
    highsOptimalNetPoints: fullSquadCase.highsOptimalNetPoints,
    maxAllowedRegret: fullSquadCase.maxAllowedRegret,
  },
];
