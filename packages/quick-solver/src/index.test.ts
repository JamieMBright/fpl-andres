import { describe, expect, it } from "vitest";

import { regretCases } from "../fixtures/load";
import {
  isCaptainEligiblePositionId,
  quickSolverInputSchema,
  solveQuickPlan,
} from "./index";

const limits = {
  beamWidth: 16,
  candidateLimitPerPosition: 8,
  maxTransfers: 2,
} as const;

describe("bounded quick solver", () => {
  it("refuses an unknown position rather than guessing captain eligibility", () => {
    expect(() => isCaptainEligiblePositionId(5)).toThrow(
      "not an FPL player position",
    );
  });

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

  it("uses current-event points for the XI and armband", () => {
    const base = regretCases[0]!.input;
    const points = new Map([
      [1, { planningPoints: 100, eventPoints: 2 }],
      [2, { planningPoints: 1, eventPoints: 9 }],
      [3, { planningPoints: 100, eventPoints: 3 }],
      [4, { planningPoints: 1, eventPoints: 8 }],
      [5, { planningPoints: 0, eventPoints: 0 }],
      [6, { planningPoints: 0, eventPoints: 0 }],
    ]);
    const input = {
      ...base,
      players: base.players.map((player) => {
        return { ...player, ...points.get(player.elementId)! };
      }),
    };

    const result = solveQuickPlan(input, { ...limits, maxTransfers: 0 });

    expect(result.starterElementIds).toEqual([2, 4]);
    expect(result.captainElementId).toBe(2);
    expect(result.viceCaptainElementId).toBe(4);
    expect(result.projectedPointsBeforeCost).toBe(26);
  });

  it("keeps both armbands on midfielders or forwards", () => {
    const base = regretCases.at(-1)!.input;
    const points = new Map([
      [1, 20],
      [3, 19],
      [4, 18],
      [5, 17],
      [8, 8],
      [9, 7],
      [10, 6],
      [11, 5],
      [12, 4],
      [13, 3],
      [14, 2],
      [15, 1],
    ]);
    const input = {
      ...base,
      players: base.players.map((player) => ({
        ...player,
        planningPoints: points.get(player.elementId) ?? 0,
        eventPoints: points.get(player.elementId) ?? 0,
      })),
    };

    const result = solveQuickPlan(input, { ...limits, maxTransfers: 0 });

    expect(result.captainElementId).toBe(8);
    expect(result.viceCaptainElementId).toBe(9);
  });

  it("does not charge transfer costs in a Free Hit scenario", () => {
    const input = {
      ...regretCases[0]!.input,
      chipScenario: "free_hit" as const,
    };
    const result = solveQuickPlan(input, { ...limits, maxTransfers: 15 });

    expect(result.chipScenario).toBe("free_hit");
    expect(result.paidTransfers).toBe(0);
    expect(result.transferCostPoints).toBe(0);
  });

  it("ranks truncated candidates by feasible squad gain under the club cap", () => {
    const base = regretCases[1]!.input;
    const input = {
      ...base,
      players: [
        {
          ...base.players[0]!,
          teamId: 1,
          planningPoints: 10,
          eventPoints: 10,
        },
        {
          ...base.players[1]!,
          teamId: 2,
          planningPoints: 1,
          eventPoints: 1,
        },
        {
          ...base.players[2]!,
          teamId: 1,
          planningPoints: 9,
          eventPoints: 9,
        },
        {
          ...base.players[2]!,
          elementId: 4,
          teamId: 3,
          planningPoints: 8,
          eventPoints: 8,
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

  it("uses a free transfer on a declared ruled-out incumbent", () => {
    const base = regretCases[0]!.input;
    const result = solveQuickPlan(
      {
        ...base,
        priorityTransferOutElementIds: [2],
      },
      { ...limits, maxTransfers: 1, transferMarginPoints: 100 },
    );

    expect(result.transfersOut).toEqual([2]);
    expect(result.transfersIn).toEqual([5]);
    expect(result.paidTransfers).toBe(0);
    expect(result.reasonCodes).toContain("ruled_out_replacement");
  });

  it("does not force a ruled-out replacement that costs a hit", () => {
    const base = regretCases[0]!.input;
    const result = solveQuickPlan(
      {
        ...base,
        availableFreeTransfers: 0,
        priorityTransferOutElementIds: [2],
      },
      { ...limits, maxTransfers: 1, transferMarginPoints: 100 },
    );

    expect(result.transfersOut).toEqual([]);
    expect(result.reasonCodes).not.toContain("ruled_out_replacement");
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
