import { describe, expect, it } from "vitest";

import { regretCases } from "../fixtures/load";
import { quickSolverInputSchema, solveQuickPlan } from "./index";

const limits = {
  beamWidth: 16,
  candidateLimitPerPosition: 8,
  maxTransfers: 2,
} as const;

describe("bounded quick solver", () => {
  it("stays within declared regret on HiGHS-verified fixtures", () => {
    for (const fixture of regretCases) {
      const result = solveQuickPlan(fixture.input, limits);
      const regret = fixture.highsOptimalNetPoints - result.netExpectedPoints;

      expect(
        regret,
        `${fixture.name} exceeded its HiGHS reference`,
      ).toBeGreaterThanOrEqual(-1e-8);
      expect(regret, fixture.name).toBeLessThanOrEqual(
        fixture.maxAllowedRegret + 1e-8,
      );
      expect(result.solver).toBe("quick-beam");
      expect(result.solverStatus).toBe("bounded");
      expect(result.objective).toBe("expected_value");
      expect(result.priceScenario).toBe("current_prices");
      expect(result.chipScenario).toBe("none");
      expect(result.captainElementId).not.toBe(result.viceCaptainElementId);
      expect(result.starterElementIds).toContain(result.captainElementId);
      expect(result.starterElementIds).toContain(result.viceCaptainElementId);
      expect(result.sourceHashes).toContain(
        fixture.input.stateEvidence.managerOverridesHash,
      );
      expect(result.dataAvailableAt).toBe(fixture.input.predictionCutoff);
    }
  });

  it("is deterministic under candidate input order", () => {
    const input = regretCases[0]!.input;
    const first = solveQuickPlan(input, limits);
    const second = solveQuickPlan(
      { ...input, players: [...input.players].reverse() },
      limits,
    );

    expect(second).toEqual(first);
  });

  it("reports and obeys hard search bounds", () => {
    const input = regretCases[0]!.input;
    const result = solveQuickPlan(input, {
      beamWidth: 1,
      candidateLimitPerPosition: 1,
      maxTransfers: 1,
    });

    expect(result.diagnostics.beamWidth).toBe(1);
    expect(result.diagnostics.maxTransfers).toBe(1);
    expect(result.diagnostics.maximumFrontierSize).toBeLessThanOrEqual(1);
    expect(result.diagnostics.deepestTransferCount).toBeLessThanOrEqual(1);
    expect(result.diagnostics.truncated).toBe(true);
    expect(result.reasonCodes).toContain("bounded_search_truncated");
  });

  it("ranks truncated candidates by feasible squad gain under the club cap", () => {
    const base = regretCases[1]!.input;
    const input = {
      ...base,
      players: [
        { ...base.players[0]!, teamId: 1, expectedPoints: 10 },
        { ...base.players[1]!, teamId: 2, expectedPoints: 1 },
        { ...base.players[2]!, teamId: 1, expectedPoints: 9 },
        {
          ...base.players[2]!,
          elementId: 4,
          teamId: 3,
          expectedPoints: 8,
          sourceHashes: [
            "sha256:4444444444444444444444444444444444444444444444444444444444444444",
          ],
        },
      ],
      availableFreeTransfers: 1,
      rules: { ...base.rules, clubLimit: 1 },
    };

    const result = solveQuickPlan(input, {
      beamWidth: 4,
      candidateLimitPerPosition: 1,
      maxTransfers: 1,
    });

    expect(result.transfersIn).toEqual([4]);
    expect(result.transfersOut).toEqual([2]);
  });

  it("rejects late evidence and missing controlling transfer cost", () => {
    const input = regretCases[0]!.input;
    expect(() =>
      quickSolverInputSchema.parse({
        ...input,
        players: input.players.map((player, index) =>
          index === 0
            ? { ...player, dataAvailableAt: "2026-09-12T09:00:01Z" }
            : player,
        ),
      }),
    ).toThrow("prediction cutoff");

    const { transferCostPoints: _transferCostPoints, ...incompleteRules } =
      input.rules;
    expect(() =>
      quickSolverInputSchema.parse({ ...input, rules: incompleteRules }),
    ).toThrow();

    const { objective: _objective, ...missingObjective } = input;
    expect(() => quickSolverInputSchema.parse(missingObjective)).toThrow();

    const { chipScenario: _chipScenario, ...missingChipScenario } = input;
    expect(() => quickSolverInputSchema.parse(missingChipScenario)).toThrow();

    expect(() =>
      quickSolverInputSchema.parse({
        ...input,
        stateEvidence: {
          ...input.stateEvidence,
          overridesUpdatedAt: "2026-09-12T09:00:01Z",
        },
      }),
    ).toThrow("manager state");
  });
});
