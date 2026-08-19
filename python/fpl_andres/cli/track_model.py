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

from fpl_andres.backtesting.captain_significance import BASELINE_POLICY
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
        owned_captain_policies = {
            entry["label"]: {
                "meanChosenPoints": entry.get("meanChosenPoints"),
                "meanReachableCeiling": entry.get("meanReachableCeiling"),
                "ownedSquadRegret": entry.get("ownedSquadRegret"),
                "shareOfReachableCeiling": entry.get("shareOfReachableCeiling"),
            }
            for entry in season.get("ownedCaptainPolicies", [])
        }
        seasons.append(
            {
                "season": season.get("season"),
                "corpusFingerprint": season.get("corpusFingerprint"),
                "methods": methods,
                "ownedCaptainPolicies": owned_captain_policies,
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
    """The measured table and findings, all derived from the same artifact."""
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
    findings = _performance_findings(report)
    return "\n".join(rows) if not findings else f"{'\n'.join(rows)}\n\n{findings}"


def _performance_findings(report: dict[str, Any]) -> str:
    """Results prose that cannot drift away from the generated table."""
    seasons = [season for season in report.get("seasons", []) if isinstance(season, dict)]
    comparable: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]] = []
    for season in seasons:
        methods = {
            str(entry.get("label")): entry
            for entry in season.get("methods", [])
            if isinstance(entry, dict)
        }
        model = methods.get("model", {})
        form = methods.get("recent_mean", {})
        crowd = methods.get("ownership", {})
        if model and form:
            comparable.append((model, form, crowd, str(season.get("season", "unknown"))))

    paragraphs: list[str] = []
    if comparable:
        total = len(comparable)
        mae_wins = sum(
            1
            for model, form, _, _ in comparable
            if _less(model.get("meanAbsoluteError"), form.get("meanAbsoluteError"))
        )
        spearman_wins = sum(
            1
            for model, form, _, _ in comparable
            if _greater(model.get("spearman"), form.get("spearman"))
        )
        hit_wins = sum(
            1
            for model, form, _, _ in comparable
            if _greater(model.get("topNHitRate"), form.get("topNHitRate"))
        )
        crowd_wins = sum(
            1
            for model, _, crowd, _ in comparable
            if _greater(model.get("topNHitRate"), crowd.get("topNHitRate"))
        )
        paragraphs.append(
            f"Against recent form, the model wins MAE in {mae_wins}/{total} seasons, "
            f"Spearman in {spearman_wins}/{total}, and top-20 hit rate in "
            f"{hit_wins}/{total}; it beats ownership hit rate in {crowd_wins}/{total}."
        )

        biases = [
            float(model["bias"]) for model, _, _, _ in comparable if _is_number(model.get("bias"))
        ]
        if biases:
            negative = sum(value < 0 for value in biases)
            positive = sum(value > 0 for value in biases)
            paragraphs.append(
                f"Bias: {negative}/{len(biases)} negative, {positive}/{len(biases)} positive; "
                f"range {_signed(min(biases))} to {_signed(max(biases))}."
            )

        mae_rows = [
            (float(model["meanAbsoluteError"]), season)
            for model, _, _, season in comparable
            if _is_number(model.get("meanAbsoluteError"))
        ]
        spearman_rows = [
            (float(model["spearman"]), season)
            for model, _, _, season in comparable
            if _is_number(model.get("spearman"))
        ]
        if mae_rows and spearman_rows:
            highest_mae, highest_mae_season = max(mae_rows)
            lowest_spearman, lowest_spearman_season = min(spearman_rows)
            paragraphs.append(
                f"Highest MAE: {highest_mae_season} at {highest_mae:.3f}. "
                f"Lowest Spearman: {lowest_spearman_season} at {lowest_spearman:.3f}."
            )

    if seasons:
        latest = seasons[-1]
        methods = {
            str(entry.get("label")): entry
            for entry in latest.get("methods", [])
            if isinstance(entry, dict)
        }
        positions = methods.get("model", {}).get("byPosition", {})
        rated = (
            [
                (float(value), str(position))
                for position, value in positions.items()
                if _is_number(value)
            ]
            if isinstance(positions, dict)
            else []
        )
        if rated:
            value, position = min(rated)
            paragraphs.append(
                f"In {latest.get('season')}, the weakest position is {position} at "
                f"{value:.3f} Spearman."
            )

    return "\n\n".join(paragraphs)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _less(left: Any, right: Any) -> bool:
    return _is_number(left) and _is_number(right) and float(left) < float(right)


def _greater(left: Any, right: Any) -> bool:
    return _is_number(left) and _is_number(right) and float(left) > float(right)


def render_captaincy(report: dict[str, Any]) -> str:
    """Incumbent captain returns from legal model-owned XIs."""
    rows = [
        "| Season | Weeks | Chosen | Reachable XI | Owned regret | Nailed it | Blanked |",
        "| ------ | ----- | ------ | ------------ | ------------ | --------- | ------- |",
    ]
    scored = False
    for season in report.get("seasons", []):
        for entry in season.get("ownedCaptainPolicies", []):
            if entry.get("label") != "expected_points":
                continue
            scored = True
            rows.append(
                f"| {season.get('season')} | {entry.get('gameweeks')} | "
                f"{_cell(entry.get('meanChosenPoints'), 2)} | "
                f"{_cell(entry.get('meanReachableCeiling'), 2)} | "
                f"{_cell(entry.get('ownedSquadRegret'), 2)} | "
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
        entries = season.get("ownedCaptainPolicies", [])
        scored = [
            entry for entry in entries if isinstance(entry.get("meanChosenPoints"), (int, float))
        ]
        if not scored:
            continue
        best = max(float(entry["meanChosenPoints"]) for entry in scored)
        for entry in scored:
            label = str(entry.get("label"))
            totals.setdefault(label, []).append(float(entry["meanChosenPoints"]))
            wins.setdefault(label, 0)
            if float(entry["meanChosenPoints"]) == best:
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
            f"{wins.get(label, 0)} | {_verdict(label, verdicts.get(label))} |"
        )
    return "\n".join(rows)


def _verdict(label: str, entry: dict[str, Any] | None) -> str:
    """One cell: the gap, its interval, and whether it clears zero.

    An artifact predating the bootstrap has no entry for any thesis, and that
    reads as "not measured" rather than as a tie. Only the incumbent is exempt:
    it has no gap against itself.
    """
    if label == BASELINE_POLICY:
        return "baseline"
    if entry is None:
        return "not measured"
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
