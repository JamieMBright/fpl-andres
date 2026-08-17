import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { TELETEXT_PALETTE } from "../kit/teletext";

/**
 * Small frontend surfaces,
 * each either a duplication, a claim nobody checked, or a behaviour documented
 * only to the test suite.
 */

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const styles = readFileSync(resolve(ROOT, "src", "styles.css"), "utf8");
const html = readFileSync(resolve(ROOT, "index.html"), "utf8");
const budget = readFileSync(
  resolve(ROOT, "scripts", "size-budget.mjs"),
  "utf8",
);

describe("stripe custom properties", () => {
  it("declares each stripe gradient once", () => {
    // Four near-identical declarations differing in exactly
    // two numbers, so changing the pattern meant changing it four times and
    // getting three of them right. Two remain -- one per surface -- and the
    // light theme now overrides only the mix strengths.
    //
    // Scoped to the custom properties: an unrelated repeating gradient
    // elsewhere in the sheet is not this duplication.
    const stripeGradients =
      styles.match(/--fa-stripes(?:-deep)?: repeating-linear-gradient\(/g) ??
      [];
    expect(stripeGradients).toHaveLength(2);
  });

  it("maps each named kit to its requested vertical stripe colours", () => {
    const third = styles.slice(styles.indexOf(":root {"));
    const away = styles.slice(styles.indexOf(':root[data-theme="away"] {'));
    const light = styles.slice(styles.indexOf(':root[data-theme="light"] {'));

    expect(third).toContain("--fa-stripe-a: #00a13e");
    expect(third).toContain("--fa-stripe-b: #2b2065");
    expect(away).toContain("--fa-stripe-a: #ffff00");
    expect(away).toContain("--fa-stripe-b: #0000ff");
    expect(light).toContain("--fa-stripe-a: #ffffff");
    expect(light).toContain("--fa-stripe-b: #e5da15");
  });

  it("gives the Away Kit yellow enough strength to remain yellow", () => {
    expect(styles).toContain("--fa-stripe-a-mix");
    expect(styles).toContain("--fa-stripe-b-mix");
    const away = styles.slice(styles.indexOf(':root[data-theme="away"] {'));
    expect(away).toContain("--fa-stripe-a-mix: 80%");
    expect(away).toContain("--fa-stripe-b-mix: 60%");
  });

  it("grounds exposed Away Kit copy without hiding the verticals", () => {
    const start = styles.indexOf(':root[data-theme="away"] .site-header');
    const block = styles.slice(start, styles.indexOf("}", start));
    expect(start).toBeGreaterThan(-1);
    expect(block).toContain(':root[data-theme="away"] main');
    expect(block).toContain(':root[data-theme="away"] .site-footer');
    expect(block).toContain("background: color-mix(");
    expect(block).toContain("var(--fa-surface-deep) 52%");
    expect(block).toContain("transparent");
  });

  it("keeps the deep variant, because the two surfaces differ", () => {
    expect(styles).toContain("--fa-stripes-deep");
    expect(styles).toContain("--fa-surface-deep");
  });
});

describe("Top Picks position colours", () => {
  it("uses four distinct Mode 7 accents in every kit", () => {
    const positions = {
      GKP: "magenta",
      DEF: "cyan",
      MID: "green",
      FWD: "yellow",
    } as const;

    for (const [position, colour] of Object.entries(positions)) {
      const selector = `.top-pick-column[data-position="${position}"]`;
      const start = styles.indexOf(`${selector} {`);
      const block = styles.slice(start, styles.indexOf("}", start));
      expect(start).toBeGreaterThan(-1);
      expect(block).toContain(`--top-pick-accent: ${TELETEXT_PALETTE[colour]}`);
      expect(block).toContain(
        `--top-pick-accent-ink: ${TELETEXT_PALETTE.black}`,
      );
    }

    expect(styles).not.toMatch(/:root\[data-theme="[^"]+"\] \.top-pick-column/);
  });

  it("preserves the authored xPts5 capitalization", () => {
    const selector = ".top-pick-runner-points";
    const start = styles.indexOf(`${selector} {`);
    const block = styles.slice(start, styles.indexOf("}", start));
    expect(start).toBeGreaterThan(-1);
    expect(block).toContain("text-transform: none");
  });
});

describe("animation hints", () => {
  it("promotes the one continuously animated element", () => {
    // One declaration per surface, checked here.
    const mark = styles.slice(styles.indexOf(".loading-mark {"));
    expect(mark).toContain("will-change: transform");
    expect(mark).toContain("contain: strict");
  });

  it("only promotes it where motion is allowed", () => {
    // A promoted layer for something that is not animating costs memory and
    // buys nothing.
    const reduced = styles.indexOf("@media (prefers-reduced-motion:");
    const loading = styles.indexOf(".loading-mark {");
    expect(reduced).toBeGreaterThan(-1);
    expect(loading).toBeGreaterThan(reduced);
  });

  it("does not promote the short one-shot transitions", () => {
    // 150ms and one-shot. A permanent layer for a hover is exactly the misuse
    // will-change warns about.
    const promoted = styles.match(/will-change:/g) ?? [];
    expect(promoted.length).toBeLessThanOrEqual(2);
  });
});

describe("chunk names", () => {
  it("the build refuses chunks named after nothing", () => {
    // Vite already names a lazy chunk after its module, so
    // this is true by default -- which is why it is worth guarding. A
    // manualChunks rule returning "vendor" is a one-line change that would
    // make every line of the size report meaningless.
    expect(budget).toContain("not named after anything");
    expect(budget).toMatch(/chunk\|vendor/);
    expect(budget).toContain("process.exit(1)");
  });
});

describe("structured data", () => {
  it("is valid JSON", () => {
    // A malformed block is silently ignored by every consumer, so a typo here
    // produces no error anywhere -- the feature simply does not exist.
    const match =
      /<script type="application\/ld\+json">([\s\S]*?)<\/script>/.exec(html);
    expect(match).not.toBeNull();
    expect(() => JSON.parse(match![1] as string)).not.toThrow();
  });

  it("describes the site and the application, and nothing else", () => {
    const match =
      /<script type="application\/ld\+json">([\s\S]*?)<\/script>/.exec(html);
    const data = JSON.parse(match![1] as string) as {
      "@graph": { "@type": string }[];
    };
    expect(data["@graph"].map((node) => node["@type"])).toEqual([
      "WebSite",
      "WebApplication",
    ]);
  });

  it("claims nothing it cannot support", () => {
    // Wrong structured data is worse than none, because it is trusted. No
    // ratings nobody collected, no reviews nobody wrote, no postal address.
    const match =
      /<script type="application\/ld\+json">([\s\S]*?)<\/script>/.exec(html);
    const raw = match![1] as string;
    for (const forbidden of [
      "aggregateRating",
      "Review",
      "ratingValue",
      "reviewCount",
      "address",
      "telephone",
    ]) {
      expect(raw).not.toContain(forbidden);
    }
  });

  it("omits breadcrumbs, and says why", () => {
    // This is a single-page app: the head is identical on every route, so a
    // breadcrumb here would tell a crawler that does not run JavaScript that
    // every URL is the home page.
    expect(html).not.toContain("BreadcrumbList");
    expect(html).toContain("single-page app");
  });

  it("says the application is free rather than leaving it ambiguous", () => {
    expect(html).toContain('"isAccessibleForFree": true');
  });
});
