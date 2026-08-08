import { describe, expect, it } from "vitest";

import {
  ArtifactVersionError,
  OPENING_SQUAD_SCHEMA_VERSION,
  PROJECTIONS_META_SCHEMA_VERSION,
  PROJECTIONS_SCHEMA_VERSION,
  requireArtifactVersion,
} from "./artifact-version";

/**
 * The same version gate, from the reader's side.
 *
 * The check has to refuse rather than degrade. Degrading means rendering a
 * squad from a document whose fields no longer mean what the reader thinks they
 * do, and every value on the page would look plausible -- which is the failure
 * mode a version guard exists to prevent, not a softer version of it.
 */

describe("requireArtifactVersion", () => {
  it("accepts the version this build was written against", () => {
    expect(() =>
      requireArtifactVersion("a.json", { schemaVersion: 1, players: [] }, 1),
    ).not.toThrow();
  });

  it.each([
    ["an older version", { schemaVersion: 0 }],
    ["a newer version", { schemaVersion: 2 }],
    ["no version at all", { players: [] }],
    ["a string version", { schemaVersion: "1" }],
    ["a null version", { schemaVersion: null }],
    ["not an object", "1"],
    ["null", null],
    ["an array", []],
  ])("refuses %s", (_label, document) => {
    expect(() => requireArtifactVersion("a.json", document, 1)).toThrow(
      ArtifactVersionError,
    );
  });

  it("names the artifact, both versions and what to do", () => {
    // An error that says only "version mismatch" sends someone to read the
    // code to find out which of five files is stale.
    try {
      requireArtifactVersion("projections.json", { schemaVersion: 3 }, 1);
      expect.unreachable();
    } catch (caught) {
      const message = (caught as Error).message;
      expect(message).toContain("projections.json");
      expect(message).toContain("3");
      expect(message).toContain("1");
      expect(message).toContain("Re-run the publisher");
    }
  });

  it("reports a missing version as undefined rather than pretending it is zero", () => {
    try {
      requireArtifactVersion("a.json", {}, 1);
      expect.unreachable();
    } catch (caught) {
      expect((caught as Error).message).toContain("undefined");
    }
  });
});

describe("declared versions", () => {
  it("are positive integers", () => {
    for (const version of [
      PROJECTIONS_SCHEMA_VERSION,
      PROJECTIONS_META_SCHEMA_VERSION,
      OPENING_SQUAD_SCHEMA_VERSION,
    ]) {
      expect(Number.isInteger(version)).toBe(true);
      expect(version).toBeGreaterThanOrEqual(1);
    }
  });
});

describe("the committed artifacts", () => {
  it("load without throwing, which is the build-time check", async () => {
    // Importing these modules runs the guard. If a publisher changed shape
    // without a bump, this import fails and so does the build -- which is the
    // earliest place the mismatch can be caught.
    await expect(import("./projection-meta")).resolves.toBeDefined();
    await expect(import("./squad-projection")).resolves.toBeDefined();
    await expect(import("./fixture-run")).resolves.toBeDefined();
  });
});
