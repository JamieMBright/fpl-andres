"""What a bench place is actually worth.

A substitute scores only when a starter records no minutes and the auto-sub
fires. That makes his worth the chance he is needed, which depends on the eleven
in front of him — not a flat weight applied equally to the first substitute and
the fourth.
"""

from __future__ import annotations

import pytest

from fpl_andres.planning.opening import bench_weights
from fpl_andres.simulation.squad import Candidate


def _player(element_id: int, position: int) -> Candidate:
    return Candidate(
        element_id=element_id,
        element_code=element_id + 1000,
        position=position,
        team_id=1 + element_id % 20,
        price_tenths=50,
        web_name=f"P{element_id}",
    )


def _eleven(appear: float) -> tuple[list[Candidate], dict[int, float]]:
    starters = [_player(1, 1)] + [_player(index, 3) for index in range(2, 12)]
    return starters, {player.element_id: appear for player in starters}


BENCH = [_player(20, 1), _player(21, 3), _player(22, 3), _player(23, 3)]


def test_an_ever_present_eleven_makes_the_bench_worthless() -> None:
    starters, appear = _eleven(1.0)

    assert bench_weights(starters, BENCH, appear) == [0.0, 0.0, 0.0, 0.0]


def test_the_substitutes_are_worth_less_the_further_down_they_sit() -> None:
    starters, appear = _eleven(0.9)

    weights = bench_weights(starters, BENCH, appear)
    outfield = weights[1:]

    assert outfield[0] > outfield[1] > outfield[2]


def test_the_first_substitute_is_the_chance_anyone_blanks() -> None:
    starters, appear = _eleven(0.9)

    weights = bench_weights(starters, BENCH, appear)

    # Ten outfield starters, each blanking one time in ten.
    assert weights[1] == pytest.approx(1 - 0.9**10)


def test_the_reserve_keeper_only_covers_the_keeper() -> None:
    starters, appear = _eleven(0.9)
    appear[1] = 0.5

    weights = bench_weights(starters, BENCH, appear)

    # The one who started is out half the time, and no outfielder can cover him.
    assert weights[0] == pytest.approx(0.5)


def test_a_fully_fit_keeper_makes_his_understudy_worth_nothing() -> None:
    starters, appear = _eleven(0.9)
    appear[1] = 1.0

    assert bench_weights(starters, BENCH, appear)[0] == pytest.approx(0.0)


def test_a_player_with_no_published_chance_is_treated_as_missing() -> None:
    # Not as fit. An absent record is a gap in the evidence, and the bench is
    # what covers a gap.
    starters, _ = _eleven(1.0)

    weights = bench_weights(starters, BENCH, {})

    assert weights[0] == pytest.approx(1.0)
    assert weights[1] == pytest.approx(1.0)


def test_the_weights_never_exceed_a_starting_place() -> None:
    starters, appear = _eleven(0.55)

    assert all(0.0 <= weight <= 1.0 for weight in bench_weights(starters, BENCH, appear))
