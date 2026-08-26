from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fpl_andres.cli import pin_fpl500_membership
from fpl_andres.cohorts.fpl500_membership import (
    build_membership,
    read_membership,
    write_membership,
)

DEADLINE = datetime(2026, 8, 21, 17, 30, tzinfo=UTC)
SOURCE_COMMIT = "7ee37f9ef2eb40502b94cba4e2bd0a10cd84b1ad"


def _source(entry_ids: list[int]) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "generatedAt": (DEADLINE + timedelta(minutes=12)).isoformat().replace("+00:00", "Z"),
        "catalogueSize": 2_786,
        "size": len(entry_ids),
        "managers": [{"entryId": entry_id} for entry_id in entry_ids],
    }


def test_membership_pin_names_its_post_deadline_source_honestly() -> None:
    membership = build_membership(
        _source(list(range(1, 501))),
        event=1,
        deadline=DEADLINE,
        source_commit=SOURCE_COMMIT,
        source_path="data/cohort/fpl500.json",
        pinned_at=DEADLINE + timedelta(days=5),
    )

    assert membership.size == 500
    assert membership.source_catalogue_size == 2_786
    assert membership.source_commit == SOURCE_COMMIT
    assert membership.source_timing == "post-deadline"
    assert membership.label == "post-deadline capture-era FPL500 membership"
    assert membership.seconds_from_deadline == 12 * 60
    assert membership.membership_hash.startswith("sha256:")


def test_membership_hash_describes_the_set_not_ranking_order() -> None:
    forward = build_membership(
        _source(list(range(1, 501))),
        event=1,
        deadline=DEADLINE,
        source_commit=SOURCE_COMMIT,
        source_path="data/cohort/fpl500.json",
        pinned_at=DEADLINE + timedelta(days=5),
    )
    reverse = build_membership(
        _source(list(range(500, 0, -1))),
        event=1,
        deadline=DEADLINE,
        source_commit=SOURCE_COMMIT,
        source_path="data/cohort/fpl500.json",
        pinned_at=DEADLINE + timedelta(days=5),
    )

    assert forward.membership_hash == reverse.membership_hash


def test_membership_pin_refuses_anything_other_than_500_unique_entries() -> None:
    with pytest.raises(ValueError, match="500 unique"):
        build_membership(
            _source([*range(1, 500), 499]),
            event=1,
            deadline=DEADLINE,
            source_commit=SOURCE_COMMIT,
            source_path="data/cohort/fpl500.json",
            pinned_at=DEADLINE + timedelta(days=5),
        )


def test_membership_file_is_immutable_and_round_trips(tmp_path: Path) -> None:
    membership = build_membership(
        _source(list(range(1, 501))),
        event=1,
        deadline=DEADLINE,
        source_commit=SOURCE_COMMIT,
        source_path="data/cohort/fpl500.json",
        pinned_at=DEADLINE + timedelta(days=5),
    )
    output = tmp_path / "gw01.json"

    write_membership(membership, output)

    assert read_membership(output) == membership
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_membership(membership, output)


def test_pin_cli_reads_the_git_source_and_tracked_event_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deadlines = tmp_path / "deadlines.json"
    deadlines.write_text(
        '{"deadlines":[{"event":1,"deadline":"2026-08-21T17:30:00Z"}]}',
        encoding="utf-8",
    )
    output = tmp_path / "membership.json"
    monkeypatch.setattr(
        pin_fpl500_membership,
        "_git_source",
        lambda revision, path: (SOURCE_COMMIT, _source(list(range(1, 501)))),
    )

    status = pin_fpl500_membership.main(
        [
            "--event",
            "1",
            "--source-commit",
            "7ee37f9",
            "--deadline-ledger",
            str(deadlines),
            "--output",
            str(output),
        ]
    )

    saved = read_membership(output)
    assert status == 0
    assert saved.source_commit == SOURCE_COMMIT
    assert saved.deadline == DEADLINE
