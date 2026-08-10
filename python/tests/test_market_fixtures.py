"""A bookmaker's match price, read as the fixture multipliers the routes take.

`ingest-odds` has been writing this artifact for four seasons and nothing read
it. Clean sheets and goals conceded are about a sixth of every point FPL
awards, they are the two routes a match market prices directly, and the fitted
strength they came from is a shrunk season-long ratio that cannot know who is
injured this week.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fpl_andres.backtesting.fixtures import (
    market_baseline,
    market_route_adjustment,
)
from fpl_andres.models.fixture_odds import ClubMatchOdds


def _view(
    club: str,
    scores: float,
    concedes: float,
    clean_sheet: float,
) -> ClubMatchOdds:
    return ClubMatchOdds(
        club=club,
        opponent="XXX",
        home=True,
        kickoff=datetime(2026, 8, 15, 19, tzinfo=UTC),
        expected_goals=scores,
        opponent_expected_goals=concedes,
        clean_sheet=clean_sheet,
        draw_residual=0.0,
    )


#: A round of six club views: two easy fixtures, two hard, two average.
ROUND = [
    _view("ARS", 2.4, 0.6, 0.55),
    _view("BOU", 0.6, 2.4, 0.09),
    _view("MCI", 2.0, 1.0, 0.37),
    _view("EVE", 1.0, 2.0, 0.14),
    _view("BHA", 1.5, 1.5, 0.22),
    _view("WOL", 1.5, 1.5, 0.22),
]


class TestTheAverageFixture:
    """A market clean sheet is a probability and a route takes a multiplier.

    Swapping one for the other needs a denominator, and taking it from the
    priced fixtures themselves is what makes a market rung mean the same thing
    as a fitted one: both are this fixture over the average fixture.
    """

    def test_the_baseline_is_the_mean_of_what_was_priced(self) -> None:
        baseline = market_baseline(ROUND)
        assert baseline is not None

        assert baseline.goals_per_side == pytest.approx(1.5)
        assert baseline.clean_sheet == pytest.approx((0.55 + 0.09 + 0.37 + 0.14 + 0.22 + 0.22) / 6)

    def test_a_fixture_at_the_average_moves_nothing(self) -> None:
        baseline = market_baseline(ROUND)
        assert baseline is not None
        adjustment = market_route_adjustment(_view("BHA", 1.5, 1.5, baseline.clean_sheet), baseline)

        assert adjustment.attacking == pytest.approx(1.0)
        assert adjustment.conceding == pytest.approx(1.0)
        assert adjustment.clean_sheet == pytest.approx(1.0)

    def test_nothing_priced_has_no_average(self) -> None:
        """Between seasons, and any week the ingest has not run."""
        assert market_baseline([]) is None

    def test_a_round_that_prices_no_goals_is_refused(self) -> None:
        assert market_baseline([_view("ARS", 0.0, 0.0, 0.0)]) is None


class TestWhatTheMarketSaysAboutAFixture:
    def _adjust(self, view: ClubMatchOdds):
        baseline = market_baseline(ROUND)
        assert baseline is not None
        return market_route_adjustment(view, baseline)

    def test_facing_a_poor_attack_lifts_the_clean_sheet(self) -> None:
        assert self._adjust(ROUND[0]).clean_sheet > 1.0

    def test_facing_a_strong_attack_suppresses_it(self) -> None:
        assert self._adjust(ROUND[1]).clean_sheet < 1.0

    def test_conceding_and_the_clean_sheet_move_opposite_ways(self) -> None:
        easy = self._adjust(ROUND[0])
        hard = self._adjust(ROUND[1])

        assert easy.conceding < hard.conceding
        assert easy.clean_sheet > hard.clean_sheet

    def test_a_side_under_pressure_makes_more_saves(self) -> None:
        """The one route a match market cannot price, taken off the pressure."""
        assert self._adjust(ROUND[1]).saves == pytest.approx(self._adjust(ROUND[1]).conceding)
        assert self._adjust(ROUND[1]).saves > self._adjust(ROUND[0]).saves

    def test_defensive_contribution_moves_half_as_far_as_conceding(self) -> None:
        hard = self._adjust(ROUND[1])

        assert hard.defensive_contribution == pytest.approx(1.0 + (hard.conceding - 1.0) * 0.5)

    def test_an_extreme_price_is_bounded_like_a_fitted_one(self) -> None:
        """A book pricing a rout must not produce a multiplier no route can hold."""
        adjustment = self._adjust(_view("ARS", 9.0, 0.01, 0.99))

        assert adjustment.attacking <= 2.2
        assert adjustment.conceding >= 0.4
        assert adjustment.clean_sheet <= 2.2
