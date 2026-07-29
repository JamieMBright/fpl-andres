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
      expect(result.captainElementId).not.toBe(result.viceCaptainElementId);
      expect(result.starterElementIds).toContain(result.captainElementId);
      expect(result.starterElementIds).toContain(result.viceCaptainElementId);
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

    const { transferCostPoints: _, ...incompleteRules } = input.rules;
    expect(() =>
      quickSolverInputSchema.parse({ ...input, rules: incompleteRules }),
    ).toThrow();
  });
});
