"""Report what the elite cohort captained, and whether it is worth studying.

The question this answers is not "which thesis is best" -- `validate` answers
that against four seasons of realised points. It is the prior question: does the
cohort's armband contain any information at all, or is it unanimous every week?

If the top-500 captain the same player in nine weeks out of ten, then studying
them teaches nothing a projection does not already say, and the honest output of
this command is a small number of contested weeks rather than a league table.
That is why `contestedWeeks` is printed first.

Runs over whatever `capture_cohort_picks` has written so far. With no captures
it says so and exits zero: an empty series is a fact about the season, not a
failure of the job.

Usage:
    python -m fpl_andres.cli.cohort_captains
    python -m fpl_andres.cli.cohort_captains --picks picks.json
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fpl_andres.cohorts.captain_agreement import (
    SPLIT_THRESHOLD,
    CohortWeek,
    score_agreement,
)
from fpl_andres.jsonio import read_json_file

__all__ = ["build_parser", "load_weeks", "main"]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CAPTURES = REPO_ROOT / "data" / "cohort" / "portfolio"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, default=DEFAULT_CAPTURES)
    parser.add_argument(
        "--picks",
        type=Path,
        default=None,
        help=(
            "JSON mapping a policy label to {gameweek: elementId}. Without it "
            "the command reports the cohort alone."
        ),
    )
    return parser


def load_weeks(directory: Path) -> list[CohortWeek]:
    """Read every captured gameweek, newest last.

    A capture with no holdings is kept rather than dropped: a week the job ran
    and found nothing is different from a week it never ran, and only the first
    of those should look like a gap in the series.
    """
    if not directory.exists():
        return []
    weeks: list[CohortWeek] = []
    for path in sorted(directory.glob("gw*.json")):
        # `annotate_portfolio` writes `gwNN-points.json` in the same directory.
        # It repeats the event number and carries no holdings, so reading it as
        # a capture files a second, empty week against a gameweek that was
        # captured properly and doubles the series.
        if not path.stem.removeprefix("gw").isdigit():
            continue
        payload: dict[str, Any] = read_json_file(path)
        shares = {
            int(holding["elementId"]): float(holding["captainedShare"])
            for holding in payload.get("holdings", [])
            if float(holding.get("captainedShare", 0.0)) > 0.0
        }
        weeks.append(
            CohortWeek(
                event=int(payload["event"]),
                counted=int(payload.get("counted", 0)),
                share_by_element=shares,
            )
        )
    return sorted(weeks, key=lambda week: week.event)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    weeks = load_weeks(args.captures)
    if not weeks:
        print(
            f"No cohort captures in {args.captures}. Run capture_cohort_picks "
            f"each gameweek first; this command reads what it wrote.",
            file=sys.stderr,
        )
        return 0

    contested = [week for week in weeks if week.is_split]
    print(f"captured weeks: {len(weeks)}")
    print(f"contested weeks (top pick at or below {SPLIT_THRESHOLD:.0%}): {len(contested)}")
    for week in weeks:
        modal = week.modal_captain
        named = "tied" if modal is None else f"element {modal}"
        print(f"  gw{week.event:02d}  {week.unanimity:6.1%} on {named}  n={week.counted}")

    if args.picks is None:
        return 0

    picks_payload: dict[str, dict[str, int]] = read_json_file(args.picks)
    picks = {
        label: {int(event): int(element) for event, element in by_event.items()}
        for label, by_event in picks_payload.items()
    }
    print("\nagreement (a description of the cohort, not a score):")
    for entry in score_agreement(picks, weeks):
        split = "n/a" if entry.split_modal_rate is None else f"{entry.split_modal_rate:.0%}"
        print(
            f"  {entry.label:<24} {entry.modal_rate:>5.0%} of {entry.weeks:>2} weeks, "
            f"{split:>4} of {entry.split_weeks:>2} contested, mean share {entry.mean_share:.0%}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
