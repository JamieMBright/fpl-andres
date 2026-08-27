from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fpl_andres.cli.capture_cohort_picks import (
    _capture_source,
    _parse_picks,
    _write,
    build_parser,
)
from fpl_andres.cohorts.fpl500_membership import build_membership, write_membership
from fpl_andres.cohorts.portfolio import Portfolio

DEADLINE = datetime(2026, 8, 21, 17, 30, tzinfo=UTC)
SOURCE_COMMIT = "7ee37f9ef2eb40502b94cba4e2bd0a10cd84b1ad"


def _membership(path: Path, *, event: int = 1) -> None:
    membership = build_membership(
        {
            "generatedAt": (DEADLINE + timedelta(minutes=12)).isoformat(),
            "catalogueSize": 2_786,
            "size": 500,
            "managers": [{"entryId": entry_id} for entry_id in range(1, 501)],
        },
        event=event,
        deadline=DEADLINE,
        source_commit=SOURCE_COMMIT,
        source_path="data/cohort/fpl500.json",
        pinned_at=DEADLINE + timedelta(days=5),
    )
    write_membership(membership, path)


def test_fixed_membership_is_the_capture_source_and_revision(tmp_path: Path) -> None:
    membership_path = tmp_path / "membership.json"
    _membership(membership_path)
    args = build_parser().parse_args(["--event", "1", "--membership", str(membership_path)])

    source = _capture_source(args)

    assert len(source.entry_ids) == 500
    assert source.entry_ids[0] == 1
    assert source.basis == "ranked-500"
    assert source.revision.startswith("sha256:")
    assert source.membership is not None


def test_fixed_membership_must_belong_to_the_captured_event(tmp_path: Path) -> None:
    membership_path = tmp_path / "membership.json"
    _membership(membership_path, event=2)
    args = build_parser().parse_args(["--event", "1", "--membership", str(membership_path)])

    with pytest.raises(ValueError, match="belongs to gameweek 2"):
        _capture_source(args)


def test_exact_portfolio_carries_membership_provenance_and_is_immutable(
    tmp_path: Path,
) -> None:
    membership_path = tmp_path / "membership.json"
    _membership(membership_path)
    args = build_parser().parse_args(["--event", "1", "--membership", str(membership_path)])
    source = _capture_source(args)
    portfolio = Portfolio(
        event=1,
        cohort_revision=source.revision,
        attempted=500,
        responded=500,
        counted=500,
        free_hit=0,
        holdings=(),
        basis=source.basis,
    )

    output = _write(portfolio, tmp_path / "portfolio", membership=source.membership)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["basis"] == "ranked-500"
    assert saved["membership"]["label"] == "post-deadline capture-era FPL500 membership"
    assert saved["membership"]["sourceCommit"] == SOURCE_COMMIT
    assert saved["membership"]["size"] == 500
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _write(portfolio, tmp_path / "portfolio", membership=source.membership)


def test_pick_payload_retains_only_the_history_needed_for_aggregate_evidence() -> None:
    row = _parse_picks(
        17,
        1,
        {
            "active_chip": "bboost",
            "picks": [
                {
                    "element": 11,
                    "position": 1,
                    "multiplier": 1,
                    "is_captain": False,
                    "is_vice_captain": False,
                }
            ],
            "entry_history": {
                "event": 1,
                "points": 72,
                "points_on_bench": 14,
                "value": 1003,
                "bank": 7,
                "event_transfers": 0,
                "event_transfers_cost": 0,
                "overall_rank": 123,
            },
        },
    )

    assert row.active_chip == "bboost"
    assert row.history is not None
    assert row.history.points == 72
    assert row.history.points_on_bench == 14
    assert row.history.value_tenths == 1003
    assert row.history.bank_tenths == 7
