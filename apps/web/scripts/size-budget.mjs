import { gzipSync } from "node:zlib";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

/**
 * Nothing stopped the shipped bundle growing.
 *
 * Budgets are on gzipped bytes, because that is what a user waits for. Each is
 * set with roughly 15% headroom over the size measured when this was written,
 * so an ordinary change passes and a dependency that doubles the bundle does
 * not. Raising one is a deliberate edit with a number attached, which is the
 * point: the entry chunk was 616 kB before code-splitting and nothing objected.
 *
 * The stylesheet went 15 -> 17 when the site gained an info-marker component,
 * an FAQ page and an index home page. It measured 15.00 against a 15 budget,
 * which is a guard that fires on the next line of CSS rather than on a problem.
 * It went 17 -> 19 for the same reason a second time, and 19 -> 22 a third.
 */

const DIST = join(import.meta.dirname, "..", "dist", "assets");

const BUDGETS = [
  // Measured 19.29 kB, raised from 19 kB. The top-picks cards gained their
  // responsive layout and the accessible rules that go with it, and the 19 kB
  // budget was again a guard with nothing left in it: 19.29 against 19. Set at
  // 22 so an ordinary rule passes and a stylesheet that grows by a page does
  // not.
  { match: /\.css$/, name: "stylesheet", gzipKb: 22 },
  // Measured 150.66 kB, raised from 150 kB. Publishing the first
  // bookmaker-implied goals distribution expanded the static season inputs
  // consumed by the entry chunk; untouched origin/main measured 150.65 kB.
  // Set at 174 to restore the documented roughly 15% headroom.
  { match: /^index-.*\.js$/, name: "entry chunk", gzipKb: 174 },
  // Measured 54.94 kB. The plan is now the only route a manager needs: the
  // snapshot, the record, the squad builder and the season all arrive here,
  // replacing a second route that had to be downloaded separately, and the
  // squad pool carries every player in the game rather than a top-forty cut.
  // Budgeted apart from the other lazy chunks so absorbing a page does not
  // quietly raise the ceiling for everything else.
  { match: /^SeasonPlanPage-.*\.js$/, name: "plan chunk", gzipKb: 58 },
  // Measured 58.93 kB, raised from 54 kB. The worker carries the solver-used
  // market-carry table so a player's quoted fixture view fades back toward
  // history instead of staying fixed all season. Unused row-level provenance
  // and squad numbers were trimmed first; compacting the remaining carry rows
  // recovered only 0.45 kB because every retained row moves a solver route.
  //
  // Measured 68.55 kB, raised from 68 kB at model 8.5. No code entered the
  // worker: anchoring each club's attacking routes to its team goal total
  // replaced a column of repeated de-vigged prices with fitted values that
  // share fewer digits, and the artifact gzips 1.33 kB worse for it. The
  // uncompressed bundle got smaller.
  {
    match: /^season-solver\.worker-.*\.js$/,
    name: "solver worker",
    gzipKb: 70,
  },
  // Measured 39.94 kB for the shared chunk, raised from 38 kB. Consolidating
  // the team view onto the plan moved several components into shared code
  // rather than a route of their own, and the browser pool grew from a
  // top-forty-per-position cut to every player the projector can rate.
  {
    match: /^(?!index-|SeasonPlanPage-|season-solver\.worker-).*\.js$/,
    name: "lazy chunk",
    gzipKb: 42,
  },
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
 * Chunk names must stay legible.
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
