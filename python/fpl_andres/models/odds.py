"""Turning quoted prices into probabilities, correctly.

Bookmakers price fixtures for a living and are marked to market by people trying
to take their money, so their implied probabilities are the strongest freely
available estimate of match outcome, total goals and clean sheets. None of that
is usable until the margin is removed.

Quoted prices are not probabilities. Their reciprocals sum to more than one,
because the excess is the bookmaker's income. The obvious repair - divide
through by the total - is **biased**, because the margin is not spread evenly:
longshots carry more of it than favourites. That bias runs in exactly the
direction that would flatter cheap differential punts, which is what FPL
rewards, so it is the one repair not to use.

Two unbiased-ish alternatives are implemented: a power fit, and Shin's method,
which models the margin as protection against insider betting.

Nothing here fetches odds. Measured 2026-08-01, this network refuses
football-data.co.uk, api.the-odds-api.com and oddsportal.com at the TLS
handshake while the FPL API and Understat succeed, which is a gambling-category
content filter. Prices arrive from a caller.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "OddsUnavailable",
    "clean_sheet_probability",
    "devig_power",
    "devig_proportional",
    "devig_shin",
    "implied_probabilities",
    "overround",
]

_TOLERANCE = 1e-10
_MAX_ITERATIONS = 200


class OddsUnavailable(ValueError):
    """Raised when quoted prices cannot be read as a market."""


@dataclass(frozen=True)
class _Market:
    raw: tuple[float, ...]
    booksum: float


def _market(decimal_odds: Sequence[float]) -> _Market:
    if len(decimal_odds) < 2:
        raise OddsUnavailable("a market needs at least two outcomes")
    for price in decimal_odds:
        if not math.isfinite(price) or price <= 1.0:
            raise OddsUnavailable(f"decimal odds must exceed 1.0, got {price}")
    raw = tuple(1.0 / price for price in decimal_odds)
    booksum = sum(raw)
    if booksum <= 1.0:
        # Under 1.0 is an arbitrage, not a bookmaker's market; refuse rather
        # than invent a negative margin.
        raise OddsUnavailable(f"implied probabilities sum to {booksum:.4f}, not a priced market")
    return _Market(raw=raw, booksum=booksum)


def implied_probabilities(decimal_odds: Sequence[float]) -> tuple[float, ...]:
    """Raw reciprocals. These sum to more than one and are not probabilities."""
    return _market(decimal_odds).raw


def overround(decimal_odds: Sequence[float]) -> float:
    """The bookmaker's margin, as a fraction above a fair book."""
    return _market(decimal_odds).booksum - 1.0


def devig_proportional(decimal_odds: Sequence[float]) -> tuple[float, ...]:
    """Divide through by the total. Provided as the baseline to argue against.

    Assumes the margin is spread evenly across outcomes, which it is not, so it
    systematically overprices longshots.
    """
    market = _market(decimal_odds)
    return tuple(probability / market.booksum for probability in market.raw)


def devig_power(decimal_odds: Sequence[float]) -> tuple[float, ...]:
    """Find k with sum(raw_i ** k) == 1.

    Because every raw probability is below one, raising to k > 1 shrinks the
    small ones proportionally harder, which is the observed shape of the margin.
    """
    market = _market(decimal_odds)

    def total(k: float) -> float:
        return float(sum(probability**k for probability in market.raw))

    low, high = 1.0, 2.0
    while total(high) > 1.0 and high < 64.0:
        high *= 2.0
    for _ in range(_MAX_ITERATIONS):
        middle = (low + high) / 2.0
        if abs(total(middle) - 1.0) < _TOLERANCE:
            break
        if total(middle) > 1.0:
            low = middle
        else:
            high = middle
    exponent = (low + high) / 2.0
    fitted = [probability**exponent for probability in market.raw]
    scale = sum(fitted)
    return tuple(value / scale for value in fitted)


def devig_shin(decimal_odds: Sequence[float]) -> tuple[float, ...]:
    """Shin's method: the margin as protection against better-informed money.

    Solves for the insider share z that makes the implied probabilities sum to
    one. Reduces to proportional de-vigging as z approaches zero.
    """
    market = _market(decimal_odds)

    def probabilities(z: float) -> list[float]:
        if z <= 0.0:
            return [p / market.booksum for p in market.raw]
        return [
            (math.sqrt(z * z + 4.0 * (1.0 - z) * p * p / market.booksum) - z) / (2.0 * (1.0 - z))
            for p in market.raw
        ]

    low, high = 0.0, 0.99
    for _ in range(_MAX_ITERATIONS):
        middle = (low + high) / 2.0
        total = sum(probabilities(middle))
        if abs(total - 1.0) < _TOLERANCE:
            break
        if total > 1.0:
            low = middle
        else:
            high = middle
    fitted = probabilities((low + high) / 2.0)
    scale = sum(fitted)
    return tuple(value / scale for value in fitted)


def clean_sheet_probability(opponent_expected_goals: float) -> float:
    """A clean sheet is the opponent failing to score, so the Poisson zero.

    This is the join between an odds-derived goal expectation and the FPL
    scoring route the projector currently estimates from history alone.
    """
    if not math.isfinite(opponent_expected_goals) or opponent_expected_goals < 0.0:
        raise OddsUnavailable("expected goals must be finite and non-negative")
    return math.exp(-opponent_expected_goals)
