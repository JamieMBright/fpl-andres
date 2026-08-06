"""Say what moved between two backtest runs, as a markdown table.

The refresh runs in CI, so nobody watches it. A workflow that quietly rewrites
the published numbers and says "done" is how a regression ships: the diff is
four thousand lines of JSON and the one line that matters is a fourth decimal
place.

This prints the headline metrics before and after, per season and per method,
with the direction of travel marked. It is written to the job summary, so the
run itself is the record of what changed.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fpl_andres.jsonio import read_json_file

__all__ = ["build_parser", "compare", "main"]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AFTER = REPO_ROOT / "apps" / "web" / "src" / "data" / "validation.json"

#: Lower is better for the first two, higher for the rest.
METRICS: tuple[tuple[str, bool], ...] = (
    ("meanAbsoluteError", False),
    ("bias", False),
    ("spearman", True),
    ("topNHitRate", True),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, default=DEFAULT_AFTER)
    return parser


def _methods(report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for season in report.get("seasons", []):
        for method in season.get("methods", []):
            out[(str(season.get("season")), str(method.get("label")))] = method
    return out


def _arrow(delta: float, higher_is_better: bool) -> str:
    if abs(delta) < 5e-4:
        return "="
    improved = delta > 0 if higher_is_better else delta < 0
    return "better" if improved else "WORSE"


def compare(before: dict[str, Any], after: dict[str, Any]) -> str:
    """A markdown report of the change, or a line saying there was none."""
    lines = [
        "## Backtest refresh",
        "",
        f"Model `{after.get('modelVersion', 'unversioned')}`, "
        f"previously `{before.get('modelVersion', 'unversioned')}`.",
        "",
    ]

    old = _methods(before)
    new = _methods(after)
    rows: list[str] = []
    for key in sorted(new):
        season, label = key
        previous = old.get(key)
        current = new[key]
        for metric, higher_is_better in METRICS:
            now = current.get(metric)
            was = None if previous is None else previous.get(metric)
            if not isinstance(now, (int, float)):
                continue
            if not isinstance(was, (int, float)):
                rows.append(f"| {season} | {label} | {metric} | — | {now:.3f} | new |")
                continue
            delta = float(now) - float(was)
            if abs(delta) < 5e-4:
                continue
            rows.append(
                f"| {season} | {label} | {metric} | {was:.3f} | {now:.3f} | "
                f"{delta:+.3f} {_arrow(delta, higher_is_better)} |"
            )

    if not rows:
        lines.append("No headline metric moved.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Season | Method | Metric | Before | After | Change |",
            "| --- | --- | --- | --- | --- | --- |",
            *rows,
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    before = read_json_file(args.before)
    after = read_json_file(args.after)
    print(compare(before, after))
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
