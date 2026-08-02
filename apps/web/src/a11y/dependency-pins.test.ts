import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Audit item #184. Every dependency is pinned exactly, which is not the npm
 * default and therefore looks like an oversight to anyone who has not read
 * CONTRIBUTING.md. This makes it a rule rather than a habit.
 *
 * The reason it matters most for `zod`: the schemas in packages/contracts are
 * the browser half of a contract whose other half is a Pydantic model. A caret
 * range lets a minor release change coercion behaviour, and the two halves stop
 * agreeing with the Python suite still green because nothing there moved.
 */

const ROOT = join(__dirname, "..", "..", "..", "..");

const MANIFESTS = [
  "package.json",
  "apps/web/package.json",
  "packages/contracts/package.json",
  "packages/quick-solver/package.json",
];

interface Manifest {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
}

function specifiers(): { manifest: string; name: string; spec: string }[] {
  return MANIFESTS.flatMap((manifest) => {
    const parsed = JSON.parse(
      readFileSync(join(ROOT, manifest), "utf-8"),
    ) as Manifest;
    return [
      ...Object.entries(parsed.dependencies ?? {}),
      ...Object.entries(parsed.devDependencies ?? {}),
    ].map(([name, spec]) => ({ manifest, name, spec }));
  });
}

describe("dependency pinning", () => {
  it("finds dependencies at all, so this suite is not vacuous", () => {
    expect(specifiers().length).toBeGreaterThan(10);
  });

  it("pins every dependency to an exact version", () => {
    const ranged = specifiers()
      .filter(({ spec }) => !spec.startsWith("workspace:"))
      .filter(({ spec }) => !/^\d/.test(spec))
      .map(({ manifest, name, spec }) => `${manifest}: ${name}@${spec}`);

    expect(ranged).toEqual([]);
  });

  it("keeps the three that matter most exactly pinned", () => {
    // Named individually because these are the ones whose drift is silent:
    // zod breaks the cross-language contract, typescript breaks the build on a
    // commit that touched nothing, @vercel/node changes the runtime the api/
    // types were checked against.
    const byName = new Map(
      specifiers().map((entry) => [entry.name, entry.spec]),
    );

    for (const critical of ["zod", "typescript", "@vercel/node"]) {
      const spec = byName.get(critical);
      expect(
        spec,
        `${critical} should be a dependency somewhere`,
      ).toBeDefined();
      expect(spec).toMatch(/^\d+\.\d+\.\d+/);
    }
  });

  it("explains the decision where someone would look before loosening one", () => {
    const contributing = readFileSync(join(ROOT, "CONTRIBUTING.md"), "utf-8");

    expect(contributing).toContain("Dependencies are pinned exactly");
    expect(contributing).toContain("zod");
    expect(contributing).toContain("@vercel/node");
  });
});
