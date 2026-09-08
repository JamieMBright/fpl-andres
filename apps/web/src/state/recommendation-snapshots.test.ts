import { describe, expect, it } from "vitest";

import type { SolvedGameweek, SolverPlayer } from "./season-solver";
import {
  compareRecommendationToActual,
  recommendationSnapshotFromSolvedGameweek,
  shouldRecordRecommendation,
  type RecommendationSnapshot,
} from "./recommendation-snapshots";

const player = (elementId: number): SolverPlayer =>
  ({
    id: elementId,
    code: elementId * 10,
    name: `Player ${elementId}`,
    club: "TEST",
    position: "MID",
    priceTenths: 100,
  }) as SolverPlayer;

const solved = {
  event: 4,
  deadline: "2026-09-12T10:30:00Z",
  confidence: "firm",
  starters: Array.from({ length: 11 }, (_, index) => player(index + 1)),
  bench: [player(12), player(13), player(14), player(15)],
  captain: player(1),
  viceCaptain: player(2),
  transfersIn: [player(16)],
  transfersOut: [player(17)],
  projectedPoints: 64.2,
  netExpectedPoints: 60.2,
  paidTransfers: 1,
  transferCostPoints: 4,
  bankAfterTenths: 7,
  budgetBeforeTenths: 1_000,
  freeTransfersBefore: 2,
  expected: {},
  opponents: {},
  difficulty: {},
} as unknown as SolvedGameweek;

const baseSnapshot: RecommendationSnapshot = {
  season: "2026-27",
  entryId: 212279,
  event: 4,
  deadline: solved.deadline,
  modelVersion: "8.17",
  starters: solved.starters.map(({ id }) => id),
  bench: solved.bench.map(({ id }) => id),
  captain: solved.captain.id,
  viceCaptain: solved.viceCaptain.id,
  transferIn: 16,
  transferOut: 17,
  chip: null,
  projectedPoints: 64.2,
  netExpectedPoints: 60.2,
  paidTransfers: 1,
  transferCost: 4,
  confidence: "firm",
  recordedAt: "2026-09-08T08:00:00Z",
  sourceReference: "season-plan:8.17",
};

describe("recommendation snapshots", () => {
  it("serializes only derived recommendation fields", () => {
    const snapshot = recommendationSnapshotFromSolvedGameweek(
      "2026-27",
      212279,
      "8.17",
      solved,
      "2026-09-08T08:00:00Z",
      "season-plan:8.17",
    );

    expect(snapshot).toEqual(baseSnapshot);
    expect(JSON.stringify(snapshot)).not.toContain("bankAfterTenths");
    expect(JSON.stringify(snapshot)).not.toContain("freeTransfersBefore");
    expect(JSON.stringify(snapshot)).not.toContain("budgetBeforeTenths");
  });

  it("rejects malformed snapshots instead of returning a partial display", () => {
    expect(() =>
      recommendationSnapshotFromSolvedGameweek(
        "2026-27",
        212279,
        "8.17",
        { ...solved, starters: solved.starters.slice(1) },
        "2026-09-08T08:00:00Z",
      ),
    ).toThrow();
  });

  it("only records a complete published manager solve", () => {
    expect(
      shouldRecordRecommendation({
        teamStatus: "ready",
        teamSource: "published",
        solveStatus: "done",
        gameweek: solved,
        isGenericOpening: false,
        isDeclaredOnly: false,
      }),
    ).toBe(true);
    expect(
      shouldRecordRecommendation({
        teamStatus: "ready",
        teamSource: "declared",
        solveStatus: "done",
        gameweek: solved,
        isGenericOpening: false,
        isDeclaredOnly: true,
      }),
    ).toBe(false);
    expect(
      shouldRecordRecommendation({
        teamStatus: "ready",
        teamSource: "published",
        solveStatus: "solving",
        gameweek: solved,
        isGenericOpening: false,
        isDeclaredOnly: false,
      }),
    ).toBe(false);
  });

  it("compares the saved recommendation with the submitted team", () => {
    expect(
      compareRecommendationToActual(
        baseSnapshot,
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18],
        3,
        4,
      ),
    ).toEqual({
      recommendedAndSubmitted: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
      recommendedButAbsent: [15],
      submittedButNotRecommended: [18],
      captainDifferent: true,
      viceCaptainDifferent: true,
      deadline: baseSnapshot.deadline,
      modelVersion: baseSnapshot.modelVersion,
      recordedAt: baseSnapshot.recordedAt,
    });
  });
});
