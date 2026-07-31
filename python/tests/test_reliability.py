"""Return shape: how dependable a holding is, not how large."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.reliability import describe_shape

KICKOFF = datetime(2024, 8, 17, 14, 0, tzinfo=UTC)


def rows(scores: list[int], *, minutes: int = 90) -> list[ElementRow]:
    return [
        ElementRow(
            gameweek=index + 1,
            element_id=1,
            element_code=1,
            fixture_id=index + 1,
            minutes=minutes,
            started=True,
            goals=0,
            assists=0,
            expected_goals=None,
            expected_assists=None,
            total_points=score,
            price_tenths=50,
            selected=1000,
            kickoff_time=KICKOFF + timedelta(days=7 * index),
        )
        for index, score in enumerate(scores)
    ]


def test_a_steady_returner_has_a_higher_floor_than_a_lottery_ticket() -> None:
    # Same mean of four, completely different holdings.
    steady = describe_shape(rows([4, 4, 4, 4, 4, 4, 4, 4, 4, 4]))
    lumpy = describe_shape(rows([0, 0, 0, 0, 0, 0, 0, 13, 13, 14]))

    assert steady.floor > lumpy.floor
    assert steady.volatility < lumpy.volatility
    assert lumpy.ceiling > steady.ceiling


def test_the_blank_rate_counts_bare_appearances() -> None:
    shape = describe_shape(rows([2, 2, 1, 9, 8]))

    assert shape.blank_rate == 0.6
    assert shape.return_rate == 0.4


def test_gameweeks_the_player_missed_are_excluded() -> None:
    played = rows([6, 6, 6, 6])
    benched = rows([0, 0, 0, 0], minutes=0)

    shape = describe_shape([*played, *benched])

    assert shape.appearances == 4
    assert shape.median == 6.0


def test_a_thin_history_is_reported_as_unmeasured() -> None:
    assert not describe_shape(rows([9, 9])).is_measured
    assert describe_shape(rows([9, 9, 9, 9])).is_measured


def test_no_appearances_yields_a_zeroed_shape_rather_than_an_error() -> None:
    shape = describe_shape(rows([0, 0], minutes=0))

    assert shape.appearances == 0
    assert shape.floor == 0.0
    assert not shape.is_measured
