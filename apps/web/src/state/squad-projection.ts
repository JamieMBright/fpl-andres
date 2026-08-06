import projections from "../data/projections.json";
import meta from "../data/projections-meta.json";
import {
  PROJECTIONS_META_SCHEMA_VERSION,
  PROJECTIONS_SCHEMA_VERSION,
  requireArtifactVersion,
} from "./artifact-version";

requireArtifactVersion(
  "projections.json",
  projections,
  PROJECTIONS_SCHEMA_VERSION,
);
requireArtifactVersion(
  "projections-meta.json",
  meta,
  PROJECTIONS_META_SCHEMA_VERSION,
);

/** One player's record from the last completed season, as published. */
export interface PlayerProjection {
  code: number;
  name: string;
  position: string;
  priceTenths: number | null;
  expectedPoints: number;
  /** The same match on his best afternoon. */
  expectedCeiling: number;
  /** How many times his ordinary afternoon his best one is. */
  ceilingRatio: number;
  expectedMinutes: number;
  probabilityAppear: number;
  probabilityStart: number;
  appearances: number;
  floor: number | null;
  median: number | null;
  ceiling: number | null;
  returnRate: number | null;
  blankRate: number | null;
  /** Yellow cards last season, the input to the suspension derate. */
  yellowCards: number;
  /** What the suspension risk costs him, as a share of his points kept. */
  suspensionMultiplier: number;
  /** What `expectedPoints` is made of, before the derate. */
  routes: {
    appearance: number;
    attacking: number;
    cleanSheet: number;
    bonus: number;
    saves: number;
    conceding: number;
    discipline: number;
    defensiveContribution: number;
  };
  evidence: string;
}

interface Artifact {
  generatedAt: string;
  season: string;
  throughGameweek: number;
  basis: string;
  players: PlayerProjection[];
}

const artifact = projections as Artifact;

const byCode = new Map(artifact.players.map((player) => [player.code, player]));

export const projectionSeason = meta.season;
export const projectionGeneratedAt = meta.generatedAt;

/** The published record for a player, or null when there is no evidence. */
export function projectionFor(
  code: number | undefined,
): PlayerProjection | null {
  return code === undefined ? null : (byCode.get(code) ?? null);
}

/** Every published record, for comparisons that need a population. */
export function allProjections(): readonly PlayerProjection[] {
  return artifact.players;
}

export interface SquadProjection {
  /** Players in the squad we have a record for, best expectation first. */
  covered: PlayerProjection[];
  /** Names of squad members with no record at all. */
  missing: string[];
  /** Sum over the eleven strongest, ignoring formation. Null when incomplete. */
  strongestEleven: number | null;
}

interface SquadMember {
  name: string;
  code: number | undefined;
}

/**
 * Join a squad to the published record.
 *
 * Nothing is imputed for a player without a record. A promoted-club debutant
 * genuinely has no Premier League evidence, and filling the gap with a
 * position average would turn an unknown into a number the page cannot defend.
 */
export function squadProjection(members: SquadMember[]): SquadProjection {
  const covered: PlayerProjection[] = [];
  const missing: string[] = [];

  for (const member of members) {
    const projection = projectionFor(member.code);
    if (projection) covered.push(projection);
    else missing.push(member.name);
  }

  covered.sort((left, right) => right.expectedPoints - left.expectedPoints);

  return {
    covered,
    missing,
    strongestEleven:
      missing.length > 0 || covered.length < 11
        ? null
        : round(
            covered
              .slice(0, 11)
              .reduce((total, player) => total + player.expectedPoints, 0),
          ),
  };
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}
