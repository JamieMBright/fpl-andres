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

export interface XStartValidationEvent {
  generatedAt: string;
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
  clubs: readonly XStartClubValidation[];
}

export interface XStartValidation {
  generatedAt: string;
  season: string;
  events: readonly XStartValidationEvent[];
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
    season?: unknown;
    events?: unknown;
  };
  if (
    typeof candidate.season !== "string" ||
    !Array.isArray(candidate.events)
  ) {
    throw new Error("xstart-validation.json is missing its event series");
  }
  for (const event of candidate.events as XStartValidationEvent[]) {
    if (
      event.field !== "probabilitySixtyMinutesAsShipped" ||
      typeof event.population?.count !== "number" ||
      !Array.isArray(event.clubs) ||
      event.clubs.length !== 20
    ) {
      throw new Error("xstart-validation.json has an incomplete event");
    }
  }
  return document as unknown as XStartValidation;
}

export function latestXStartEvent(
  document: XStartValidation,
): XStartValidationEvent {
  const latest = [...document.events].sort(
    (left, right) => right.event - left.event,
  )[0];
  if (!latest) throw new Error("xstart-validation.json has no settled events");
  return latest;
}

export const XSTART_VALIDATION = readXStartValidation(validation);
