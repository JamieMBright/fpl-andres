import meta from "../data/projections-meta.json";
import {
  PROJECTIONS_META_SCHEMA_VERSION,
  requireArtifactVersion,
} from "./artifact-version";

requireArtifactVersion(
  "projections-meta.json",
  meta,
  PROJECTIONS_META_SCHEMA_VERSION,
);

/** Header fields only: the season label costs a kilobyte, not the whole squad. */
export const projectionSeason = meta.season;
export const projectionGeneratedAt = meta.generatedAt;
export const projectionThroughGameweek = meta.throughGameweek;
export const projectionBasis = meta.basis;
