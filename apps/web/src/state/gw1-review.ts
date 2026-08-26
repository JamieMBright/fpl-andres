import review from "../data/gw1-review.json";
import {
  GW1_REVIEW_SCHEMA_VERSION,
  requireArtifactVersion,
} from "./artifact-version";

export type Gw1ReviewBand = "below" | "as_projected" | "above" | "haul";

export interface Gw1ReviewActual {
  starts: number;
  minutes: number;
  goals: number;
  assists: number;
  cleanSheets: number;
  goalsConceded: number;
  ownGoals: number;
  penaltiesSaved: number;
  penaltiesMissed: number;
  yellowCards: number;
  redCards: number;
  saves: number;
  bonus: number;
  defensiveContribution: number;
}

export interface Gw1ReviewPick {
  elementId: number;
  squadPosition: number;
  multiplier: number;
  isCaptain: boolean;
  isViceCaptain: boolean;
  identity: {
    code: number;
    name: string;
    position: "GKP" | "DEF" | "MID" | "FWD";
    club: string;
    teamId: number;
    priceTenths: number;
  };
  actualPoints: number;
  countedPoints: number;
  frozenXpts: number;
  opponentNeutralXpts: number;
  delta: number;
  band: Gw1ReviewBand;
  startRateAsShipped: number;
  actual: Gw1ReviewActual;
}

export interface Gw1Review {
  season: string;
  event: 1;
  generatedAt: string;
  canonicalManifestRevision: string;
  recordedCodeRevision: string;
  canonicalModelVersion: string;
  canonicalDeadline: string;
  canonicalFrozenAt: string;
  evidence: {
    frozenInputs: string;
    liveSourceHash: string;
    liveCapturedAt: string;
    picksSourceHash: string;
    picksObservedAt: string;
    level: "observed";
  };
  team: {
    entryId: number;
    points: number;
    benchPoints: number;
    activeChip: string | null;
  };
  picks: readonly Gw1ReviewPick[];
}

export function readGw1Review(document: unknown): Gw1Review {
  requireArtifactVersion(
    "gw1-review.json",
    document,
    GW1_REVIEW_SCHEMA_VERSION,
  );
  if (typeof document !== "object" || document === null) {
    throw new Error("gw1-review.json was not an object");
  }
  const candidate = document as {
    event?: unknown;
    picks?: unknown;
    team?: { points?: unknown; benchPoints?: unknown };
  };
  if (
    candidate.event !== 1 ||
    !Array.isArray(candidate.picks) ||
    candidate.picks.length !== 15 ||
    typeof candidate.team?.points !== "number" ||
    typeof candidate.team.benchPoints !== "number"
  ) {
    throw new Error(
      "gw1-review.json is missing its settled fifteen and totals",
    );
  }
  return document as unknown as Gw1Review;
}

export const GW1_REVIEW = readGw1Review(review);
