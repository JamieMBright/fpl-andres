import validation from "../data/xstart-validation.json";
import {
  requireArtifactVersion,
  XSTART_VALIDATION_SCHEMA_VERSION,
} from "./artifact-version";

export interface XStartMetrics {
  count: number;
  brier: number;
  logLoss: number;
  meanForecast: number;
  actualStartRate: number;
}

export interface XStartClubValidation extends XStartMetrics {
  club: string;
  topElevenHits: number;
  actualStarters: number;
  topElevenRecall: number | null;
  selected: readonly {
    elementId: number;
    probability: number;
    started: boolean;
  }[];
  missedStarters: readonly { elementId: number; probability: number }[];
}

export interface XStartValidation {
  generatedAt: string;
  season: string;
  event: number;
  modelVersion: string;
  field: "probabilitySixtyMinutesAsShipped";
  evidence: {
    frozenRevision: string;
    frozenAt: string;
    liveSourceHash: string;
    liveCapturedAt: string;
    level: "observed";
  };
  population: XStartMetrics;
  topEleven: {
    hits: number;
    actualStarters: number;
    recall: number | null;
  };
  reliability: readonly (XStartMetrics & {
    label: string;
    lower: number;
    upper: number;
  })[];
  clubs: readonly XStartClubValidation[];
}

export function readXStartValidation(document: unknown): XStartValidation {
  requireArtifactVersion(
    "xstart-validation.json",
    document,
    XSTART_VALIDATION_SCHEMA_VERSION,
  );
  if (typeof document !== "object" || document === null) {
    throw new Error("xstart-validation.json was not an object");
  }
  const candidate = document as {
    field?: unknown;
    population?: { count?: unknown };
    clubs?: unknown;
  };
  if (
    candidate.field !== "probabilitySixtyMinutesAsShipped" ||
    typeof candidate.population?.count !== "number" ||
    !Array.isArray(candidate.clubs) ||
    candidate.clubs.length !== 20
  ) {
    throw new Error(
      "xstart-validation.json is missing its population and clubs",
    );
  }
  return document as unknown as XStartValidation;
}

export const XSTART_VALIDATION = readXStartValidation(validation);
