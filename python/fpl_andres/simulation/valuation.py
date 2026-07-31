"""Squad value, bank, and what a player actually sells for.

FPL does not let you bank the whole of a price rise. A player who cost 7.0 and
now trades at 7.4 sells for 7.2: you keep half the profit, rounded down to the
nearest tenth. A player who has fallen sells for whatever he is now worth, with
the loss taken in full.

That asymmetry is the whole reason team value compounds slowly, and why a squad's
paper value and its sale value are different numbers. Modelling one as the other
overstates spending power all season, and by the run-in the error is large enough
to buy a player who was never affordable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

__all__ = [
    "Holding",
    "Portfolio",
    "selling_price",
]


def selling_price(purchase_tenths: int, current_tenths: int) -> int:
    """What FPL pays when this player is sold.

    Half of any profit, rounded down to the nearest tenth of a million. Losses
    are not softened: a fallen player sells for his current price.
    """
    if purchase_tenths <= 0:
        raise ValueError("purchase price must be positive")
    if current_tenths <= purchase_tenths:
        return current_tenths
    profit = current_tenths - purchase_tenths
    return purchase_tenths + profit // 2


@dataclass(frozen=True)
class Holding:
    """One player, at the price he was bought for."""

    element_id: int
    purchase_tenths: int

    def sells_for(self, prices: Mapping[int, int]) -> int:
        current = prices.get(self.element_id, self.purchase_tenths)
        return selling_price(self.purchase_tenths, current)


@dataclass
class Portfolio:
    """A squad's holdings and its cash, tracked in tenths of a million."""

    holdings: dict[int, Holding]
    bank_tenths: int

    @classmethod
    def opening(
        cls, element_ids: Iterable[int], prices: Mapping[int, int], budget_tenths: int
    ) -> Portfolio:
        holdings = {
            element_id: Holding(element_id, prices[element_id])
            for element_id in element_ids
            if element_id in prices
        }
        spent = sum(holding.purchase_tenths for holding in holdings.values())
        if spent > budget_tenths:
            raise ValueError("opening squad costs more than the budget allows")
        return cls(holdings=holdings, bank_tenths=budget_tenths - spent)

    def sale_value(self, prices: Mapping[int, int]) -> int:
        """What the squad would raise if every player were sold today."""
        return sum(holding.sells_for(prices) for holding in self.holdings.values())

    def paper_value(self, prices: Mapping[int, int]) -> int:
        """What the squad is quoted at. Always at least the sale value."""
        return sum(
            prices.get(element_id, holding.purchase_tenths)
            for element_id, holding in self.holdings.items()
        )

    def team_value(self, prices: Mapping[int, int]) -> int:
        """Sale value plus cash: the number that actually constrains a transfer."""
        return self.sale_value(prices) + self.bank_tenths

    def affordable(self, outgoing: int, prices: Mapping[int, int]) -> int:
        """Budget available for a replacement once ``outgoing`` is sold."""
        holding = self.holdings.get(outgoing)
        if holding is None:
            return self.bank_tenths
        return self.bank_tenths + holding.sells_for(prices)

    def transfer(self, outgoing: int, incoming: int, prices: Mapping[int, int]) -> None:
        """Sell one player and buy another, settling the difference in cash."""
        holding = self.holdings.get(outgoing)
        if holding is None:
            raise KeyError(f"element {outgoing} is not held")
        if incoming in self.holdings:
            raise ValueError(f"element {incoming} is already held")
        cost = prices.get(incoming)
        if cost is None:
            raise KeyError(f"element {incoming} has no price")

        proceeds = holding.sells_for(prices)
        if self.bank_tenths + proceeds < cost:
            raise ValueError("cannot afford the incoming player")

        del self.holdings[outgoing]
        self.bank_tenths += proceeds - cost
        # Bought at today's price, which becomes the basis for his own future sale.
        self.holdings[incoming] = Holding(incoming, cost)
