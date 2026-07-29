from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from fpl_andres.models.contracts import FixtureResult


@dataclass(frozen=True)
class WalkForwardSlice:
    prediction_cutoff: datetime
    train: tuple[FixtureResult, ...]
    holdout: tuple[FixtureResult, ...]
    rejected_leaks: tuple[FixtureResult, ...]


def walk_forward_split(
    fixtures: Sequence[FixtureResult],
    *,
    prediction_cutoff: datetime,
) -> WalkForwardSlice:
    _require_utc(prediction_cutoff)
    train: list[FixtureResult] = []
    holdout: list[FixtureResult] = []
    rejected_leaks: list[FixtureResult] = []

    for fixture in fixtures:
        if fixture.kickoff_time > prediction_cutoff:
            holdout.append(fixture)
        elif fixture.data_available_at <= prediction_cutoff:
            train.append(fixture)
        else:
            rejected_leaks.append(fixture)

    return WalkForwardSlice(
        prediction_cutoff=prediction_cutoff,
        train=tuple(sorted(train, key=_fixture_order)),
        holdout=tuple(sorted(holdout, key=_fixture_order)),
        rejected_leaks=tuple(sorted(rejected_leaks, key=_fixture_order)),
    )


def iter_walk_forward_slices(
    fixtures: Sequence[FixtureResult],
    *,
    prediction_cutoffs: Sequence[datetime],
) -> Iterator[WalkForwardSlice]:
    previous: datetime | None = None
    for cutoff in prediction_cutoffs:
        _require_utc(cutoff)
        if previous is not None and cutoff <= previous:
            raise ValueError("prediction cutoffs must be strictly increasing")
        previous = cutoff
        yield walk_forward_split(fixtures, prediction_cutoff=cutoff)


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("prediction cutoff must be an aware UTC timestamp")


def _fixture_order(fixture: FixtureResult) -> tuple[datetime, int, int]:
    return fixture.kickoff_time, fixture.home_team_id, fixture.away_team_id
