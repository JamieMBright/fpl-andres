"""Chip strategy.

Each chip wants a different kind of gameweek, and three of the four can be
picked off the fixture list before a ball is kicked:

- **Triple captain** wants the squad's most expensive attacker against the
  league's leakiest defence. That is a fixture you can find in advance, not a
  moment you have to guess at.
- **Free hit** wants the largest double gameweek: a whole team playing twice,
  for one week, handed back afterwards.
- **Bench boost** wants the next largest double, where all fifteen play.
- **Wildcard** is not dated here. It is taken opportunistically, subject only to
  the game's own rule of one per half of the season.

Timing uses the fixture list and team strength measured from results to date.
Neither is a future result, so nothing here is hindsight.

One caveat worth stating plainly: double gameweeks are confirmed in-season as
cup runs resolve, so a real manager has less notice than this planner assumes.
The timing is a ceiling on what fixture-based planning can achieve rather than a
claim about what was knowable in August.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "ChipName",
    "ChipState",
    "plan_chips",
]

ChipName = Literal["wildcard", "free_hit", "triple_captain", "bench_boost"]

# FPL grants a second wildcard in the second half. The boundary is a rule of the
# game rather than a preference, so it is named rather than tuned.
_SECOND_HALF_FIRST_EVENT = 20
_FINAL_EVENT = 38
_NORMAL_FIXTURE_COUNT = 10


@dataclass
class ChipState:
    """Which chips remain, and when each was played."""

    played: dict[ChipName, int] = field(default_factory=dict)
    wildcards_used_by_half: dict[int, int] = field(default_factory=dict)

    def half_of(self, gameweek: int) -> int:
        return 1 if gameweek < _SECOND_HALF_FIRST_EVENT else 2

    def available(self, chip: ChipName, gameweek: int) -> bool:
        if chip == "wildcard":
            return self.wildcards_used_by_half.get(self.half_of(gameweek), 0) == 0
        return chip not in self.played

    def record(self, chip: ChipName, gameweek: int) -> None:
        self.played[chip] = gameweek
        if chip == "wildcard":
            half = self.half_of(gameweek)
            self.wildcards_used_by_half[half] = self.wildcards_used_by_half.get(half, 0) + 1


def plan_chips(
    *,
    fixtures_by_event: Mapping[int, int],
    star_fixture_value: Mapping[int, float],
    from_gameweek: int,
    last_event: int,
    rng: random.Random,
    squad_floor_value: Mapping[int, float] | None = None,
) -> dict[int, ChipName]:
    """Date every chip once, from the calendar rather than week by week.

    Every placement reads the squad, because a chip is worth what *this*
    fifteen makes of it. That is not a refinement, it is the difference between
    a simulation and a coincidence: the free hit used to take the largest
    double gameweek, which is a property of the fixture list alone, so every
    manager in a simulated league played it in the same week and the league had
    no variance in the one dimension it exists to measure.

    ``star_fixture_value`` scores each gameweek for the squad's best captaincy
    option: how leaky the opponent is, times how often he plays. The triple
    captain takes the highest.

    ``squad_floor_value`` scores each gameweek by the *weakest* of the fifteen.
    The bench boost takes the highest, because the chip pays all fifteen and is
    decided by the worst of them: a big double with two players blanking is
    worth less than an ordinary week where everybody plays.

    The free hit takes the lowest, because it replaces the squad for one week
    and is worth most where the squad is worst — which is what a blank gameweek
    is. Wildcards take the worst remaining week in each half, a rebuild being
    permanent where a free hit is not.

    With no squad value supplied every one of these falls back to the fixture
    calendar, which is a guess and produces exactly the uniformity described
    above.
    """
    weeks = list(range(from_gameweek, last_event + 1))
    if not weeks:
        return {}
    plan: dict[int, ChipName] = {}

    doubles = sorted(
        (week for week in weeks if fixtures_by_event.get(week, 0) > _NORMAL_FIXTURE_COUNT),
        key=lambda week: (-fixtures_by_event.get(week, 0), week),
    )

    if squad_floor_value:
        # Worst week for this fifteen: a blank, usually. The chip replaces them
        # for one week, so it is worth most exactly where they are worth least.
        worst = min(weeks, key=lambda week: (squad_floor_value.get(week, 0.0), week))
        plan[worst] = "free_hit"
    elif doubles:
        plan[doubles[0]] = "free_hit"

    if squad_floor_value:
        boostable = [week for week in weeks if week not in plan]
        if boostable:
            best_floor = max(boostable, key=lambda week: (squad_floor_value.get(week, 0.0), -week))
            if squad_floor_value.get(best_floor, 0.0) > 0.0:
                plan[best_floor] = "bench_boost"
    elif len(doubles) > 1:
        plan[doubles[1]] = "bench_boost"

    free = [week for week in weeks if week not in plan]
    if free:
        best = max(free, key=lambda week: (star_fixture_value.get(week, 0.0), -week))
        if star_fixture_value.get(best, 0.0) > 0.0:
            plan[best] = "triple_captain"

    for half_weeks in (
        [week for week in weeks if week < _SECOND_HALF_FIRST_EVENT],
        [week for week in weeks if week >= _SECOND_HALF_FIRST_EVENT],
    ):
        open_weeks = [week for week in half_weeks if week not in plan]
        if not open_weeks:
            continue
        # The worst remaining week in the half. A rebuild is permanent, so it
        # goes before a bad run rather than on the single worst afternoon --
        # which the free hit has already taken.
        #
        # It was `rng.choice`: a chip placed by a coin toss, which is not a
        # decision at all and made two runs of the same season disagree about a
        # quarter of the chip budget.
        if squad_floor_value:
            chosen = min(
                open_weeks,
                key=lambda week: (squad_floor_value.get(week, 0.0), week),
            )
        else:
            chosen = rng.choice(open_weeks)
        plan[chosen] = "wildcard"

    return plan
