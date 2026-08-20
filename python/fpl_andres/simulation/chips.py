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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "ChipName",
    "ChipRules",
    "ChipState",
    "chip_rules_for",
    "plan_chips",
]

ChipName = Literal["wildcard", "free_hit", "triple_captain", "bench_boost"]

CHIP_NAMES: tuple[ChipName, ...] = (
    "wildcard",
    "free_hit",
    "triple_captain",
    "bench_boost",
)

# FPL splits the season in two for chip purposes. The boundary is a rule of the
# game rather than a preference, so it is named rather than tuned.
_SECOND_HALF_FIRST_EVENT = 20
_FINAL_EVENT = 38
_NORMAL_FIXTURE_COUNT = 10


@dataclass(frozen=True)
class ChipRules:
    """How many of each chip a season grants, and where its halves divide.

    Not a constant. Until 2025-26 a season granted one wildcard per half and a
    single free hit, bench boost and triple captain for the whole year. From
    2025-26 the game grants a full set of all four in each half: eight chips,
    the first set expiring at the boundary.

    A backtest that plays the old allowance through a new season leaves three
    chips on the table against every real manager it is compared to, and one
    that plays the new allowance through an old season is cheating. Neither is
    recoverable from the corpus, which stores results and not rules, so the
    allowance is named per season and an unnamed season fails rather than
    defaulting to either.
    """

    #: Sets of the four chips granted across the season. One set still means
    #: two wildcards, because the second wildcard predates the second set.
    sets: int
    second_half_first_event: int
    source_reference: str

    def allowance(self, chip: ChipName, half: int) -> int:
        """How many of `chip` may be played in `half`.

        One under every allowance the game has used: what changes between them
        is how many the season grants overall, not how many fit in a half.
        """
        return 1

    def season_allowance(self, chip: ChipName) -> int:
        # The second wildcard predates the second set of everything else.
        if chip == "wildcard":
            return 2
        return self.sets


#: Published in the game's own rules each summer. `ChipWindow` reads the same
#: thing from the live bootstrap for the current season; the corpus carries no
#: bootstrap, so completed seasons are named here.
CHIP_RULES_BY_SEASON: dict[str, ChipRules] = {
    season: ChipRules(
        sets=1,
        second_half_first_event=_SECOND_HALF_FIRST_EVENT,
        source_reference="https://fantasy.premierleague.com/help/rules",
    )
    for season in ("2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25")
}
CHIP_RULES_BY_SEASON.update(
    {
        season: ChipRules(
            sets=2,
            second_half_first_event=_SECOND_HALF_FIRST_EVENT,
            source_reference="https://www.premierleague.com/news/4process/fantasy-premier-league-2025-26-chips",
        )
        for season in ("2025-26", "2026-27")
    }
)


class ChipRulesUnavailable(LookupError):
    """Raised when a season's chip allowance has not been recorded."""


def chip_rules_for(season: str) -> ChipRules:
    """The chip allowance for one season, or a visible failure.

    Guessing here would silently change what a simulated season is allowed to
    do, which is the one thing a backtest is not permitted to be vague about.
    """
    try:
        return CHIP_RULES_BY_SEASON[season]
    except KeyError:
        raise ChipRulesUnavailable(
            f"no chip allowance recorded for {season}; add it to "
            "CHIP_RULES_BY_SEASON with the rule's source rather than assuming one"
        ) from None


_LEGACY_RULES = ChipRules(
    sets=1,
    second_half_first_event=_SECOND_HALF_FIRST_EVENT,
    source_reference="https://fantasy.premierleague.com/help/rules",
)


@dataclass
class ChipState:
    """Which chips remain, and when each was played."""

    rules: ChipRules = _LEGACY_RULES
    played: dict[ChipName, int] = field(default_factory=dict)
    #: `(chip, half)` -> count. Tracks every chip by half, because from 2025-26
    #: every chip is granted per half rather than only the wildcard.
    used_by_half: dict[tuple[ChipName, int], int] = field(default_factory=dict)

    def half_of(self, gameweek: int) -> int:
        return 1 if gameweek < self.rules.second_half_first_event else 2

    def played_count(self, chip: ChipName) -> int:
        return sum(count for (name, _), count in self.used_by_half.items() if name == chip)

    def available(self, chip: ChipName, gameweek: int) -> bool:
        half = self.half_of(gameweek)
        if self.used_by_half.get((chip, half), 0) >= self.rules.allowance(chip, half):
            return False
        return self.played_count(chip) < self.rules.season_allowance(chip)

    def record(self, chip: ChipName, gameweek: int) -> None:
        half = self.half_of(gameweek)
        # The last week it was played, which is what a one-per-season chip
        # meant by this field before a season granted two of them.
        self.played[chip] = gameweek
        self.used_by_half[(chip, half)] = self.used_by_half.get((chip, half), 0) + 1


def plan_chips(
    *,
    fixtures_by_event: Mapping[int, int],
    star_fixture_value: Mapping[int, float],
    from_gameweek: int,
    last_event: int,
    rng: random.Random,
    squad_floor_value: Mapping[int, float] | None = None,
    rules: ChipRules = _LEGACY_RULES,
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
    boundary = rules.second_half_first_event
    halves = [
        [week for week in weeks if week < boundary],
        [week for week in weeks if week >= boundary],
    ]

    if rules.sets >= 2:
        # A set per half, each expiring at the boundary. Dated within its own
        # half rather than across the season, because a chip that cannot be
        # carried over has to take the best week it can still reach.
        for half_weeks in halves:
            _date_set(
                plan,
                half_weeks,
                fixtures_by_event=fixtures_by_event,
                star_fixture_value=star_fixture_value,
                squad_floor_value=squad_floor_value,
            )
    else:
        _date_set(
            plan,
            weeks,
            fixtures_by_event=fixtures_by_event,
            star_fixture_value=star_fixture_value,
            squad_floor_value=squad_floor_value,
        )

    # The wildcard is one per half under every allowance the game has used.
    for half_weeks in halves:
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


def _date_set(
    plan: dict[int, ChipName],
    weeks: Sequence[int],
    *,
    fixtures_by_event: Mapping[int, int],
    star_fixture_value: Mapping[int, float],
    squad_floor_value: Mapping[int, float] | None,
) -> None:
    """Date one free hit, bench boost and triple captain across `weeks`."""
    weeks = [week for week in weeks if week not in plan]
    if not weeks:
        return

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
