import { gzipSync } from "node:zlib";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

/**
 * Audit item #122. Nothing stopped the shipped bundle growing.
 *
 * Budgets are on gzipped bytes, because that is what a user waits for. Each is
 * set with roughly 15% headroom over the size measured when this was written,
 * so an ordinary change passes and a dependency that doubles the bundle does
 * not. Raising one is a deliberate edit with a number attached, which is the
 * point: the entry chunk was 616 kB before code-splitting and nothing objected.
 */

const DIST = join(import.meta.dirname, "..", "dist", "assets");

const BUDGETS = [
  // Measured 6.47 kB. The whole design system ships on first paint by design:
  // it is one stylesheet and splitting it would cost a round trip to save 6 kB.
  { match: /\.css$/, name: "stylesheet", gzipKb: 8 },
  // Measured 129.20 kB. Router, zod, lucide and the shell.
  { match: /^index-.*\.js$/, name: "entry chunk", gzipKb: 150 },
  // Measured 19.51 kB, the largest lazy chunk.
  { match: /^(?!index-).*\.js$/, name: "lazy chunk", gzipKb: 32 },
];

const files = readdirSync(DIST);
const failures = [];
const report = [];

for (const budget of BUDGETS) {
  const matching = files.filter((file) => budget.match.test(file));
  for (const file of matching) {
    const gzipKb = gzipSync(readFileSync(join(DIST, file))).length / 1024;
    report.push(
      `  ${file.padEnd(38)} ${gzipKb.toFixed(2).padStart(7)} kB gzip  (budget ${budget.gzipKb} kB)`,
    );
    if (gzipKb > budget.gzipKb) {
      failures.push(
        `${budget.name} ${file} is ${gzipKb.toFixed(2)} kB gzipped, over its ${budget.gzipKb} kB budget`,
      );
    }
  }
}

console.log("Bundle sizes:");
console.log(report.sort().join("\n"));

if (failures.length > 0) {
  console.error("\nSize budget exceeded:");
  for (const failure of failures) console.error(`  ${failure}`);
  console.error(
    "\nEither reduce the bundle or raise the budget in scripts/size-budget.mjs,\n" +
      "with the new measurement in the commit message.",
  );
  process.exit(1);
}

console.log("\nAll bundles within budget.");
