"""Two prices for the same quantity have to agree before either is published.

A club's expected goals is the sum of what its players are expected to score.
The team book says one number and the anytime-scorer market says another, and
on the 2026-08-20 artifact they disagreed by a median factor of 2.48 with every
club in the same direction. That is not noise: a complete team book can have its
margin removed and a one-sided player market cannot, so the player side is
inflated by construction.

These pin the reconciliation and the probability identities that would have
caught the inflation on the day it appeared.
"""

from __future__ import annotations

import math

import pytest

from fpl_andres.adapters.the_odds_api import read_event
from fpl_andres.models.market_routes import (
    MarketRoutesError,
    implied_events,
    reconcile_to_team_total,
)


def test_player_rates_are_fitted_onto_the_team_book() -> None:
    probabilities = {1: 0.6, 2: 0.4, 3: 0.2}
    reconciled, mismatch = reconcile_to_team_total(probabilities, 0.8, club="ARS")

    assert sum(reconciled.values()) == pytest.approx(0.8)
    assert mismatch.exponent > 1.0
    assert mismatch.quoted_players == 3
    assert mismatch.player_events > mismatch.team_events


def test_the_longshot_gives_up_more_than_the_favourite() -> None:
    """A book earns most of its margin on the long prices.

    A flat rescale takes the same fraction off every player, which leaves the
    favourite far too cheap. Measured on Manchester City that put Haaland at a
    fifth of his side's goals.
    """
    probabilities = {1: 0.6, 2: 0.1}
    reconciled, _ = reconcile_to_team_total(probabilities, 0.5, club="MCI")

    favourite_kept = reconciled[1] / implied_events(0.6)
    longshot_kept = reconciled[2] / implied_events(0.1)
    assert favourite_kept > longshot_kept


def test_reconciliation_keeps_the_order_the_market_priced() -> None:
    probabilities = {1: 0.6, 2: 0.4, 3: 0.2}
    reconciled, _ = reconcile_to_team_total(probabilities, 0.8, club="ARS")

    assert reconciled[1] > reconciled[2] > reconciled[3]


def test_a_club_with_no_team_price_keeps_what_it_was_quoted() -> None:
    probabilities = {1: 0.6, 2: 0.4}
    reconciled, mismatch = reconcile_to_team_total(probabilities, 0.0, club="COV")

    assert reconciled == {key: implied_events(value) for key, value in probabilities.items()}
    assert mismatch.exponent == 1.0


def test_a_club_with_no_quoted_players_is_not_a_division_by_zero() -> None:
    reconciled, mismatch = reconcile_to_team_total({}, 1.4, club="HUL")

    assert reconciled == {}
    assert mismatch.exponent == 1.0


def test_an_unreachable_total_leaves_the_prices_alone() -> None:
    # No exponent can lift two short prices to twenty goals, so the fit is
    # abandoned rather than driven to the edge of its bracket.
    reconciled, mismatch = reconcile_to_team_total({1: 0.6, 2: 0.4}, 20.0, club="ARS")

    assert mismatch.exponent == 1.0
    assert reconciled[1] == pytest.approx(implied_events(0.6))


def test_impossible_probabilities_are_refused_rather_than_fitted() -> None:
    with pytest.raises(MarketRoutesError):
        reconcile_to_team_total({1: 1.0}, 1.0, club="ARS")
    with pytest.raises(MarketRoutesError):
        reconcile_to_team_total({1: 0.2}, -1.0, club="ARS")


def _book(key: str, market: str, outcomes: list[dict[str, object]]) -> dict[str, object]:
    return {"key": key, "markets": [{"key": market, "outcomes": outcomes}]}


def _event(*bookmakers: dict[str, object]) -> dict[str, object]:
    return {
        "home_team": "Arsenal",
        "away_team": "Coventry City",
        "commence_time": "2026-08-21T19:00:00Z",
        "bookmakers": list(bookmakers),
    }


def test_two_selections_for_one_player_are_not_read_as_a_complete_book() -> None:
    """The bug that put twenty-one players above their own anytime price.

    A book listing the same footballer twice in one market is quoting the same
    thing twice, not quoting a yes and its no. De-vigging the pair reads one as
    the complement of the other and inflates both.
    """
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_first_goal_scorer",
                [
                    {"description": "Kai Havertz", "name": "Kai Havertz", "price": 7.0},
                    {"description": "Kai Havertz", "name": "Kai Havertz", "price": 8.0},
                ],
            )
        )
    )

    assert len(rows) == 1
    # The median implied of 7.0 and 8.0, not a devigged 0.5-ish pair.
    assert rows[0].first_goal == pytest.approx(1.0 / 7.5, abs=1e-6)
    assert rows[0].first_goal < 0.2


def test_a_genuine_yes_and_no_pair_is_still_devigged() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_goal_scorer_anytime",
                [
                    {"description": "Kai Havertz", "name": "Yes", "price": 1.9},
                    {"description": "Kai Havertz", "name": "No", "price": 1.9},
                ],
            )
        )
    )

    assert rows[0].anytime_goal == pytest.approx(0.5, abs=1e-6)


def test_first_scorer_never_exceeds_anytime_scorer() -> None:
    """A hard identity: first is a subset of anytime, so it cannot be larger."""
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_goal_scorer_anytime",
                [{"description": "Kai Havertz", "name": "Yes", "price": 2.5}],
            ),
            _book(
                "bet365",
                "player_first_goal_scorer",
                [
                    {"description": "Kai Havertz", "name": "Kai Havertz", "price": 7.0},
                    {"description": "Kai Havertz", "name": "Kai Havertz", "price": 8.0},
                ],
            ),
        )
    )

    row = rows[0]
    assert row.anytime_goal is not None and row.first_goal is not None
    assert row.first_goal <= row.anytime_goal


def test_the_poisson_inversion_round_trips() -> None:
    for probability in (0.01, 0.25, 0.5, 0.75, 0.95):
        assert 1.0 - math.exp(-implied_events(probability)) == pytest.approx(probability)
