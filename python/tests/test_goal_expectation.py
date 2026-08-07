"""Recovering a goals distribution from 1X2 and over/under markets.

The clean sheet a manager is paid for is P(opponent scores nothing), and no free
feed sells a correct-score market. These tests pin the reconstruction that
stands in for one.
"""

from __future__ import annotations

import math

import pytest

from fpl_andres.models.goal_expectation import (
    fit_goal_expectation,
    score_probability,
    total_goals_mean,
)
from fpl_andres.models.odds import OddsUnavailable

# A strong home favourite: roughly 1.40 / 5.00 / 8.00 with goals expected.
FAVOURITE = ((1.40, 5.00, 8.00), (1.75, 2.10))


class TestTotalGoalsMean:
    def test_inverts_the_over_under_market_exactly(self) -> None:
        # Total goals is Poisson because the sum of independent Poissons is,
        # so this inversion is exact rather than fitted.
        mean = total_goals_mean(0.5)
        under = sum(math.exp(-mean) * mean**k / math.factorial(k) for k in range(3))
        assert under == pytest.approx(0.5, abs=1e-9)

    def test_a_higher_over_price_means_more_goals(self) -> None:
        assert total_goals_mean(0.7) > total_goals_mean(0.4)

    def test_refuses_a_probability_outside_the_unit_interval(self) -> None:
        with pytest.raises(OddsUnavailable):
            total_goals_mean(1.0)

    def test_refuses_a_whole_goal_line_which_can_push(self) -> None:
        with pytest.raises(OddsUnavailable):
            total_goals_mean(0.5, line=3.0)


class TestFitGoalExpectation:
    def test_gives_the_favourite_the_larger_share_of_the_goals(self) -> None:
        fit = fit_goal_expectation(*FAVOURITE)
        assert fit.home > fit.away
        assert fit.total == pytest.approx(fit.home + fit.away)

    def test_the_total_matches_the_over_under_market_it_was_given(self) -> None:
        fit = fit_goal_expectation(*FAVOURITE)
        assert total_goals_mean(0.5) > 0
        assert 2.0 < fit.total < 4.0

    def test_a_clean_sheet_is_the_opposing_mean_not_the_own_one(self) -> None:
        # The route that pays a defender is the opponent failing to score.
        fit = fit_goal_expectation(*FAVOURITE)
        assert fit.home_clean_sheet == pytest.approx(math.exp(-fit.away))
        assert fit.away_clean_sheet == pytest.approx(math.exp(-fit.home))
        assert fit.home_clean_sheet > fit.away_clean_sheet

    def test_a_level_market_splits_the_goals_evenly(self) -> None:
        fit = fit_goal_expectation((2.6, 3.3, 2.6), (1.9, 1.9))
        assert fit.home == pytest.approx(fit.away, abs=1e-6)
        assert fit.home_clean_sheet == pytest.approx(fit.away_clean_sheet, abs=1e-6)

    def test_reports_the_draw_error_rather_than_absorbing_it(self) -> None:
        # Independent Poisson under-prices draws. The residual is published so a
        # reader can see the size of the Dixon-Coles correction not applied.
        fit = fit_goal_expectation(*FAVOURITE)
        assert isinstance(fit.draw_residual, float)
        assert abs(fit.draw_residual) < 0.2

    def test_a_market_priced_for_arbitrage_is_refused(self) -> None:
        with pytest.raises(OddsUnavailable):
            fit_goal_expectation((10.0, 10.0, 10.0), (1.9, 1.9))

    def test_reconstructs_the_correct_score_market_the_feed_does_not_sell(
        self,
    ) -> None:
        fit = fit_goal_expectation(*FAVOURITE)
        grid = [score_probability(home, away, fit) for home in range(11) for away in range(11)]
        # Not exactly one: the grid is truncated at ten goals a side, and the
        # tail beyond it is real probability rather than rounding.
        assert sum(grid) == pytest.approx(1.0, abs=1e-4)
        # 1-0 to the favourite must beat 0-1 against him.
        assert score_probability(1, 0, fit) > score_probability(0, 1, fit)

    def test_a_negative_scoreline_is_refused(self) -> None:
        fit = fit_goal_expectation(*FAVOURITE)
        with pytest.raises(OddsUnavailable):
            score_probability(-1, 0, fit)
