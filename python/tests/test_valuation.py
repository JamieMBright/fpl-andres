"""Selling price, bank and team value."""

from __future__ import annotations

import pytest

from fpl_andres.simulation.valuation import Holding, Portfolio, selling_price

PRICES = {1: 74, 2: 50, 3: 120, 4: 45}


def test_half_the_profit_is_kept_rounded_down() -> None:
    # Bought at 7.0, now 7.4: profit of 0.4, half of it is 0.2.
    assert selling_price(70, 74) == 72


def test_an_odd_profit_rounds_down_not_up() -> None:
    # Bought at 7.0, now 7.3: half of 0.3 is 0.15, which rounds to 0.1.
    assert selling_price(70, 73) == 71


def test_a_single_tenth_of_profit_is_not_bankable() -> None:
    assert selling_price(70, 71) == 70


def test_a_loss_is_taken_in_full() -> None:
    assert selling_price(70, 64) == 64


def test_an_unchanged_price_sells_for_itself() -> None:
    assert selling_price(70, 70) == 70


def test_a_zero_purchase_price_is_refused_rather_than_divided_by() -> None:
    with pytest.raises(ValueError, match="purchase price must be positive"):
        selling_price(0, 70)


def test_paper_value_exceeds_sale_value_once_a_player_has_risen() -> None:
    portfolio = Portfolio(
        holdings={1: Holding(1, 70), 2: Holding(2, 50)},
        bank_tenths=0,
    )

    assert portfolio.paper_value(PRICES) == 124
    assert portfolio.sale_value(PRICES) == 122


def test_team_value_counts_the_bank() -> None:
    portfolio = Portfolio(holdings={1: Holding(1, 70)}, bank_tenths=15)

    assert portfolio.team_value(PRICES) == 72 + 15


def test_an_opening_squad_banks_whatever_it_did_not_spend() -> None:
    portfolio = Portfolio.opening([1, 2], PRICES, budget_tenths=1000)

    assert portfolio.bank_tenths == 1000 - (74 + 50)
    assert portfolio.holdings[1].purchase_tenths == 74


def test_an_unaffordable_opening_squad_is_refused() -> None:
    with pytest.raises(ValueError, match="more than the budget"):
        Portfolio.opening([1, 3], PRICES, budget_tenths=100)


def test_affordability_uses_the_sale_price_not_the_quoted_price() -> None:
    portfolio = Portfolio(holdings={1: Holding(1, 70)}, bank_tenths=0)

    # Quoted at 7.4 but only sells for 7.2, so 7.4 is not affordable.
    assert portfolio.affordable(1, PRICES) == 72


def test_a_transfer_settles_the_difference_in_cash() -> None:
    portfolio = Portfolio(holdings={1: Holding(1, 70)}, bank_tenths=10)

    portfolio.transfer(1, 2, PRICES)

    # Sold for 72, bought at 50, so the bank gains 22.
    assert portfolio.bank_tenths == 32
    assert 1 not in portfolio.holdings
    assert portfolio.holdings[2].purchase_tenths == 50


def test_a_new_player_is_held_at_the_price_actually_paid() -> None:
    portfolio = Portfolio(holdings={1: Holding(1, 70)}, bank_tenths=100)

    portfolio.transfer(1, 3, PRICES)

    # He now rises further; only profit from 12.0 onward is ours.
    assert portfolio.holdings[3].sells_for({3: 124}) == 122


def test_an_unaffordable_transfer_is_refused_rather_than_overdrawn() -> None:
    portfolio = Portfolio(holdings={1: Holding(1, 70)}, bank_tenths=0)

    with pytest.raises(ValueError, match="cannot afford"):
        portfolio.transfer(1, 3, PRICES)


def test_selling_a_player_you_do_not_own_is_an_error() -> None:
    portfolio = Portfolio(holdings={1: Holding(1, 70)}, bank_tenths=0)

    with pytest.raises(KeyError):
        portfolio.transfer(9, 2, PRICES)


def test_buying_a_player_you_already_own_is_an_error() -> None:
    portfolio = Portfolio(holdings={1: Holding(1, 70), 2: Holding(2, 50)}, bank_tenths=0)

    with pytest.raises(ValueError, match="already held"):
        portfolio.transfer(1, 2, PRICES)
