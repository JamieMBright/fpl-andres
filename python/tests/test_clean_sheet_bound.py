"""A probability cannot exceed one, however soft the fixture.

The best defenders keep a clean sheet in over half their matches and the fixture
multiplier reaches 2.2, so the unclamped product reached 1.238 against Gabriel's
2025-26 record: nearly five points for a four-point clean sheet, and only ever
for premium defenders in the easiest fixtures.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.fixtures import RouteAdjustment
from fpl_andres.backtesting.projector import _league_rates, _supporting_points

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
DEFENDER = 2
CLEAN_SHEET_POINTS = 4


def _rows(clean_sheets: list[int]) -> list[ElementRow]:
    return [
        ElementRow(
            gameweek=index,
            element_id=1,
            element_code=1000,
            fixture_id=index,
            minutes=90,
            started=True,
            goals=0,
            assists=0,
            expected_goals=0.0,
            expected_assists=0.0,
            total_points=6,
            price_tenths=60,
            selected=1000,
            kickoff_time=KICKOFF + timedelta(days=7 * index),
            clean_sheets=sheet,
            saves=0,
            bonus=0,
            goals_conceded=0,
        )
        for index, sheet in enumerate(clean_sheets, start=1)
    ]


class _Minutes:
    probability_sixty_minutes = 1.0
    expected_minutes = 90.0


def _points(clean_sheets: list[int], multiplier: float) -> float:
    rows = _rows(clean_sheets)
    league = _league_rates(rows, {1: DEFENDER})
    return _supporting_points(
        rows,
        DEFENDER,
        _Minutes(),  # type: ignore[arg-type]
        league,
        5.0,
        RouteAdjustment(1.0, multiplier, 1.0, 1.0, 1.0),
    )


class CleanSheetBoundTest(unittest.TestCase):
    def test_a_soft_fixture_never_pays_more_than_a_clean_sheet_is_worth(self) -> None:
        """Better than one clean sheet in two, against the softest opponent."""
        elite = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1]

        self.assertLessEqual(_points(elite, 2.2), CLEAN_SHEET_POINTS + 1e-9)

    def test_a_soft_fixture_still_pays_more_than_a_hard_one(self) -> None:
        steady = [1, 0] * 8

        self.assertGreater(_points(steady, 1.6), _points(steady, 0.6))

    def test_a_defender_who_never_keeps_one_is_paid_nothing_for_it(self) -> None:
        self.assertAlmostEqual(_points([0] * 16, 2.2), 0.0, delta=1e-9)


if __name__ == "__main__":
    unittest.main()
