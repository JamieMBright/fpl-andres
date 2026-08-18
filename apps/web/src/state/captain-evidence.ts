import type { CaptaincyInterval } from "./captaincy-verdict";

export interface OwnedCaptainPolicy {
  label: string;
  gameweeks: number;
  meanChosenPoints: number | null;
  meanReachableCeiling: number | null;
  ownedSquadRegret: number | null;
  shareOfReachableCeiling?: number | null;
  perfectWeeks?: number;
  blankRate?: number | null;
}

export interface OwnedCaptainSeason {
  season: string;
  ownedCaptainPolicies?: readonly OwnedCaptainPolicy[];
}

interface RawCaptaincyInterval {
  label: string;
  weeks: number;
  meanPoints: number | null;
  improvement: number | null;
  lower: number | null;
  upper: number | null;
  better: boolean;
  familySize?: number;
}

export interface CaptainEvidenceReport {
  captainEvidenceScope?: string;
  captainSignificance?: readonly RawCaptaincyInterval[];
  seasons?: readonly OwnedCaptainSeason[];
}

export interface CaptainEvidence {
  significance: readonly CaptaincyInterval[];
  seasons: readonly OwnedCaptainSeason[];
}

export function captainEvidence(
  report: CaptainEvidenceReport,
): CaptainEvidence {
  if (report.captainEvidenceScope !== "model_owned_xi") {
    return { significance: [], seasons: [] };
  }
  return {
    significance: (report.captainSignificance ?? []).flatMap((entry) =>
      entry.meanPoints === null ||
      entry.improvement === null ||
      entry.lower === null ||
      entry.upper === null
        ? []
        : [
            {
              ...entry,
              meanPoints: entry.meanPoints,
              improvement: entry.improvement,
              lower: entry.lower,
              upper: entry.upper,
            },
          ],
    ),
    seasons: (report.seasons ?? []).filter(
      (season) => (season.ownedCaptainPolicies?.length ?? 0) > 0,
    ),
  };
}
