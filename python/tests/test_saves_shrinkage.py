"""A keeper with two appearances was priced on two appearances.

Saves was the only supporting route with no shrinkage prior. Measured across
2023-24 to 2025-26: keepers with ten or more appearances spread 0.63-0.71 save
points a match, but the one-to-three bucket spread 0.00-1.50 against a league
rate near 0.65. One keeper projected 1.50 a match forever off two games.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.fixtures import RouteAdjustment
from fpl_andres.backtesting.rates import league_rates
from fpl_andres.backtesting.scoring import supporting_breakdown

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
GOALKEEPER = 1
PRIOR_NINETIES = 10.0


def _rows(saves: list[int], *, element_id: int = 1) -> list[ElementRow]:
    return [
        ElementRow(
            gameweek=index,
            element_id=element_id,
            element_code=1000 + element_id,
            fixture_id=index,
            minutes=90,
            started=True,
            goals=0,
            assists=0,
            expected_goals=0.0,
            expected_assists=0.0,
            total_points=3,
            price_tenths=45,
            selected=1000,
            kickoff_time=KICKOFF + timedelta(days=7 * index),
            clean_sheets=0,
            saves=made,
            bonus=0,
            goals_conceded=0,
        )
        for index, made in enumerate(saves, start=1)
    ]


class _Minutes:
    probability_sixty_minutes = 1.0
    expected_minutes = 90.0


def _save_points(own: list[int], league_rows: list[ElementRow]) -> float:
    rows = _rows(own)
    positions = {row.element_id: GOALKEEPER for row in [*rows, *league_rows]}
    league = league_rates([*rows, *league_rows], positions)
    return supporting_breakdown(
        rows,
        GOALKEEPER,
        _Minutes(),  # type: ignore[arg-type]
        league,
        PRIOR_NINETIES,
        RouteAdjustment(
            attacking=1.0,
            clean_sheet=1.0,
            conceding=1.0,
            saves=1.0,
            defensive_contribution=1.0,
        ),
    ).total


class SavesShrinkageTest(unittest.TestCase):
    def setUp(self) -> None:
        # A league of ordinary keepers making three saves a match.
        self.league = _rows([3] * 40, element_id=2)

    def test_a_thin_hot_record_is_pulled_toward_the_league(self) -> None:
        """Two games at six saves must not project six saves forever."""
        thin = _save_points([6, 6], self.league)
        unshrunk = 6 // 3

        self.assertLess(thin, unshrunk)

    def test_a_long_record_keeps_its_own_rate(self) -> None:
        """Evidence should outweigh the prior once there is enough of it."""
        thin = _save_points([6, 6], self.league)
        long = _save_points([6] * 38, self.league)

        self.assertGreater(long, thin)

    def test_a_thin_cold_record_is_also_pulled_up(self) -> None:
        """Shrinkage is not a one-way discount."""
        cold = _save_points([0, 0], self.league)

        self.assertGreater(cold, 0.0)

    def test_shrinkage_never_inverts_the_ordering(self) -> None:
        busy = _save_points([9] * 20, self.league)
        quiet = _save_points([0] * 20, self.league)

        self.assertGreater(busy, quiet)


if __name__ == "__main__":
    unittest.main()
