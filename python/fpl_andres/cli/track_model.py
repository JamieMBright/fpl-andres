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

__all__ = [
    "build_parser",
    "main",
    "merge_history",
    "render_captaincy",
    "render_performance",
    "replace_between",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VALIDATION = REPO_ROOT / "apps" / "web" / "src" / "data" / "validation.json"
DEFAULT_HISTORY = REPO_ROOT / "apps" / "web" / "src" / "data" / "model-history.json"
DEFAULT_CARD = REPO_ROOT / "docs" / "MODEL_CARDS.md"

# The card quoted the numbers by hand, so the first automated refresh moved the
# artifact and left the document behind -- which is the exact drift the guard in
# `test_measured_performance.py` exists to catch, arriving by a new route.
PERFORMANCE_MARKERS = (
    "<!-- measured-performance:start -->",
    "<!-- measured-performance:end -->",
)
CAPTAINCY_MARKERS = ("<!-- captaincy:start -->", "<!-- captaincy:end -->")
POLICY_MARKERS = ("<!-- captain-policies:start -->", "<!-- captain-policies:end -->")

#: U+2212, because a hyphen in front of a number is not a minus sign.
MINUS = "\u2212"

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
    parser.add_argument("--card", type=Path, default=DEFAULT_CARD)
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


def _signed(value: float, digits: int = 3) -> str:
    text = f"{abs(value):.{digits}f}"
    return f"{MINUS}{text}" if value < 0 else f"+{text}"


def _cell(value: Any, digits: int = 3) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    text = f"{abs(float(value)):.{digits}f}"
    return f"{MINUS}{text}" if float(value) < 0 else text


def render_performance(report: dict[str, Any]) -> str:
    """The measured-performance table, in the column order the guard parses."""
    rows = [
        "| Season  | MAE   | vs form | Spearman | vs form | Top-20 hit | form  | crowd | Bias   |",
        "| ------- | ----- | ------- | -------- | ------- | ---------- | ----- | ----- | ------ |",
    ]
    for season in report.get("seasons", []):
        methods = {entry["label"]: entry for entry in season.get("methods", [])}
        model = methods.get("model", {})
        form = methods.get("recent_mean", {})
        crowd = methods.get("ownership", {})
        mae, form_mae = model.get("meanAbsoluteError"), form.get("meanAbsoluteError")
        error_gap = (
            f"{MINUS}{abs((mae - form_mae) / form_mae) * 100:.1f}%"
            if isinstance(mae, (int, float))
            and isinstance(form_mae, (int, float))
            and form_mae
            and mae < form_mae
            else "—"
        )
        rho, form_rho = model.get("spearman"), form.get("spearman")
        rho_gap = (
            _signed(rho - form_rho)
            if isinstance(rho, (int, float)) and isinstance(form_rho, (int, float))
            else "—"
        )
        rows.append(
            f"| {season.get('season')} | {_cell(mae)} | {error_gap} | {_cell(rho)} | "
            f"{rho_gap} | {_cell(model.get('topNHitRate'))} | {_cell(form.get('topNHitRate'))} | "
            f"{_cell(crowd.get('topNHitRate'))} | {_cell(model.get('bias'))} |"
        )
    return "\n".join(rows)


def render_captaincy(report: dict[str, Any]) -> str:
    """Captain returns per season and method, or a line saying it was not scored."""
    rows = [
        "| Season | Method | Weeks | Captain | Best available | Left behind | Nailed it |"
        " Blanked |",
        "| ------ | ------ | ----- | ------- | -------------- | ----------- | --------- |"
        " ------- |",
    ]
    scored = False
    for season in report.get("seasons", []):
        for entry in season.get("captaincy", []):
            scored = True
            rows.append(
                f"| {season.get('season')} | `{entry.get('label')}` | "
                f"{entry.get('gameweeks')} | {_cell(entry.get('meanPoints'), 2)} | "
                f"{_cell(entry.get('meanBestPoints'), 2)} | {_cell(entry.get('regret'), 2)} | "
                f"{entry.get('perfectWeeks')} | {_cell(entry.get('blankRate'), 2)} |"
            )
    if not scored:
        return "Not yet measured."
    return "\n".join(rows)


def render_policies(report: dict[str, Any]) -> str:
    """Every captaincy thesis, averaged over the seasons it was scored on.

    Per-season rows would be nine policies times four seasons and nobody would
    read them; the artifact keeps those. What the card needs is the season count
    a policy won, because a thesis that wins once and loses three times is a
    thesis that got lucky.
    """
    totals: dict[str, list[float]] = {}
    wins: dict[str, int] = {}
    for season in report.get("seasons", []):
        entries = season.get("captainPolicies", [])
        scored = [entry for entry in entries if isinstance(entry.get("meanPoints"), (int, float))]
        if not scored:
            continue
        best = max(float(entry["meanPoints"]) for entry in scored)
        for entry in scored:
            label = str(entry.get("label"))
            totals.setdefault(label, []).append(float(entry["meanPoints"]))
            wins.setdefault(label, 0)
            if float(entry["meanPoints"]) == best:
                wins[label] += 1
    if not totals:
        return "Not yet measured."

    # The paired bootstrap, keyed by thesis, so the table can say which of the
    # leads above survive an interval. A mean and a season count still let a
    # reader crown the top row; the verdict column is what refuses.
    verdicts = {str(entry.get("label")): entry for entry in report.get("captainSignificance", [])}

    seasons = max(len(values) for values in totals.values())
    rows = [
        f"| Thesis | Mean captain points | Seasons won (of {seasons}) | vs projection (95% CI) |",
        "| ------ | ------------------- | -------------------------- | ---------------------- |",
    ]
    for label in sorted(totals, key=lambda key: -sum(totals[key]) / len(totals[key])):
        values = totals[label]
        rows.append(
            f"| `{label}` | {sum(values) / len(values):.2f} | "
            f"{wins.get(label, 0)} | {_verdict(verdicts.get(label))} |"
        )
    return "\n".join(rows)


def _verdict(entry: dict[str, Any] | None) -> str:
    """One cell: the gap, its interval, and whether it clears zero."""
    if entry is None:
        return "baseline"
    lower = entry.get("lower")
    upper = entry.get("upper")
    improvement = entry.get("improvement")
    if not isinstance(lower, (int, float)):
        return "not measured"
    if not isinstance(upper, (int, float)):
        return "not measured"
    if not isinstance(improvement, (int, float)):
        return "not measured"
    mark = " **yes**" if entry.get("better") else ""
    return f"{float(improvement):+.2f} [{float(lower):+.2f}, {float(upper):+.2f}]{mark}"


def replace_between(text: str, markers: tuple[str, str], body: str) -> str:
    start, end = markers
    if start not in text or end not in text:
        raise ValueError(f"{start} and {end} must both appear in the document")
    head, _, rest = text.partition(start)
    _, _, tail = rest.partition(end)
    return f"{head}{start}\n\n{body}\n\n{end}{tail}"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    report = read_json_file(args.validation)
    existing: list[dict[str, Any]] = read_json_file(args.history) if args.history.exists() else []

    try:
        history, changed = merge_history(existing, _row(report, args.code_revision))
    except ValueError as error:
        print(f"model history: {error}", file=sys.stderr)
        return 1

    card = args.card.read_text(encoding="utf-8")
    card = replace_between(card, PERFORMANCE_MARKERS, render_performance(report))
    card = replace_between(card, CAPTAINCY_MARKERS, render_captaincy(report))
    card = replace_between(card, POLICY_MARKERS, render_policies(report))
    args.card.write_text(card, encoding="utf-8")
    print(f"model card: tables rewritten in {args.card}.")

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
