import { useEffect, useState } from "react";
import { z } from "zod";

import type { SolvedGameweek } from "./season-solver";

const elementId = z.number().int().positive();
const snapshotSchema = z
  .object({
    season: z.string().regex(/^\d{4}-\d{2}$/),
    entryId: elementId,
    event: z.number().int().min(1).max(47),
    deadline: z.iso.datetime(),
    modelVersion: z.string().min(1),
    starters: z.array(elementId).length(11),
    bench: z.array(elementId).length(4),
    captain: elementId,
    viceCaptain: elementId,
    transferIn: elementId.nullable(),
    transferOut: elementId.nullable(),
    chip: z.enum(["Free Hit", "Wildcard"]).nullable(),
    projectedPoints: z.number().finite(),
    netExpectedPoints: z.number().finite(),
    paidTransfers: z.number().int().min(0).max(47),
    transferCost: z.number().finite().min(0),
    confidence: z.enum(["firm", "projected", "provisional"]),
    recordedAt: z.iso.datetime(),
    sourceReference: z.string().min(1).max(500).nullable(),
  })
  .superRefine((snapshot, context) => {
    const squad = [...snapshot.starters, ...snapshot.bench];
    if (new Set(squad).size !== squad.length) {
      context.addIssue({
        code: "custom",
        path: ["starters"],
        message: "players must be unique",
      });
    }
    if (!snapshot.starters.includes(snapshot.captain)) {
      context.addIssue({
        code: "custom",
        path: ["captain"],
        message: "captain must start",
      });
    }
    if (!snapshot.starters.includes(snapshot.viceCaptain)) {
      context.addIssue({
        code: "custom",
        path: ["viceCaptain"],
        message: "vice-captain must start",
      });
    }
    if (snapshot.captain === snapshot.viceCaptain) {
      context.addIssue({
        code: "custom",
        path: ["viceCaptain"],
        message: "captain and vice-captain must differ",
      });
    }
    if ((snapshot.transferIn === null) !== (snapshot.transferOut === null)) {
      context.addIssue({
        code: "custom",
        path: ["transferIn"],
        message: "transfers must be a pair",
      });
    }
  });

export type RecommendationSnapshot = z.infer<typeof snapshotSchema>;
const STORAGE_PREFIX = "fpl-andres:recommendation-snapshot:v1";

function cacheKey(entryId: number): string {
  return `${STORAGE_PREFIX}:${String(entryId)}`;
}

export type SnapshotSolveEligibility = {
  teamStatus: "ready" | "idle" | "loading" | "failed";
  teamSource: "published" | "declared" | undefined;
  solveStatus: "idle" | "solving" | "done" | "failed";
  gameweek: SolvedGameweek | undefined;
  isGenericOpening: boolean;
  isDeclaredOnly: boolean;
};

