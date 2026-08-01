"""An opening squad is judged on the eleven it fields, not the fifteen it owns.

The rules encoded here came from the owner, who plays the game: you score
eleven, your substitutes have to be capable of playing, and with one transfer a
week a squad you can leave alone is worth more than one you must keep repairing.
"""

from __future__ import annotations

import unittest

import pytest

from fpl_andres.planning.opening import (
    OpeningSettings,
    best_eleven,
    choose_opening_squad,
)
from fpl_andres.simulation.squad import Candidate, SquadRules

RULES = SquadRules(budget_tenths=1000, club_limit=3, position_counts={1: 2, 2: 5, 3: 5, 4: 3})
SETTINGS = OpeningSettings(rules=RULES)


def player(element_id: int, position: int, price: int, team: int) -> Candidate:
    return Candidate(
        element_id=element_id,
        element_code=element_id * 10,
        position=position,
        team_id=team,
        price_tenths=price,
        web_name=f"P{element_id}",
    )


def _pool() -> list[Candidate]:
    """Enough players at each position, spread over enough clubs to be legal."""
    pool: list[Candidate] = []
    element_id = 1
    for position, count in ((1, 12), (2, 30), (3, 30), (4, 20)):
        for index in range(count):
            pool.append(player(element_id, position, 40 + (index % 8) * 5, team=index % 10 + 1))
            element_id += 1
    return pool


class BestElevenTest(unittest.TestCase):
    def test_fields_a_legal_formation(self) -> None:
        squad = [player(i, 1, 40, 1) for i in range(1, 3)]
        squad += [player(i, 2, 40, i) for i in range(3, 8)]
        squad += [player(i, 3, 40, i) for i in range(8, 13)]
        squad += [player(i, 4, 40, i) for i in range(13, 16)]
        points = {member.element_id: float(member.element_id) for member in squad}

        eleven, _ = best_eleven(squad, points, SETTINGS)

        self.assertEqual(len(eleven), 11)
        self.assertEqual(sum(1 for p in eleven if p.position == 1), 1)
        self.assertGreaterEqual(sum(1 for p in eleven if p.position == 2), 3)
        self.assertGreaterEqual(sum(1 for p in eleven if p.position == 4), 1)

    def test_never_starts_two_goalkeepers(self) -> None:
        squad = [player(1, 1, 40, 1), player(2, 1, 40, 2)]
        squad += [player(i, 2, 40, i) for i in range(3, 8)]
        squad += [player(i, 3, 40, i) for i in range(8, 13)]
        squad += [player(i, 4, 40, i) for i in range(13, 16)]
        # Both keepers are the best scorers in the squad.
        points = {member.element_id: 1.0 for member in squad}
        points[1] = 99.0
        points[2] = 98.0

        eleven, _ = best_eleven(squad, points, SETTINGS)

        self.assertEqual(sum(1 for p in eleven if p.position == 1), 1)


class ChooseOpeningSquadTest(unittest.TestCase):
    def test_refuses_a_bench_that_cannot_play(self) -> None:
        pool = _pool()
        points = {member.element_id: 1.0 for member in pool}
        # Only a handful of footballers actually start anywhere.
        start_rate = {member.element_id: 0.0 for member in pool}

        with self.assertRaises(ValueError):
            choose_opening_squad(pool, points, start_rate, SETTINGS)

    def test_spends_on_the_eleven_rather_than_the_fifteen(self) -> None:
        pool = _pool()
        start_rate = {member.element_id: 0.9 for member in pool}
        # One outstanding player at each outfield position, at three different
        # clubs so the three-per-club limit is not what decides the test.
        points = {member.element_id: 1.0 for member in pool}
        standouts = (13, 44, 75)
        for standout in standouts:
            points[standout] = 20.0
        self.assertEqual(
            len({next(p for p in pool if p.element_id == s).team_id for s in standouts}),
            3,
        )

        plan = choose_opening_squad(pool, points, start_rate, SETTINGS)
        starting = {member.element_id for member in plan.starters}

        for standout in standouts:
            self.assertIn(standout, starting, f"{standout} should be picked and started")

    # Runs the HiGHS solver over a full candidate pool.
    @pytest.mark.slow
    def test_produces_a_legal_squad_inside_the_budget(self) -> None:
        pool = _pool()
        points = {member.element_id: float(member.element_id % 7) for member in pool}
        start_rate = {member.element_id: 0.8 for member in pool}

        plan = choose_opening_squad(pool, points, start_rate, SETTINGS)

        self.assertEqual(len(plan.squad), 15)
        self.assertEqual(len(plan.starters), 11)
        self.assertEqual(len(plan.bench), 4)
        self.assertLessEqual(plan.spent_tenths, RULES.budget_tenths)
        for team in {member.team_id for member in plan.squad}:
            self.assertLessEqual(sum(1 for member in plan.squad if member.team_id == team), 3)

    def test_the_bench_counts_for_something_but_not_everything(self) -> None:
        pool = _pool()
        points = {member.element_id: 1.0 for member in pool}
        start_rate = {member.element_id: 0.8 for member in pool}

        plan = choose_opening_squad(pool, points, start_rate, SETTINGS)

        # Eleven players at one point each; the bench is not in this figure.
        self.assertAlmostEqual(plan.expected_points, 11.0)


if __name__ == "__main__":
    unittest.main()
