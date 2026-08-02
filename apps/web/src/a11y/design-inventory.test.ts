import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Audit item #202. A component inventory is only useful while it is complete.
 * This is the part that rots first, so it is the part with a test.
 *
 * The accessibility checklist beside it names the test that enforces each rule,
 * which is checked here too: a checklist entry pointing at a file that no
 * longer exists is worse than no entry, because it claims coverage.
 */

const ROOT = join(__dirname, "..", "..", "..", "..");
const COMPONENTS = join(ROOT, "apps", "web", "src", "components");
const DESIGN = readFileSync(join(ROOT, "DESIGN.md"), "utf-8");

function componentNames(): string[] {
  return readdirSync(COMPONENTS)
    .filter((entry) => entry.endsWith(".tsx") && !entry.includes(".test."))
    .map((entry) => entry.replace(/\.tsx$/, ""));
}

describe("component inventory", () => {
  it("finds components at all, so this suite is not vacuous", () => {
    expect(componentNames().length).toBeGreaterThan(10);
  });

  it("lists every component that exists", () => {
    const missing = componentNames().filter(
      (name) => !DESIGN.includes(`\`${name}\``),
    );
    expect(missing).toEqual([]);
  });

  it("lists nothing that no longer exists", () => {
    const inventory =
      DESIGN.split("## Component inventory")[1]?.split("##")[0] ?? "";
    const listed = [...inventory.matchAll(/^\| `(\w+)`/gm)].map(
      (match) => match[1],
    );
    const present = new Set(componentNames());

    expect(listed.length).toBeGreaterThan(10);
    expect(listed.filter((name) => name && !present.has(name))).toEqual([]);
  });
});

describe("accessibility checklist", () => {
  const CHECKLIST_TESTS = [
    "contrast.spec.ts",
    "static-accessibility.test.ts",
    "responsive.spec.ts",
    "team-entry.spec.ts",
  ];

  it("names a test for every rule", () => {
    const section =
      DESIGN.split("## Accessibility checklist")[1]?.split("\n## ")[0] ?? "";
    const rows = [
      // Padding-tolerant: prettier realigns markdown tables, and a regex
      // anchored on single spaces silently matches nothing after `pnpm format`.
      ...section.matchAll(/^\|\s*(?!Rule)(?!-)(.+?)\s*\|\s*`(.+?)`\s*\|$/gm),
    ];

    expect(rows.length).toBeGreaterThan(8);
    for (const [, , enforcer] of rows) {
      expect(CHECKLIST_TESTS).toContain(enforcer);
    }
  });

  it("every named enforcer actually exists", () => {
    const searchRoots = [
      join(ROOT, "apps", "web", "e2e"),
      join(ROOT, "apps", "web", "src", "a11y"),
    ];
    const present = new Set(searchRoots.flatMap((root) => readdirSync(root)));

    for (const enforcer of CHECKLIST_TESTS) {
      expect(present.has(enforcer), `${enforcer} is claimed but missing`).toBe(
        true,
      );
    }
  });

  it("says which rules are deliberately not enforced", () => {
    // A checklist that only lists what it checks implies the rest is covered.
    expect(DESIGN).toContain("deliberately **not** enforced");
    expect(DESIGN).toContain("Colour is never the only signal");
    expect(DESIGN).toContain("prefers-reduced-motion");
  });
});