export function parseRecommendationSnapshot(
  value: unknown,
): RecommendationSnapshot | null {
  const parsed = snapshotSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function readRecommendationSnapshotCache(
  storage: Storage,
  entryId: number,
): RecommendationSnapshot | null {
  const serialized = storage.getItem(cacheKey(entryId));
  if (serialized === null) return null;
  try {
    const snapshot = parseRecommendationSnapshot(JSON.parse(serialized));
    if (!snapshot || snapshot.entryId !== entryId) {
      storage.removeItem(cacheKey(entryId));
      return null;
    }
    return snapshot;
  } catch {
    storage.removeItem(cacheKey(entryId));
    return null;
  }
}

function writeRecommendationSnapshotCache(
  storage: Storage,
  snapshot: RecommendationSnapshot,
): void {
  storage.setItem(cacheKey(snapshot.entryId), JSON.stringify(snapshot));
}

export function shouldRecordRecommendation(
  eligibility: SnapshotSolveEligibility,
): boolean {
  return (
    eligibility.teamStatus === "ready" &&
    eligibility.teamSource === "published" &&
    eligibility.solveStatus === "done" &&
    eligibility.gameweek !== undefined &&
    !eligibility.isGenericOpening &&
    !eligibility.isDeclaredOnly &&
    eligibility.gameweek.starters.length === 11 &&
    eligibility.gameweek.bench.length === 4
  );
}

export function recommendationSnapshotFromSolvedGameweek(
  season: string,
  entryId: number,
  modelVersion: string,
  gameweek: SolvedGameweek,
  recordedAt: string,
  sourceReference: string | undefined = undefined,
): RecommendationSnapshot {
  const snapshot = {
    season,
    entryId,
    event: gameweek.event,
    deadline: gameweek.deadline,
    modelVersion,
    starters: gameweek.starters.map(({ id }) => id),
    bench: gameweek.bench.map(({ id }) => id),
    captain: gameweek.captain.id,
    viceCaptain: gameweek.viceCaptain.id,
    transferIn: gameweek.transfersIn[0]?.id ?? null,
    transferOut: gameweek.transfersOut[0]?.id ?? null,
    chip: gameweek.chip ?? null,
    projectedPoints: gameweek.projectedPoints,
    netExpectedPoints: gameweek.netExpectedPoints,
    paidTransfers: gameweek.paidTransfers,
    transferCost: gameweek.transferCostPoints,
    confidence: gameweek.confidence,
    recordedAt,
    sourceReference: sourceReference ?? null,
  };
  const parsed = snapshotSchema.safeParse(snapshot);
  if (!parsed.success)
    throw new TypeError("solver returned an invalid recommendation");
  return parsed.data;
}

export async function readRecommendationSnapshot(
  entryId: number,
  fetchApi: typeof fetch = fetch,
): Promise<RecommendationSnapshot | null> {
  const response = await fetchApi(
    `/api/recommendation-snapshot?entryId=${String(entryId)}`,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) return null;
  const body: unknown = await response.json();
  if (typeof body !== "object" || body === null || !("snapshot" in body)) {
    return null;
  }
  return parseRecommendationSnapshot(body.snapshot);
}

export async function recordRecommendationSnapshot(
  snapshot: RecommendationSnapshot,
  fetchApi: typeof fetch = fetch,
): Promise<boolean> {
  const serialized = JSON.stringify(snapshot);
  const response = await fetchApi("/api/recommendation-snapshot", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: serialized,
  });
  return response.ok;
}

export function useRecommendationSnapshot(
  entryId: number | null,
): RecommendationSnapshot | null {
  const [state, setState] = useState<{
    entryId: number | null;
    snapshot: RecommendationSnapshot | null;
  }>(() => ({
    entryId,
    snapshot:
      entryId === null || typeof window === "undefined"
        ? null
        : readRecommendationSnapshotCache(window.localStorage, entryId),
  }));

  useEffect(() => {
    if (entryId === null) return;
    let active = true;
    void readRecommendationSnapshot(entryId)
      .catch(() => null)
      .then((snapshot) => {
        if (!active) return;
        if (snapshot)
          writeRecommendationSnapshotCache(window.localStorage, snapshot);
        setState({ entryId, snapshot });
      });
    return () => {
      active = false;
    };
  }, [entryId]);

  return state.entryId === entryId ? state.snapshot : null;
}

export interface RecommendationComparison {
  recommendedAndSubmitted: number[];
  recommendedButAbsent: number[];
  submittedButNotRecommended: number[];
  captainDifferent: boolean;
  viceCaptainDifferent: boolean;
  deadline: string;
  modelVersion: string;
  recordedAt: string;
}

export function compareRecommendationToActual(
  snapshot: RecommendationSnapshot,
  submittedSquad: readonly number[],
  captain: number,
  viceCaptain: number,
): RecommendationComparison {
  const recommended = new Set([...snapshot.starters, ...snapshot.bench]);
  const submitted = new Set(submittedSquad);
  return {
    recommendedAndSubmitted: [...recommended].filter((id) => submitted.has(id)),
    recommendedButAbsent: [...recommended].filter((id) => !submitted.has(id)),
    submittedButNotRecommended: [...submitted].filter(
      (id) => !recommended.has(id),
    ),
    captainDifferent: snapshot.captain !== captain,
    viceCaptainDifferent: snapshot.viceCaptain !== viceCaptain,
    deadline: snapshot.deadline,
    modelVersion: snapshot.modelVersion,
    recordedAt: snapshot.recordedAt,
  };
}
