"""Chip timing: dated from the fixture list, not guessed at week by week."""

from __future__ import annotations

import random

from fpl_andres.simulation.chips import ChipState, plan_chips


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
