import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Audit items #128, #129 and #130.
 *
 * #130 asked for every icon to carry an accessible name or `aria-hidden`, and
 * for that to be asserted rather than inspected. The audit of the current tree
 * found zero violations — so the value here is not the fix, it is turning a
 * state that happens to be correct into one that stays correct.
 *
 * #129 asked for a visible focus outline on scrollable regions carrying
 * `tabIndex={0}`. All eight already use `.squad-table-wrap`, which has one.
 * Asserted here so a ninth region using a different class is caught.
 */

const SOURCE = join(__dirname, "..");

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return path.endsWith(".tsx") && !path.endsWith(".test.tsx") ? [path] : [];
  });
}

function read(path: string): string {
  return readFileSync(path, "utf-8");
}

const files = sourceFiles(SOURCE);

describe("icons", () => {
  const iconNames = new Set<string>();
  for (const file of files) {
    const match = /import \{([^}]+)\} from "lucide-react"/s.exec(read(file));
    if (!match?.[1]) continue;
    for (const name of match[1].split(",")) {
      const trimmed = name.trim();
      if (trimmed) iconNames.add(trimmed);
    }
  }

  it("imports icons at all, so this suite is not vacuous", () => {
    expect(iconNames.size).toBeGreaterThan(5);
  });

  it("every icon is either hidden or named", () => {
    const unlabelled: string[] = [];
    for (const file of files) {
      const source = read(file);
      for (const name of iconNames) {
        const usage = new RegExp(`<${name}\\b([^>]*)/?>`, "g");
        let match = usage.exec(source);
        while (match !== null) {
          const attributes = match[1] ?? "";
          if (
            !attributes.includes("aria-hidden") &&
            !attributes.includes("aria-label")
          ) {
            unlabelled.push(`${file}: <${name}${attributes.trim()}>`);
          }
          match = usage.exec(source);
        }
      }
    }
    // A decorative icon beside a text label must be hidden, or a screen reader
    // reads the label twice. An icon that is the only content of a control must
    // be named, or the control has no name at all.
    expect(unlabelled).toEqual([]);
  });
});

describe("focusable scroll regions", () => {
  const withTabIndex = files.filter((file) =>
    read(file).includes("tabIndex={0}"),
  );

  it("exist, so this suite is not vacuous", () => {
    expect(withTabIndex.length).toBeGreaterThan(0);
  });

  it("all use the class that carries a focus outline", () => {
    const offenders: string[] = [];
    for (const file of withTabIndex) {
      const source = read(file);
      const occurrences = source.split("tabIndex={0}");
      // Each preceding chunk must contain the wrapper class near its end.
      for (const chunk of occurrences.slice(0, -1)) {
        if (!chunk.slice(-400).includes("squad-table-wrap")) {
          offenders.push(file);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the outline is actually defined", () => {
    const styles = read(join(SOURCE, "styles.css"));
    expect(styles).toContain(".squad-table-wrap:focus-visible");
  });

  it("keyboard users are told the region scrolls", () => {
    // A tabbable div with no name is a focus stop that announces nothing.
    for (const file of withTabIndex) {
      expect(read(file)).toMatch(/aria-label="[^"]*Scrollable/);
    }
  });
});

describe("analysis state announcements", () => {
  // Audit item #115 split App.tsx apart: the live region lives with the page
  // that owns the state, and the sentences with the messages module. Reading
  // both keeps this checking the behaviour rather than a file name.
  const page = read(join(SOURCE, "pages", "TeamAnalysisPage.tsx"));
  const messages = read(join(SOURCE, "state", "team-analysis-messages.ts"));

  it("has a polite live region for the analysis state", () => {
    expect(page).toContain('aria-live="polite"');
    expect(page).toContain('role="status"');
  });

  it("keeps the live region out of the visual layout", () => {
    const live = page.slice(
      page.indexOf('aria-live="polite"') - 200,
      page.indexOf('aria-live="polite"') + 200,
    );
    expect(live).toContain("visually-hidden");
  });

  it("does not mark the whole result region live", () => {
    // That would re-read the entire squad on every transition.
    const region = page.slice(
      page.indexOf('aria-label="Analysis result"'),
      page.indexOf('aria-label="Analysis result"') + 300,
    );
    expect(region).not.toContain("aria-live");
  });

  it("announces every state the reducer can produce", () => {
    for (const status of ["loading", "refreshing", "ready", "stale"]) {
      expect(messages).toContain(`case "${status}":`);
    }
  });
});
