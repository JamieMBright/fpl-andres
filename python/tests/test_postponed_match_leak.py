"""A postponed match is evidence that did not exist yet.

The rate and minutes models both carry a guard: an observation whose kickoff is
after the prediction cutoff is a leak and must raise. `backtesting/rates.py`
built every observation with `kickoff_time=min(row.kickoff_time, cutoff)`, so
the value handed to the guard could never exceed the cutoff and the guard could
never fire. What survived was a gameweek-number filter, and a gameweek number is
not a date.

Postponements are the case it was written for. A fixture labelled gameweek 12
and replayed in the week of gameweek 25 has `gameweek < prediction_event` for
everything from 13 onward, so it was admitted into training for gameweeks it had
not been played before. Weather postponements happen a few times a season; the
2019/20 suspension moved a quarter of one.

A guard that cannot fire is worse than no guard, because it reads as an
assurance. These tests hold both halves: the leak is refused, and the ordinary
case is untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.projector import ProjectionSettings
from fpl_andres.backtesting.rates import (
    project_element_minutes,
    project_element_rates,
)

SEASON_START = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
#: The decision moment for gameweek 20.
CUTOFF = SEASON_START + timedelta(days=7 * 20)


def _row(
    gameweek: int,
    kickoff: datetime,
    *,
    fixture_id: int | None = None,
    goals: int = 0,
    minutes: int = 90,
) -> ElementRow:
    return ElementRow(
        gameweek=gameweek,
        element_id=1,
        element_code=1,
        fixture_id=gameweek if fixture_id is None else fixture_id,
        minutes=minutes,
        started=minutes >= 60,
        goals=goals,
        assists=0,
        expected_goals=float(goals),
        expected_assists=0.0,
        total_points=2 + 5 * goals,
        price_tenths=50,
        selected=1000,
        kickoff_time=kickoff,
    )


def _played_before_the_cutoff() -> list[ElementRow]:
    return [_row(week, SEASON_START + timedelta(days=7 * week)) for week in range(1, 20)]


def _postponed() -> ElementRow:
    """Labelled gameweek 12, actually played a fortnight after the cutoff."""
    return _row(12, CUTOFF + timedelta(days=14), fixture_id=912, goals=3)


class TestPostponedMatchesAreNotEvidenceYet:
    def test_a_rate_ignores_a_match_played_after_the_cutoff(self) -> None:
        settings = ProjectionSettings()
        rows = _played_before_the_cutoff()

        without = project_element_rates(1, "2025-26", 20, rows, CUTOFF, settings, position=4)
        with_leak = project_element_rates(
            1, "2025-26", 20, [*rows, _postponed()], CUTOFF, settings, position=4
        )

        assert with_leak.goals_per_90 == without.goals_per_90

    def test_a_match_played_before_the_cutoff_still_counts(self) -> None:
        # The guard must refuse a date, not a gameweek number. Without this the
        # cheapest "fix" -- dropping anything out of gameweek order -- passes.
        settings = ProjectionSettings()
        rows = _played_before_the_cutoff()[:-1]
        scored = _row(19, SEASON_START + timedelta(days=7 * 19), goals=3)

        without = project_element_rates(1, "2025-26", 20, rows, CUTOFF, settings, position=4)
        with_goal = project_element_rates(
            1, "2025-26", 20, [*rows, scored], CUTOFF, settings, position=4
        )

        assert with_goal.goals_per_90 > without.goals_per_90

    def test_minutes_ignore_a_match_played_after_the_cutoff(self) -> None:
        settings = ProjectionSettings()
        rows = _played_before_the_cutoff()

        without = project_element_minutes(1, "2025-26", 20, rows, CUTOFF, settings)
        with_leak = project_element_minutes(
            1,
            "2025-26",
            20,
            [*rows, _row(12, CUTOFF + timedelta(days=14), fixture_id=912)],
            CUTOFF,
            settings,
        )

        assert with_leak.expected_minutes == without.expected_minutes

    def test_a_synthetic_kickoff_is_not_treated_as_a_leak(self) -> None:
        # A missing kickoff falls back to a year-2000 timestamp so the ordering
        # survives. Filtering on the date must not drop those rows.
        settings = ProjectionSettings()
        rows = [_row(week, datetime(2000, 1, 1, tzinfo=UTC)) for week in range(1, 20)]

        projection = project_element_minutes(1, "2025-26", 20, rows, CUTOFF, settings)

        assert projection.expected_minutes > 0.0
