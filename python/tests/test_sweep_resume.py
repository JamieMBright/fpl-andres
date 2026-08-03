"""The sweep can be run repeatedly without being told where it got to.

Ten million more managers register before a season starts, so the catalogue is
never finished — it is a thing you re-run. That needs three properties: it
resumes from the checkpoint, it stops on its own when it walks off the end of
the register, and a scheduled run can be given a time budget instead of being
left to discover that a six-hour job takes sixteen.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fpl_andres.cli import sweep_managers
from fpl_andres.cli.sweep_managers import (
    EMPTY_BLOCKS_TO_STOP,
    Progress,
    _load_progress,
    build_parser,
)


def test_resume_reads_the_checkpoint_rather_than_the_start_flag(tmp_path: Path) -> None:
    checkpoint = tmp_path / "sweep-checkpoint.json"
    checkpoint.write_text(
        json.dumps({"next_id": 2_500_001, "with_history": 12, "qualifying": 3}),
        encoding="utf-8",
    )

    with patch.object(sweep_managers, "CHECKPOINT", checkpoint):
        resumed = _load_progress(start=1, resume=True)

    assert resumed.next_id == 2_500_001, "a resume that restarts at 1 re-sweeps for days"
    assert resumed.qualifying == 3


def test_a_checkpoint_written_before_the_end_marker_still_loads(tmp_path: Path) -> None:
    """The committed checkpoint predates `reached_end_at`; it must not crash."""
    checkpoint = tmp_path / "sweep-checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "next_id": 2_500_001,
                "with_history": 2_178_517,
                "qualifying": 2_207,
                "missing": 13_323,
                "errors": 85,
            }
        ),
        encoding="utf-8",
    )

    with patch.object(sweep_managers, "CHECKPOINT", checkpoint):
        resumed = _load_progress(start=1, resume=True)

    assert resumed.reached_end_at is None


def test_without_resume_the_start_flag_wins(tmp_path: Path) -> None:
    checkpoint = tmp_path / "sweep-checkpoint.json"
    checkpoint.write_text(json.dumps({"next_id": 900_000}), encoding="utf-8")

    with patch.object(sweep_managers, "CHECKPOINT", checkpoint):
        fresh = _load_progress(start=1, resume=False)

    assert fresh.next_id == 1


def test_the_ceiling_reaches_past_the_managers_who_have_not_registered_yet() -> None:
    args = build_parser().parse_args([])

    # The first sweep stopped at 2.5M because that was the ceiling, not because
    # the ids ran out. Another ten million sign up before a deadline.
    assert args.until >= 12_000_000


def test_a_time_budget_is_optional_and_must_be_positive() -> None:
    assert build_parser().parse_args([]).max_seconds is None
    assert build_parser().parse_args(["--max-seconds", "3600"]).max_seconds == 3600

    parser = build_parser()
    try:
        parser.parse_args(["--max-seconds", "0"])
    except SystemExit as exit_code:
        assert exit_code.code == 2
    else:
        raise AssertionError("a zero-second budget should be refused")


def test_the_end_of_the_register_is_more_ids_than_any_observed_gap() -> None:
    """13,323 gaps in the first 2.5M ids, none of them remotely this wide."""
    assert EMPTY_BLOCKS_TO_STOP * sweep_managers.BLOCK >= 6_000


def test_progress_round_trips_through_the_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "sweep-checkpoint.json"
    written = Progress(next_id=41, with_history=9, qualifying=2, reached_end_at=40)

    with patch.object(sweep_managers, "CHECKPOINT", checkpoint):
        sweep_managers._save_progress(written)
        restored = _load_progress(start=1, resume=True)

    assert restored == written
