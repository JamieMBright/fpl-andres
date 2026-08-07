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
  // Measured 14.04 kB, raised from 14 kB. Six new surfaces landed at once: the
  // season fixture strip, the method-step bar charts, the peer chart in the
  // card, the squad market and pitch, and the record chart with its key. Dead
  // rules from the squad builder's old dropdown form were removed first, which
  // gained 0.03 kB, so what remains is new UI rather than accumulated slack.
  { match: /\.css$/, name: "stylesheet", gzipKb: 15 },
  // Measured 128.26 kB. Router, zod, lucide and the shell.
  { match: /^index-.*\.js$/, name: "entry chunk", gzipKb: 150 },
  // Measured 33.64 kB for squad-projection, raised from 32 kB: every player now
  // carries his eight route components, his ceiling and the multiple it came
  // from. That is the artifact the whole plan is argued from, so it is bytes
  // spent on evidence rather than on decoration.
  { match: /^(?!index-).*\.js$/, name: "lazy chunk", gzipKb: 36 },
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

/*
 * Audit item #125: chunk names must stay legible.
 *
 * Vite already names a lazy chunk after the module that produced it, so the
 * report above reads "CalibrationPage-DzpDSLNJ.js" rather than "chunk-4a1f.js".
 * That is the whole of what the item asked for, and it is true by default --
 * which is exactly why it is worth guarding. Adding a `manualChunks` function
 * that returns "vendor" or an index is a one-line change that would make every
 * line of this report meaningless, and nothing else would complain.
 */
const anonymous = files.filter(
  (file) =>
    file.endsWith(".js") && /^(chunk|vendor)-[A-Za-z0-9_-]+\.js$/.test(file),
);
if (anonymous.length > 0) {
  console.error(
    "\nThese chunks are not named after anything:\n" +
      anonymous.map((file) => `  ${file}`).join("\n") +
      "\n\nA bundle report of hashes cannot be read. Name the chunk after its\n" +
      "entry module, or remove the manualChunks rule that produced this.",
  );
  process.exit(1);
}

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
