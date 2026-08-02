"""A mutation-testing trial for the rules and scoring modules.

Audit item #166 asked whether the suite actually catches regressions, or merely
executes the lines that coverage reports.

Deliberately not `mutmut` or `cosmic-ray`. Both are good tools and both are a
dependency, a config file and a cache directory to maintain, for a question that
is asked once. This applies a small set of classic mutation operators to two
named modules, runs the tests, and reports the kill rate.

A surviving mutant is a change to the code that no test objects to. That is
either a gap in the suite or a line that does not matter, and both are worth
knowing about.

    python scripts/mutation_trial.py
    python scripts/mutation_trial.py --module fpl_andres/rules.py
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The two modules #166 names. Rules decide what is legal; scoring decides what
# won. A regression in either is a wrong answer rather than a crash, which is
# exactly the kind a passing suite can hide.
TARGETS = ("python/fpl_andres/rules.py", "python/fpl_andres/backtesting/score.py")

# Applied in order; the first match in a line is mutated and the rest left alone.
OPERATORS: tuple[tuple[str, str], ...] = (
    (r"(?<![<>=!])>=(?!=)", ">"),
    (r"(?<![<>=!])<=(?!=)", "<"),
    (r"(?<![<>=!])>(?![=>])", ">="),
    (r"(?<![<>=!])<(?![=<])", "<="),
    (r"(?<![<>=!])==(?!=)", "!="),
    (r"(?<![<>=!])!=(?!=)", "=="),
    (r"\band\b", "or"),
    (r"\bor\b", "and"),
    (r"\bTrue\b", "False"),
    (r"\bFalse\b", "True"),
)


@dataclass
class Mutant:
    path: Path
    line_number: int
    before: str
    after: str


def _mutants(path: Path) -> list[Mutant]:
    found: list[Mutant] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        # Comments and docstring bodies are not behaviour.
        if not stripped or stripped.startswith("#") or stripped.startswith('"'):
            continue
        for pattern, replacement in OPERATORS:
            mutated, count = re.subn(pattern, replacement, line, count=1)
            if count:
                found.append(Mutant(path, number, line, mutated))
                break
    return found


def _run_tests(paths: list[str]) -> bool:
    """True when the suite still passes, which means the mutant survived."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mutation-trial")
    parser.add_argument("--module", action="append", default=None)
    parser.add_argument("--tests", default="python/tests")
    parser.add_argument("--limit", type=int, default=0, help="0 means every mutant")
    args = parser.parse_args(argv)

    targets = [ROOT / target for target in (args.module or TARGETS)]
    survivors: list[Mutant] = []
    killed = 0

    for target in targets:
        original = target.read_text(encoding="utf-8")
        mutants = _mutants(target)
        if args.limit:
            mutants = mutants[: args.limit]
        print(f"{target.relative_to(ROOT)}: {len(mutants)} mutants")

        for index, mutant in enumerate(mutants, start=1):
            lines = original.splitlines(keepends=True)
            ending = "\n" if lines[mutant.line_number - 1].endswith("\n") else ""
            lines[mutant.line_number - 1] = mutant.after + ending
            target.write_text("".join(lines), encoding="utf-8")
            try:
                survived = _run_tests([args.tests])
            finally:
                target.write_text(original, encoding="utf-8")

            if survived:
                survivors.append(mutant)
                print(f"  [{index}/{len(mutants)}] SURVIVED line {mutant.line_number}")
            else:
                killed += 1
                print(f"  [{index}/{len(mutants)}] killed   line {mutant.line_number}")

    total = killed + len(survivors)
    if total == 0:
        print("no mutants generated")
        return 0

    print(f"\nkill rate: {killed}/{total} ({killed / total:.0%})")
    if survivors:
        print("\nsurvivors -- a change here breaks nothing:")
        for mutant in survivors:
            location = f"{mutant.path.relative_to(ROOT)}:{mutant.line_number}"
            print(f"  {location}\n    - {mutant.before.strip()}\n    + {mutant.after.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
