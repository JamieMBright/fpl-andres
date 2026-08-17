/**
 * Schema versions for the published JSON artifacts.
 *
 * These files are written by the Python publishers and imported
 * here at build time. Nothing recorded which shape they were in, so a change to
 * a writer would have been picked up silently: a field quietly absent,
 * `undefined` where a number was expected, and a page that renders wrongly
 * rather than refusing.
 *
 * Because the artifacts are imported rather than fetched, this check runs at
 * build time and fails CI. That is the earliest place it can fail, which is the
 * point of having it at all.
 *
 * These numbers must match `python/fpl_andres/artifacts.py`. A test asserts
 * that they do, because two constants that are meant to agree and are never
 * compared will eventually not.
 */

export const PROJECTIONS_SCHEMA_VERSION = 2;
export const SEASON_INPUTS_SCHEMA_VERSION = 4;
export const PROJECTIONS_META_SCHEMA_VERSION = 1;
export const OPENING_SQUAD_SCHEMA_VERSION = 1;
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

/**
 * Refuse an artifact this build does not understand.
 *
 * Refusing rather than degrading, because the alternative is rendering a squad
 * from a document whose fields no longer mean what the reader thinks they do,
 * and every value on the page would look plausible.
 */
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
