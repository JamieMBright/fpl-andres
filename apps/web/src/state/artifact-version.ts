/**
 * Schema versions for the published JSON artifacts.
 *
 * These files are written by the Python publishers and imported by the app or
 * API at build time. A version moves incompatible shapes to a build failure.
 */

export const PROJECTIONS_SCHEMA_VERSION = 2;
export const SEASON_INPUTS_SCHEMA_VERSION = 6;
export const PROJECTIONS_META_SCHEMA_VERSION = 1;
export const OPENING_SQUAD_SCHEMA_VERSION = 1;
export const SEASON_PLAN_SCHEMA_VERSION = 2;
export const GW1_REVIEW_SCHEMA_VERSION = 2;
export const XSTART_VALIDATION_SCHEMA_VERSION = 3;
export const FPL500_SCHEMA_VERSION = 3;
export const UNDERSTAT_SCHEMA_VERSION = 1;

export class ArtifactVersionError extends Error {
  override name = "ArtifactVersionError";
  constructor(artifact: string, expected: number, found: unknown) {
    super(
      `${artifact} is schema version ${String(found)}, but this build expects ${expected}. ` +
        `Re-run the publisher, or bump the reader.`,
    );
  }
}

export function requireArtifactVersion(
  artifact: string,
  document: unknown,
  expected: number,
): void {
  const found =
    typeof document === "object" && document !== null
      ? (document as { schemaVersion?: unknown }).schemaVersion
      : undefined;
  if (found !== expected) {
    throw new ArtifactVersionError(artifact, expected, found);
  }
}
