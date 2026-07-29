from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.models.contracts import FixtureResult
from fpl_andres.models.walk_forward import iter_walk_forward_slices, walk_forward_split


def fixture(
    *,
    event: int,
    kickoff: datetime,
    available: datetime,
    home: int,
    away: int,
) -> FixtureResult:
    return FixtureResult(
        season="2026-27",
        event=event,
        home_team_id=home,
        away_team_id=away,
        home_goals=1,
        away_goals=0,
        kickoff_time=kickoff,
        data_available_at=available,
        source_hash=f"sha256:{event:064x}",
    )


CUTOFF = datetime(2026, 8, 16, 20, tzinfo=UTC)
PLAYED = fixture(
    event=1,
    kickoff=datetime(2026, 8, 16, 15, tzinfo=UTC),
    available=datetime(2026, 8, 16, 18, tzinfo=UTC),
    home=1,
    away=2,
)
AVAILABLE_AT_CUTOFF = fixture(
    event=1,
    kickoff=datetime(2026, 8, 16, 17, tzinfo=UTC),
    available=CUTOFF,
    home=3,
    away=4,
)
LATE_RESULT = fixture(
    event=1,
    kickoff=datetime(2026, 8, 16, 16, tzinfo=UTC),
    available=CUTOFF + timedelta(minutes=30),
    home=5,
    away=6,
)
FUTURE = fixture(
    event=2,
    kickoff=datetime(2026, 8, 22, 15, tzinfo=UTC),
    available=datetime(2026, 8, 22, 18, tzinfo=UTC),
    home=99,
    away=1,
)


def test_walk_forward_split_separates_available_future_and_late_results() -> None:
    result = walk_forward_split(
        (FUTURE, LATE_RESULT, AVAILABLE_AT_CUTOFF, PLAYED),
        prediction_cutoff=CUTOFF,
    )

    assert [(row.home_team_id, row.away_team_id) for row in result.train] == [
        (1, 2),
        (3, 4),
    ]
    assert [(row.home_team_id, row.away_team_id) for row in result.holdout] == [(99, 1)]
    assert [(row.home_team_id, row.away_team_id) for row in result.rejected_leaks] == [(5, 6)]
    assert all(row.home_team_id != 99 for row in result.train)


def test_walk_forward_split_is_invariant_to_input_order() -> None:
    forward = walk_forward_split(
        (PLAYED, AVAILABLE_AT_CUTOFF, LATE_RESULT, FUTURE),
        prediction_cutoff=CUTOFF,
    )
    reverse = walk_forward_split(
        (FUTURE, LATE_RESULT, AVAILABLE_AT_CUTOFF, PLAYED),
        prediction_cutoff=CUTOFF,
    )

    assert reverse == forward


def test_walk_forward_cutoffs_must_increase_strictly() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        tuple(
            iter_walk_forward_slices(
                (PLAYED, FUTURE),
                prediction_cutoffs=(CUTOFF, CUTOFF),
            )
        )


def test_walk_forward_rejects_naive_cutoff() -> None:
    with pytest.raises(ValueError, match="aware UTC"):
        walk_forward_split((PLAYED,), prediction_cutoff=CUTOFF.replace(tzinfo=None))
