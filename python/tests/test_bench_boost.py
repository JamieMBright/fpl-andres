"""The bench boost is decided by the worst of the fifteen, not the fixture count.

Owner's rule: play it when all fifteen have a reasonable expectation. A large
double gameweek with two players blanking is worth less than an ordinary week
where everybody is on the pitch.
"""

from __future__ import annotations

import random
import unittest

from fpl_andres.simulation.chips import plan_chips

NORMAL = {event: 10 for event in range(1, 39)}


def _plan(floor: dict[int, float] | None, fixtures: dict[int, int] | None = None):
    return plan_chips(
        fixtures_by_event=fixtures or NORMAL,
        star_fixture_value={},
        from_gameweek=1,
        last_event=38,
        rng=random.Random(7),
        squad_floor_value=floor,
    )


def _week_of(plan: dict[int, str], chip: str) -> int | None:
    return next((week for week, name in plan.items() if name == chip), None)


class BenchBoostTest(unittest.TestCase):
    def test_takes_the_week_the_weakest_player_is_worth_most(self) -> None:
        floor = {event: 1.0 for event in range(1, 39)}
        floor[24] = 5.0

        self.assertEqual(_week_of(_plan(floor), "bench_boost"), 24)

    def test_a_blanking_squad_member_sinks_a_double_gameweek(self) -> None:
        """Ten fixtures where everyone plays beats twelve where two do not."""
        fixtures = dict(NORMAL)
        fixtures[30] = 14
        floor = {event: 1.0 for event in range(1, 39)}
        # The big double leaves somebody without a fixture at all.
        floor[30] = 0.0
        floor[12] = 2.0

        plan = _plan(floor, fixtures)

        self.assertEqual(_week_of(plan, "bench_boost"), 12)
        self.assertNotEqual(_week_of(plan, "bench_boost"), 30)

    def test_a_squad_with_no_playable_week_is_left_undated(self) -> None:
        self.assertIsNone(_week_of(_plan({event: 0.0 for event in range(1, 39)}), "bench_boost"))

    def test_without_a_floor_it_falls_back_to_the_second_double(self) -> None:
        fixtures = dict(NORMAL)
        fixtures[20] = 16
        fixtures[30] = 14

        plan = _plan(None, fixtures)

        self.assertEqual(_week_of(plan, "free_hit"), 20)
        self.assertEqual(_week_of(plan, "bench_boost"), 30)

    def test_it_never_lands_on_the_free_hit_week(self) -> None:
        floor = {event: 1.0 for event in range(1, 39)}
        # The free hit takes the week this fifteen is worth least. The bench
        # boost must not then be asked to play a bench that is not there.
        floor[20] = 0.0
        floor[24] = 5.0

        plan = _plan(floor)

        self.assertEqual(_week_of(plan, "free_hit"), 20)
        self.assertNotEqual(_week_of(plan, "bench_boost"), 20)


if __name__ == "__main__":
    unittest.main()
