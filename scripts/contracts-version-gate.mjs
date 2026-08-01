#!/usr/bin/env node
/**
 * Audit item #142: a schema change must come with a version bump.
 *
 * `@fpl-andres/contracts` is the shared boundary. The Python models, the web
 * app and the serverless handlers all agree through it, and the generated
 * schema is checked into the repository so a change is visible in review.
 *
 * What was not visible was whether the change was breaking. A pull request
 * could alter the schema and leave the version alone, and nothing recorded that
 * the boundary had moved -- so nothing downstream could say "I need at least
 * this version", and a stale copy would fail later, somewhere else, in a way
 * that looks like a bug in the consumer.
 *
 * The rule: if `generated/contracts.schema.json` differs from the base branch,
 * `packages/contracts/package.json` must declare a different version. What the
 * new version should be is a judgement about whether the change breaks
 * anything, and that is not a judgement a script can make. It only insists that
 * the judgement was made.
 *
 * Runs in CI against the merge base. Outside CI it compares against `main`, or
 * says why it cannot and exits zero -- a developer without the base branch
 * fetched should not be blocked by a gate meant for review.
 */

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const SCHEMA_PATH = "packages/contracts/generated/contracts.schema.json";
const MANIFEST_PATH = "packages/contracts/package.json";

function git(...args) {
  return execFileSync("git", args, { encoding: "utf8" }).trim();
}

function tryGit(...args) {
  try {
    return git(...args);
  } catch {
    return null;
  }
}

function baseRef() {
  const explicit = process.env.GITHUB_BASE_REF;
  if (explicit) {
    const remote = `origin/${explicit}`;
    if (tryGit("rev-parse", "--verify", remote) !== null) return remote;
  }
  for (const candidate of ["origin/main", "main"]) {
    if (tryGit("rev-parse", "--verify", candidate) !== null) return candidate;
  }
  return null;
}

const base = baseRef();
if (base === null) {
  console.log(
    "contracts version gate: no base branch to compare against, skipping.",
  );
  process.exit(0);
}

const mergeBase = tryGit("merge-base", base, "HEAD") ?? base;
const schemaBefore = tryGit("show", `${mergeBase}:${SCHEMA_PATH}`);
const schemaNow = readFileSync(SCHEMA_PATH, "utf8");

if (schemaBefore !== null && schemaBefore.trim() === schemaNow.trim()) {
  console.log("contracts version gate: schema unchanged.");
  process.exit(0);
}

const manifestBefore = tryGit("show", `${mergeBase}:${MANIFEST_PATH}`);
const versionNow = JSON.parse(readFileSync(MANIFEST_PATH, "utf8")).version;
const versionBefore =
  manifestBefore === null ? null : JSON.parse(manifestBefore).version;

if (versionBefore !== null && versionBefore === versionNow) {
  console.error(
    [
      `${SCHEMA_PATH} changed but @fpl-andres/contracts is still ${versionNow}.`,
      "",
      "The shared boundary moved. Decide whether the change is breaking and",
      `bump "version" in ${MANIFEST_PATH} to say so. A consumer cannot ask for`,
      "a version that was never issued.",
    ].join("\n"),
  );
  process.exit(1);
}

console.log(
  `contracts version gate: schema changed and version moved ${String(versionBefore)} -> ${versionNow}.`,
);
