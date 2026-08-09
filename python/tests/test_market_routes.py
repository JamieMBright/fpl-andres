"""Reading a bookmaker's player price as an expectation, not a probability.

FPL pays per goal; a book prices the chance of at least one. The inversion
between them is an assumption, and these pin both the assumption and what it
refuses to do.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.
"""

from __future__ import annotations

import math

import pytest

from fpl_andres.models.market_routes import (
    MarketRoutesError,
    blend_rate,
    implied_events,
    market_attack,
)


class TestTheInversion:
    def test_a_shorter_price_expects_more_goals(self) -> None:
        assert implied_events(0.5) > implied_events(0.25)

    def test_a_price_of_nothing_expects_nothing(self) -> None:
        assert implied_events(0.0) == 0.0

    def test_the_rate_reproduces_the_price_it_came_from(self) -> None:
        """The round trip is the whole claim: P = 1 - exp(-lambda)."""
        for probability in (0.05, 0.2, 0.37, 0.61, 0.9):
            assert 1.0 - math.exp(-implied_events(probability)) == pytest.approx(probability)

    def test_the_rate_exceeds_the_price_because_a_player_can_score_twice(self) -> None:
        """Taking the price as the expectation undercounts every brace."""
        assert implied_events(0.4) > 0.4

    def test_a_certainty_is_refused_rather_than_clamped(self) -> None:
        """It inverts to an infinite rate, and no book prices one."""
        with pytest.raises(MarketRoutesError, match=r"\[0, 1\)"):
            implied_events(1.0)

    def test_a_negative_chance_is_refused(self) -> None:
        with pytest.raises(MarketRoutesError):
            implied_events(-0.01)


class TestPricingTheAttackingRoute:
    def test_both_prices_are_read_into_one_expectation(self) -> None:
        attack = market_attack(anytime_goal=0.3, anytime_assist=0.15)
        assert attack is not None

        assert attack.goals == pytest.approx(implied_events(0.3))
        assert attack.assists == pytest.approx(implied_events(0.15))

    def test_a_scorer_market_alone_still_counts(self) -> None:
        """Books open anytime-scorer on every fixture and assists on rather fewer."""
        attack = market_attack(anytime_goal=0.3, anytime_assist=None)
        assert attack is not None

        assert attack.goals == pytest.approx(implied_events(0.3))
        assert attack.assists is None

    def test_an_assist_market_alone_still_counts(self) -> None:
        attack = market_attack(anytime_goal=None, anytime_assist=0.15)
        assert attack is not None

        assert attack.goals is None

    def test_a_player_the_book_ignored_produces_nothing(self) -> None:
        """Not the same as a player priced at nothing; there is no view to blend."""
        assert market_attack(anytime_goal=None, anytime_assist=None) is None


class TestBlendingWithTheRecord:
    def test_no_weight_leaves_the_record_untouched(self) -> None:
        assert blend_rate(1.4, 2.2, 0.0) == pytest.approx(1.4)

    def test_full_weight_hands_the_route_to_the_market(self) -> None:
        assert blend_rate(1.4, 2.2, 1.0) == pytest.approx(2.2)

    def test_a_share_lands_between_the_two(self) -> None:
        assert blend_rate(1.0, 2.0, 0.35) == pytest.approx(1.35)

    def test_a_weight_outside_a_share_is_refused(self) -> None:
        """A weight above one would extrapolate past the market itself."""
        with pytest.raises(MarketRoutesError, match="0 to 1"):
            blend_rate(1.0, 2.0, 1.5)

    def test_a_negative_rate_is_refused_rather_than_averaged(self) -> None:
        with pytest.raises(MarketRoutesError, match="negative"):
            blend_rate(-1.0, 2.0, 0.35)
