"""Integer-payout routes must divide per match, never on the mean.

Saves pay one point per three and goals conceded cost one per two. Both are
floor divisions, so averaging first and dividing after inflates them: Jensen's
inequality, and worth about thirteen points across a goalkeeper's season.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.projector import project_next_match

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
KEEPER = 1


def _corpus(saves_per_match: list[int]) -> SeasonCorpus:
    corpus = SeasonCorpus(season="2025-26")
    corpus.position_by_element[KEEPER] = 1
    corpus.team_by_element[KEEPER] = 1
    corpus.name_by_element[KEEPER] = "Keeper"
    corpus.code_by_element[KEEPER] = 9001

    for index, saves in enumerate(saves_per_match, start=1):
        corpus.rows_by_gameweek[index] = [
            ElementRow(
                gameweek=index,
                element_id=KEEPER,
                element_code=9001,
                fixture_id=index,
                minutes=90,
                started=True,
                goals=0,
                assists=0,
                expected_goals=0.0,
                expected_assists=0.0,
                total_points=2,
                price_tenths=45,
                selected=1000,
                kickoff_time=KICKOFF + timedelta(days=7 * index),
                clean_sheets=0,
                saves=saves,
                bonus=0,
                goals_conceded=0,
            )
        ]
    return corpus


class IntegerPayoutTest(unittest.TestCase):
    """Compared against each other, because absolute points also carry the
    minutes model's shrinkage and that is not what these tests are about."""

    def _points(self, saves: list[int]) -> float:
        return project_next_match(_corpus(saves))[0].expected_points

    def test_two_saves_a_game_pays_nothing(self) -> None:
        """Two saves never reaches three, so it is worth the same as none."""
        self.assertAlmostEqual(self._points([2] * 20), self._points([0] * 20), delta=0.01)

    def test_three_saves_a_game_pays_one(self) -> None:
        """A point, scaled by expected minutes, which sit below a full ninety."""
        gain = self._points([3] * 20) - self._points([0] * 20)

        self.assertGreater(gain, 0.85)
        self.assertLessEqual(gain, 1.0)

    def test_the_same_mean_is_not_the_same_points(self) -> None:
        """2,2,2,6 averages three saves a game but pays half as often."""
        steady = self._points([3] * 20)
        lumpy = self._points([2, 2, 2, 6] * 5)

        self.assertLess(lumpy, steady)
        # Averaging first and dividing after would have made these equal.
        self.assertGreater(steady - lumpy, 0.4)


if __name__ == "__main__":
    unittest.main()
