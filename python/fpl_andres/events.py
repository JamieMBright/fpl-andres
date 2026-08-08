"""How many gameweeks a season can have.

An ordinary season is 38. A disrupted one is not: 2019/20 was suspended in
March and resumed in June, and its events run to 47. The history schema has
always allowed that, and the rate and minutes models have always read 47.

Three other guards said 38, which meant fitting Dixon-Coles or scoring a
backtest on 2019/20 raised on an event that really happened. One number, in one
place, so the two halves of the package cannot disagree about what a season is
again.
"""

from __future__ import annotations

__all__ = ["MAX_EVENT"]

MAX_EVENT = 47
