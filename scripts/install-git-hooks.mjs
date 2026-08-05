#!/usr/bin/env node
// A formatting failure in CI is the cheapest possible red build, so the hook
// that prevents it is installed by `pnpm install` rather than by remembering.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const HOOKS_PATH = ".githooks";

function git(args) {
  return execFileSync("git", args, { encoding: "utf8" }).trim();
}

try {
  git(["rev-parse", "--git-dir"]);
} catch {
  process.exit(0);
}

let current = "";
try {
  current = git(["config", "--get", "core.hooksPath"]);
} catch {
  current = "";
}

// Another tool owns the hook path (agents and some editors set their own).
// Overwriting it would silently disable them, so leave it alone and say so.
if (current && current !== HOOKS_PATH) {
  console.log(
    `core.hooksPath is set to ${current}; leaving it. Run "corepack pnpm format" before committing.`,
  );
  process.exit(0);
}

if (current !== HOOKS_PATH) {
  // `pre-commit install` writes .git/hooks/pre-commit and already runs
  // prettier; redirecting the hook path would silently disable it.
  let gitDir = "";
  try {
    gitDir = git(["rev-parse", "--git-common-dir"]);
  } catch {
    gitDir = ".git";
  }
  if (existsSync(join(gitDir, "hooks", "pre-commit"))) {
    console.log(
      'A pre-commit hook is already installed; leaving hooks alone. It must format staged files, or run "corepack pnpm format" before committing.',
    );
    process.exit(0);
  }
  git(["config", "core.hooksPath", HOOKS_PATH]);
}
