"""Effective points and the points-to-rank mapping."""

from __future__ import annotations

import pytest

from fpl_andres.planning.effective import RankModel, effective_points

HAALAND = 1
DIFFERENTIAL = 2

FIELD = RankModel(mean_points=50.0, standard_deviation=15.0, field_size=11_000_000)


def test_an_average_score_finishes_mid_table() -> None:
    assert FIELD.share_below(50.0) == pytest.approx(0.5)
    assert FIELD.rank_of(50.0) == pytest.approx(5_500_000, rel=1e-6)


def test_a_better_score_ranks_higher() -> None:
    assert FIELD.rank_of(80.0) < FIELD.rank_of(50.0)


def test_the_same_points_are_worth_fewer_places_further_up() -> None:
    # Ten points from average moves millions; ten from an elite score moves far
    # fewer, because the field thins out.
    near_average = FIELD.places_gained(50.0, 10.0)
    already_elite = FIELD.places_gained(110.0, 10.0)

    assert near_average > already_elite


def test_a_field_with_no_spread_is_refused() -> None:
    with pytest.raises(ValueError, match="no spread"):
        RankModel(mean_points=50.0, standard_deviation=0.0, field_size=100)


def test_a_field_of_one_is_refused() -> None:
    with pytest.raises(ValueError, match="no ranks to climb"):
        RankModel(mean_points=50.0, standard_deviation=10.0, field_size=1)


def test_owning_what_everyone_owns_moves_nobody() -> None:
    ranked = effective_points({HAALAND: 12.0}, {HAALAND: 1.0}, held=[HAALAND])

    assert ranked[0].swing == pytest.approx(0.0)


def test_missing_what_everyone_owns_costs_his_whole_return() -> None:
    ranked = effective_points({HAALAND: 12.0}, {HAALAND: 1.0}, held=[])

    assert ranked[0].swing == pytest.approx(-12.0)
    assert ranked[0].cover == pytest.approx(12.0)


def test_a_captained_template_player_costs_more_than_his_score() -> None:
    # Effective ownership above one: owned by all, captained by most.
    ranked = effective_points({HAALAND: 10.0}, {HAALAND: 1.8}, held=[])

    assert ranked[0].swing == pytest.approx(-18.0)


def test_a_differential_pays_almost_his_whole_score() -> None:
    ranked = effective_points({DIFFERENTIAL: 8.0}, {DIFFERENTIAL: 0.02}, held=[DIFFERENTIAL])

    assert ranked[0].swing == pytest.approx(7.84)
    assert ranked[0].upside == pytest.approx(7.84)


def test_a_player_the_field_does_not_list_is_treated_as_unowned() -> None:
    ranked = effective_points({DIFFERENTIAL: 6.0}, {}, held=[DIFFERENTIAL])

    assert ranked[0].effective_ownership == 0.0
    assert ranked[0].swing == pytest.approx(6.0)


def test_candidates_are_ordered_by_what_they_do_to_your_position() -> None:
    ranked = effective_points(
        {HAALAND: 12.0, DIFFERENTIAL: 8.0},
        {HAALAND: 1.0, DIFFERENTIAL: 0.05},
        held=[DIFFERENTIAL],
    )

    # The differential you own beats the template you are missing.
    assert [entry.element_id for entry in ranked] == [DIFFERENTIAL, HAALAND]


def test_a_swing_converts_into_places_on_the_table() -> None:
    ranked = effective_points({DIFFERENTIAL: 8.0}, {DIFFERENTIAL: 0.05}, held=[DIFFERENTIAL])

    places = ranked[0].places(FIELD, current_points=50.0)

    assert places > 0
