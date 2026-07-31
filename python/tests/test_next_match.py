"""Between-seasons projection: a per-match rate, with no fixture to lean on.

The pre-season number is the one most likely to be over-read, so its boundaries
are pinned here: it must ignore the fixture list entirely, key on the code that
follows a player between seasons, and stay silent about anyone without evidence.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.fixtures import Fixture
from fpl_andres.backtesting.projector import project_next_match

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
STEADY = 1
CAMEO = 2
TEAM = 1
OPPONENT = 2


def _row(gameweek: int, element_id: int, *, minutes: int, points: int) -> ElementRow:
    return ElementRow(
        gameweek=gameweek,
        element_id=element_id,
        element_code=element_id * 1000,
        fixture_id=gameweek * 10 + element_id,
        minutes=minutes,
        started=minutes >= 60,
        goals=1 if points >= 6 else 0,
        assists=0,
        expected_goals=0.5,
        expected_assists=0.2,
        total_points=points,
        price_tenths=70 + gameweek,
        selected=1000,
        kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
        clean_sheets=0,
        saves=0,
        bonus=1,
    )


def _corpus(*, with_fixtures: bool) -> SeasonCorpus:
    corpus = SeasonCorpus(season="2025-26")
    for element_id in (STEADY, CAMEO):
        corpus.position_by_element[element_id] = 4
        corpus.team_by_element[element_id] = TEAM
        corpus.name_by_element[element_id] = f"P{element_id}"
        corpus.code_by_element[element_id] = element_id * 1000

    for gameweek in range(1, 21):
        rows = [_row(gameweek, STEADY, minutes=90, points=6)]
        # Two brief appearances is not a season anyone can describe.
        if gameweek <= 2:
            rows.append(_row(gameweek, CAMEO, minutes=8, points=1))
        corpus.rows_by_gameweek[gameweek] = rows

    if with_fixtures:
        for event in range(1, 21):
            corpus.fixtures_by_event[event] = [
                Fixture(
                    fixture_id=event,
                    event=event,
                    team_h=TEAM,
                    team_a=OPPONENT,
                    kickoff_time=KICKOFF + timedelta(days=7 * event),
                    team_h_score=3,
                    team_a_score=0,
                    finished=True,
                )
            ]
    return corpus


class ProjectNextMatchTest(unittest.TestCase):
    def test_projects_a_single_match_not_a_season(self) -> None:
        [projection] = [
            entry
            for entry in project_next_match(_corpus(with_fixtures=False))
            if entry.element_id == STEADY
        ]

        # An ever-present is projected near, but below, a full match: the
        # minutes model shrinks toward a prior rather than promising ninety.
        self.assertGreater(projection.expected_minutes, 75.0)
        self.assertLess(projection.expected_minutes, 90.0)
        # One match of a player scoring six a week, not twenty.
        self.assertGreater(projection.expected_points, 2.0)
        self.assertLess(projection.expected_points, 12.0)

    def test_the_fixture_list_makes_no_difference(self) -> None:
        """A schedule that has already been played must not tilt next season."""
        without = {
            entry.code: entry.expected_points
            for entry in project_next_match(_corpus(with_fixtures=False))
        }
        with_schedule = {
            entry.code: entry.expected_points
            for entry in project_next_match(_corpus(with_fixtures=True))
        }

        self.assertEqual(without.keys(), with_schedule.keys())
        for code, points in without.items():
            self.assertAlmostEqual(points, with_schedule[code], places=6)

    def test_keys_on_the_code_that_survives_the_season(self) -> None:
        codes = {entry.code for entry in project_next_match(_corpus(with_fixtures=False))}

        self.assertIn(STEADY * 1000, codes)
        self.assertNotIn(STEADY, codes)

    def test_a_player_without_minutes_is_left_out(self) -> None:
        projected = {entry.element_id for entry in project_next_match(_corpus(with_fixtures=False))}

        self.assertNotIn(CAMEO, projected)

    def test_an_empty_season_projects_nobody(self) -> None:
        self.assertEqual(project_next_match(SeasonCorpus(season="2025-26")), [])


if __name__ == "__main__":
    unittest.main()
