"""A gap in the gameweeks changes every aggregate, and says nothing about it.

Bias, error and season totals are all sums over whatever weeks the corpus
happens to hold. Nothing downstream counts them, so a missing gameweek moves
every published figure with no signal at all.

Reported rather than raised: an in-progress season is legitimately short, and
only a hole in the middle is a fault.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)


def _corpus(gameweeks: list[int]) -> SeasonCorpus:
    corpus = SeasonCorpus(season="2025-26")
    for gameweek in gameweeks:
        corpus.rows_by_gameweek[gameweek] = [
            ElementRow(
                gameweek=gameweek,
                element_id=1,
                element_code=1,
                fixture_id=gameweek,
                minutes=90,
                started=True,
                goals=0,
                assists=0,
                expected_goals=0.0,
                expected_assists=0.0,
                total_points=2,
                price_tenths=50,
                selected=1,
                kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
            )
        ]
    return corpus


class MissingGameweekTest(unittest.TestCase):
    def test_a_contiguous_run_reports_nothing(self) -> None:
        self.assertEqual(_corpus([1, 2, 3, 4]).missing_gameweeks, ())

    def test_a_hole_in_the_middle_is_named(self) -> None:
        self.assertEqual(_corpus([1, 2, 4, 5]).missing_gameweeks, (3,))

    def test_every_hole_is_named(self) -> None:
        self.assertEqual(_corpus([1, 3, 5]).missing_gameweeks, (2, 4))

    def test_a_run_of_holes_is_named_in_full(self) -> None:
        self.assertEqual(_corpus([1, 6]).missing_gameweeks, (2, 3, 4, 5))

    def test_a_season_that_starts_late_is_not_a_gap(self) -> None:
        """Only the interior counts; a corpus can legitimately begin at GW7."""
        self.assertEqual(_corpus([7, 8, 9]).missing_gameweeks, ())

    def test_a_single_gameweek_has_no_interior(self) -> None:
        self.assertEqual(_corpus([12]).missing_gameweeks, ())

    def test_an_empty_corpus_reports_nothing(self) -> None:
        self.assertEqual(_corpus([]).missing_gameweeks, ())

    def test_the_order_is_ascending_so_a_report_reads_naturally(self) -> None:
        gaps = _corpus([1, 10]).missing_gameweeks

        self.assertEqual(list(gaps), sorted(gaps))


if __name__ == "__main__":
    unittest.main()
