"""Chip timing: dated from the fixture list, not guessed at week by week."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from fpl_andres.simulation.chips import (
    ChipRulesUnavailable,
    ChipState,
    chip_rules_for,
    plan_chips,
)


def plan(
    fixtures: dict[int, int],
    star: dict[int, float],
    *,
    start: int = 7,
    last: int = 38,
    seed: int = 1,
) -> dict[int, str]:
    return plan_chips(
        fixtures_by_event=fixtures,
        star_fixture_value=star,
        from_gameweek=start,
        last_event=last,
        rng=random.Random(seed),
    )


def test_a_second_wildcard_arrives_in_the_second_half() -> None:
    state = ChipState()
    state.record("wildcard", 8)

    assert not state.available("wildcard", 12)
    assert state.available("wildcard", 25)


def test_a_wildcard_cannot_be_played_twice_in_the_same_half() -> None:
    state = ChipState()
    state.record("wildcard", 25)

    assert not state.available("wildcard", 30)


def test_every_other_chip_is_once_a_season() -> None:
    state = ChipState()
    state.record("triple_captain", 12)

    assert not state.available("triple_captain", 30)
    assert state.available("bench_boost", 30)


def test_2025_26_grants_a_second_set_of_every_chip() -> None:
    """The allowance changed, and a backtest on the old one plays three short.

    Until 2024-25 a season granted one free hit, bench boost and triple captain
    between August and May. From 2025-26 it grants a full set in each half.
    """
    old = chip_rules_for("2024-25")
    new = chip_rules_for("2025-26")

    assert old.sets == 1
    assert new.sets == 2
    for chip in ("free_hit", "bench_boost", "triple_captain"):
        assert old.season_allowance(chip) == 1
        assert new.season_allowance(chip) == 2
    # The second wildcard predates the second set, so it is two under both.
    assert old.season_allowance("wildcard") == 2
    assert new.season_allowance("wildcard") == 2


def test_a_second_set_chip_is_still_one_per_half() -> None:
    state = ChipState(rules=chip_rules_for("2025-26"))
    state.record("triple_captain", 12)

    assert not state.available("triple_captain", 15)
    # The first set expires at the boundary; the second is a fresh grant.
    assert state.available("triple_captain", 25)

    state.record("triple_captain", 25)
    assert not state.available("triple_captain", 30)


def test_a_season_with_no_recorded_allowance_fails_rather_than_assuming_one() -> None:
    """Guessing here silently changes what a simulated season may do."""
    with pytest.raises(ChipRulesUnavailable):
        chip_rules_for("2031-32")


def test_two_sets_date_a_chip_in_each_half() -> None:
    fixtures = {event: 10 for event in range(1, 39)}
    floor = {event: 5.0 for event in range(1, 39)}
    star = {event: 3.0 for event in range(1, 39)}

    plan = plan_chips(
        fixtures_by_event=fixtures,
        star_fixture_value=star,
        from_gameweek=1,
        last_event=38,
        rng=random.Random(1),
        squad_floor_value=floor,
        rules=chip_rules_for("2025-26"),
    )

    counts = Counter(plan.values())
    assert counts["free_hit"] == 2
    assert counts["bench_boost"] == 2
    assert counts["triple_captain"] == 2
    assert counts["wildcard"] == 2
    for chip in ("free_hit", "bench_boost", "triple_captain", "wildcard"):
        halves = {1 if week < 20 else 2 for week, name in plan.items() if name == chip}
        assert halves == {1, 2}, f"{chip} was not dated once in each half"


def test_one_set_still_dates_three_chips_once_and_the_wildcard_twice() -> None:
    fixtures = {event: 10 for event in range(1, 39)}
    floor = {event: 5.0 for event in range(1, 39)}
    star = {event: 3.0 for event in range(1, 39)}

    plan = plan_chips(
        fixtures_by_event=fixtures,
        star_fixture_value=star,
        from_gameweek=1,
        last_event=38,
        rng=random.Random(1),
        squad_floor_value=floor,
        rules=chip_rules_for("2024-25"),
    )

    counts = Counter(plan.values())
    assert counts["free_hit"] == 1
    assert counts["bench_boost"] == 1
    assert counts["triple_captain"] == 1
    assert counts["wildcard"] == 2


def test_the_free_hit_takes_the_largest_double_gameweek() -> None:
    fixtures = {week: 10 for week in range(7, 39)}
    fixtures[25] = 16
    fixtures[31] = 13

    dated = plan(fixtures, {})

    assert dated[25] == "free_hit"


def test_the_bench_boost_takes_the_next_largest_double() -> None:
    fixtures = {week: 10 for week in range(7, 39)}
    fixtures[25] = 16
    fixtures[31] = 13

    dated = plan(fixtures, {})

    assert dated[31] == "bench_boost"


def test_a_season_with_no_double_dates_neither() -> None:
    dated = plan({week: 10 for week in range(7, 39)}, {})

    assert "free_hit" not in dated.values()
    assert "bench_boost" not in dated.values()


def test_the_triple_captain_follows_the_best_home_fixture() -> None:
    fixtures = {week: 10 for week in range(7, 39)}
    star = {week: 0.8 for week in range(7, 39)}
    star[22] = 1.9

    dated = plan(fixtures, star)

    assert dated[22] == "triple_captain"


def test_a_star_with_no_home_fixture_worth_taking_leaves_it_undated() -> None:
    dated = plan({week: 10 for week in range(7, 39)}, {week: 0.0 for week in range(7, 39)})

    assert "triple_captain" not in dated.values()


def test_one_wildcard_is_dated_in_each_half() -> None:
    dated = plan({week: 10 for week in range(7, 39)}, {})

    weeks = [week for week, chip in dated.items() if chip == "wildcard"]
    assert len(weeks) == 2
    assert min(weeks) < 20 <= max(weeks)


def test_no_gameweek_is_given_two_chips() -> None:
    fixtures = {week: 10 for week in range(7, 39)}
    fixtures[25] = 16
    fixtures[31] = 13
    star = {week: 1.0 for week in range(7, 39)}

    dated = plan(fixtures, star)

    assert len(dated) == len(set(dated))
