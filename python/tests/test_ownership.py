"""Effective ownership and rank-relative swing."""

from __future__ import annotations

import pytest

from fpl_andres.planning.ownership import (
    effective_ownership,
    mandatory_players,
    swing,
)

HAALAND = 1
DIFFERENTIAL = 2
UNOWNED = 3


def field(managers: int, *, owning: int, captaining: int) -> tuple[list, list]:
    squads = [[HAALAND] if index < owning else [DIFFERENTIAL] for index in range(managers)]
    captains: list[int | None] = [
        HAALAND if index < captaining else None for index in range(managers)
    ]
    return squads, captains


def test_captaincy_counts_a_second_time() -> None:
    squads, captains = field(10, owning=5, captaining=2)

    ownership = effective_ownership(squads, captains)

    assert ownership[HAALAND].owned_share == 0.5
    assert ownership[HAALAND].captained_share == 0.2
    assert ownership[HAALAND].effective == pytest.approx(0.7)


def test_owning_what_everyone_owns_is_worth_nothing() -> None:
    squads, captains = field(10, owning=10, captaining=0)
    ownership = effective_ownership(squads, captains)

    held = swing({HAALAND: 8.0}, ownership, [HAALAND])
    mine = next(entry for entry in held if entry.element_id == HAALAND)

    assert mine.swing == pytest.approx(0.0)
    assert mine.is_hedge


def test_not_owning_what_everyone_owns_costs_his_full_return() -> None:
    squads, captains = field(10, owning=10, captaining=0)
    ownership = effective_ownership(squads, captains)

    without = swing({HAALAND: 8.0}, ownership, [])
    mine = next(entry for entry in without if entry.element_id == HAALAND)

    assert mine.swing == pytest.approx(-8.0)


def test_a_differential_pays_almost_his_whole_score() -> None:
    squads, captains = field(20, owning=20, captaining=0)
    ownership = effective_ownership(squads, captains)

    ranked = swing({UNOWNED: 6.0}, ownership, [UNOWNED])
    mine = next(entry for entry in ranked if entry.element_id == UNOWNED)

    assert mine.swing == pytest.approx(6.0)
    assert not mine.is_hedge


def test_a_captained_template_player_is_worse_to_miss_than_his_score() -> None:
    squads, captains = field(10, owning=10, captaining=8)
    ownership = effective_ownership(squads, captains)

    without = swing({HAALAND: 10.0}, ownership, [])
    mine = next(entry for entry in without if entry.element_id == HAALAND)

    # Effective ownership of 1.8 means missing him costs nearly double.
    assert mine.swing == pytest.approx(-18.0)


def test_a_heavily_owned_scorer_is_mandatory_and_a_rare_one_is_not() -> None:
    squads, captains = field(10, owning=9, captaining=5)
    ownership = effective_ownership(squads, captains)

    mandatory = mandatory_players({HAALAND: 8.0, DIFFERENTIAL: 8.0}, ownership, threshold=5.0)

    assert mandatory == [HAALAND]


def test_a_squad_without_a_captain_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="captain entry"):
        effective_ownership([[HAALAND]], [])


def test_an_empty_field_measures_nothing_rather_than_guessing() -> None:
    assert effective_ownership([], []) == {}
