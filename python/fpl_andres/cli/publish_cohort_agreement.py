"""Publish a summary of what the FPL500 cohort captained each gameweek.

Reads all captured portfolio files and writes a single JSON that the
`score-cohort-agreement` workflow commits after each gameweek capture. This is
the agreement series: who the cohort captained, week by week, and whether each
week was contested enough to carry any information.

The output is intentionally a description, not a verdict. The module-level
comment in `cohorts/captain_agreement.py` explains why: the cohort is selected
on outcome, so measuring the outcome is the trap.  This file is the
measurement. What it means is a separate question.

Usage:
    python -m fpl_andres.cli.publish_cohort_agreement
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_andres.cohorts.captain_agreement import (
    SPLIT_THRESHOLD,
    CohortWeek,
    score_agreement,
    weight_agreement_signal,
)
from fpl_andres.cli.cohort_captains import load_weeks
from fpl_andres.jsonio import read_json_file

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PORTFOLIO_DIR = REPO_ROOT / "data" / "cohort" / "portfolio"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "cohort" / "agreement.json"

SCHEMA_VERSION = 1
# Maximum top captains per week to include in the file. Keeps the file compact;
# the rest are noise.
TOP_CAPTAINS = 5
# Minimum captain share to include in the per-week list. Shares below this are
# fractional noise rather than meaningful choices.
MINIMUM_SHARE = 0.01


def _week_payload(week: CohortWeek) -> dict[str, Any]:
    top = sorted(week.share_by_element.items(), key=lambda row: -row[1])[:TOP_CAPTAINS]
    return {
        "event": week.event,
        "counted": week.counted,
        "modalCaptain": week.modal_captain,
        "unanimity": round(week.unanimity, 5),
        "isSplit": week.is_split,
        "topCaptains": [
            {"elementId": element_id, "share": round(share, 5)}
            for element_id, share in top
            if share >= MINIMUM_SHARE
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-cohort-agreement")
    parser.add_argument("--portfolio-dir", type=Path, default=DEFAULT_PORTFOLIO_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--picks",
        type=Path,
        default=None,
        help=(
            "JSON mapping a policy label to {gameweek: elementId}. "
            "When provided, scored and weighted policy agreement signals are "
            "included in the output under 'signals'."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    weeks = load_weeks(args.portfolio_dir)
    if not weeks:
        print(
            f"No cohort captures in {args.portfolio_dir}. Nothing to publish.",
            file=sys.stderr,
        )
        return 0

    picks: dict[str, dict[int, int]] = {}
    if args.picks is not None:
        raw_picks: dict[str, dict[str, int]] = read_json_file(args.picks)
        picks = {
            label: {int(event): int(element) for event, element in by_event.items()}
            for label, by_event in raw_picks.items()
        }

    signals = weight_agreement_signal(score_agreement(picks, weeks))

    contested = [week for week in weeks if week.is_split]
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "splitThreshold": SPLIT_THRESHOLD,
        "capturedWeeks": len(weeks),
        "contestedWeeks": len(contested),
        "weeks": [_week_payload(week) for week in weeks],
        "signals": [
            {
                "label": s.label,
                "splitWeeks": s.split_weeks,
                "weight": round(s.weight, 5),
                "splitModalRate": round(s.split_modal_rate, 5) if s.split_modal_rate is not None else None,
                "meanShare": round(s.mean_share, 5),
                "weightedRate": round(s.weighted_rate, 5) if s.weighted_rate is not None else None,
            }
            for s in signals
        ],
    }

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {output} — {len(weeks)} weeks, {len(contested)} contested "
        f"(split threshold {SPLIT_THRESHOLD:.0%})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
