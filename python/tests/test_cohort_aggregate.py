from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpl_andres.cli.capture_cohort_aggregate import write_aggregate
from fpl_andres.cohorts.portfolio import (
    EntryHistory,
    ManagerPicks,
    aggregate_manager_history,
)


def _row(
    entry: int,
    *,
    points: int,
    bench: int,
    chip: str | None,
    total_points: int | None = None,
    overall_rank: int | None = None,
) -> ManagerPicks:
    return ManagerPicks(
        entry_id=entry,
        event=1,
        picks=(),
        active_chip=chip,
        history=EntryHistory(
            points=points,
            points_on_bench=bench,
            value_tenths=1000 + entry,
            bank_tenths=entry,
            event_transfers=0,
            event_transfers_cost=0,
            total_points=total_points,
            overall_rank=overall_rank,
        ),
    )


def test_aggregate_reports_chips_and_distributions_but_not_fake_gw1_transfers() -> None:
    aggregate = aggregate_manager_history(
        [
            _row(1, points=50, bench=2, chip=None),
            _row(2, points=70, bench=8, chip="3xc"),
            _row(3, points=90, bench=14, chip="bboost"),
        ],
        event=1,
        attempted=3,
        cohort_revision="sha256:pinned",
        minimum_coverage=0.9,
    )

    assert aggregate.coverage == 1.0
    assert aggregate.chips == {"none": 1, "3xc": 1, "bboost": 1}
    assert aggregate.total_points.mean == pytest.approx(70)
    assert aggregate.total_points.median == pytest.approx(70)
    assert aggregate.bench_points.mean == pytest.approx(8)
    assert aggregate.transfers_available is False


def test_season_standing_is_the_cumulative_total_sorted_high_to_low() -> None:
    aggregate = aggregate_manager_history(
        [
            _row(1, points=50, bench=2, chip=None, total_points=200, overall_rank=9_000),
            _row(2, points=70, bench=8, chip=None, total_points=340, overall_rank=1_200),
            # No overall_rank yet: still counted, rank published as null.
            _row(3, points=90, bench=14, chip=None, total_points=90),
        ],
        event=1,
        attempted=3,
        cohort_revision="sha256:pinned",
        minimum_coverage=0.9,
    )

    assert [row.total_points for row in aggregate.season_standing] == [340, 200, 90]
    assert aggregate.season_standing[0].overall_rank == 1_200
    assert aggregate.season_standing[2].overall_rank is None


def test_season_standing_omits_an_entry_with_no_cumulative_total_at_all() -> None:
    aggregate = aggregate_manager_history(
        [
            _row(1, points=50, bench=2, chip=None, total_points=200),
            _row(2, points=70, bench=8, chip=None),
        ],
        event=1,
        attempted=2,
        cohort_revision="sha256:pinned",
        minimum_coverage=0.9,
    )

    assert len(aggregate.season_standing) == 1
    assert aggregate.season_standing[0].total_points == 200


def test_aggregate_sidecar_is_immutable_and_contains_no_manager_identity(
    tmp_path: Path,
) -> None:
    aggregate = aggregate_manager_history(
        [_row(1, points=50, bench=2, chip=None, total_points=50, overall_rank=1_000_000)],
        event=1,
        attempted=1,
        cohort_revision="sha256:pinned",
        minimum_coverage=0.9,
    )
    output = tmp_path / "gw01-aggregates.json"

    write_aggregate(aggregate, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["cohortRevision"] == "sha256:pinned"
    assert "entryId" not in json.dumps(payload)
    assert payload["seasonStanding"] == [{"overallRank": 1_000_000, "totalPoints": 50}]
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_aggregate(aggregate, output)
