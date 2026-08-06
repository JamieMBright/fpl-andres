"""Append one backtest run to the model's own history.

`validation.json` is a snapshot: it says how the model scores now and forgets
how it scored before. That is the wrong shape for the only question that matters
after the first release — is this getting better?

So every run appends a row here. One row per (model version, corpus
fingerprint) pair, because re-running the same model over the same corpus
produces the same numbers and a second row would be a duplicate dressed as
progress. A run whose numbers moved without the version moving is a corpus
change, and the fingerprint says which.

The file is committed. It is a few kilobytes a year and it is the only record
that survives a regenerated artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fpl_andres.jsonio import read_json_file

__all__ = ["build_parser", "main", "merge_history"]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VALIDATION = REPO_ROOT / "apps" / "web" / "src" / "data" / "validation.json"
DEFAULT_HISTORY = REPO_ROOT / "apps" / "web" / "src" / "data" / "model-history.json"

#: Enough to compare two runs, and nothing a reader would have to scroll past.
CARRIED_METRICS = (
    "meanAbsoluteError",
    "spearman",
    "topNHitRate",
    "bias",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument(
        "--code-revision",
        default="",
        help="Commit the run was produced from. Recorded, never trusted.",
    )
    return parser


def _row(report: dict[str, Any], code_revision: str) -> dict[str, Any]:
    seasons = []
    for season in report.get("seasons", []):
        methods = {
            method["label"]: {key: method.get(key) for key in CARRIED_METRICS}
            for method in season.get("methods", [])
        }
        captaincy = {
            entry["label"]: {
                "meanPoints": entry.get("meanPoints"),
                "regret": entry.get("regret"),
                "shareOfCeiling": entry.get("shareOfCeiling"),
            }
            for entry in season.get("captaincy", [])
        }
        seasons.append(
            {
                "season": season.get("season"),
                "corpusFingerprint": season.get("corpusFingerprint"),
                "methods": methods,
                "captaincy": captaincy,
            }
        )
    return {
        "modelVersion": report.get("modelVersion"),
        "generatedAt": report.get("generatedAt"),
        "codeRevision": code_revision,
        "seasons": seasons,
    }


def merge_history(
    existing: list[dict[str, Any]], row: dict[str, Any]
) -> tuple[list[dict[str, Any]], bool]:
    """Add the row unless the same model has already been scored on the same corpus.

    Returns the history and whether it changed, so a caller can skip writing a
    file that would only differ by its timestamp.
    """
    if row.get("modelVersion") is None:
        raise ValueError("the run carries no modelVersion, so it cannot be tracked")

    def key(entry: dict[str, Any]) -> tuple[Any, ...]:
        return (
            entry.get("modelVersion"),
            tuple(
                (season.get("season"), season.get("corpusFingerprint"))
                for season in entry.get("seasons", [])
            ),
        )

    if any(key(entry) == key(row) for entry in existing):
        return existing, False
    return [*existing, row], True


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    report = read_json_file(args.validation)
    existing: list[dict[str, Any]] = read_json_file(args.history) if args.history.exists() else []

    try:
        history, changed = merge_history(existing, _row(report, args.code_revision))
    except ValueError as error:
        print(f"model history: {error}", file=sys.stderr)
        return 1

    if not changed:
        print("model history: this model has already been scored on this corpus.")
        return 0

    args.history.parent.mkdir(parents=True, exist_ok=True)
    args.history.write_text(
        json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"model history: {len(history)} runs recorded in {args.history}.")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
