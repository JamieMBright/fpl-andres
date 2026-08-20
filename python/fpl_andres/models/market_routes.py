"""What a bookmaker's player prices imply a footballer will actually do.

A book prices "anytime goalscorer": the chance of at least one. FPL pays per
goal. Those are different numbers, and the bridge between them is an assumption
rather than an identity, so it is named here instead of buried in a caller.
Goals arrive within a match as a Poisson process, which makes P(at least one)
equal to ``1 - exp(-lambda)`` and therefore ``lambda = -ln(1 - P)``.

The assumption is mild for a footballer and it fails in one direction. Hardly
anybody scores twice, so the tail the inversion invents is small; real scoring
is slightly underdispersed against Poisson, so a player quoted very short reads
a shade high. That is stated rather than corrected, because there is no
measurement here to correct it with.

What the market has and this repository does not is the fixture. An anytime
price is for a named opponent at a named venue and already carries the team
news, the rotation risk and the manager's press conference. What it does not
have is a season: the price exists for the next match and nothing else. So a
market rate is read as evidence about a player and blended with the record at a
weight the caller supplies -- never substituted for it, and never extrapolated
past the match it was quoted for.

Point values are arguments rather than constants. The scoring table lives in
`backtesting/scoring.py`, this is a model, and a model importing the backtest to
learn that a midfielder's goal is worth five is the wrong direction.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "MarketAttack",
    "MarketCards",
    "MarketRoutesError",
    "TeamTotalMismatch",
    "blend_rate",
    "implied_events",
    "market_attack",
    "market_cards",
    "reconcile_to_team_total",
]


class MarketRoutesError(ValueError):
    """Raised when a price cannot be read as evidence about a scoring route."""


#: How far the fitted exponent may travel before the fit is abandoned. A book
#: quoting a squad three times over lands near two; the low end leaves room for
#: a player market implying fewer goals than the team price, which happens when
#: only a handful of a squad is quoted.
_EXPONENT_BOUNDS = (0.05, 20.0)


def implied_events(probability: float) -> float:
    """How many the market expects, from the chance of at least one.

    A probability of one would invert to an infinite rate, so it is refused
    rather than clamped: no book prices a footballer certain to score, and a
    quote that says otherwise is a parsing fault worth seeing.
    """
    if not 0.0 <= probability < 1.0:
        raise MarketRoutesError(f"a chance of at least one must be in [0, 1), got {probability}")
    return -math.log1p(-probability)


@dataclass(frozen=True)
class MarketAttack:
    """Goals and assists the market expects of one player in one fixture.

    Either half may be absent. Books open an anytime-scorer market on every
    fixture and an assist market on rather fewer, so requiring both would throw
    away most of what arrives. The halves are kept apart so each can be blended
    against the record's own estimate of the same thing.
    """

    goals: float | None
    assists: float | None


def market_attack(anytime_goal: float | None, anytime_assist: float | None) -> MarketAttack | None:
    """One fixture's attacking expectation, or None when neither is priced."""
    goals = None if anytime_goal is None else implied_events(anytime_goal)
    assists = None if anytime_assist is None else implied_events(anytime_assist)
    if goals is None and assists is None:
        return None
    return MarketAttack(goals=goals, assists=assists)


def blend_rate(recorded: float, market: float, weight: float) -> float:
    """The record and the market, weighted, floored at nothing.

    The weight is the caller's because a default here would be an unsourced
    parameter deciding how much of the projection a bookmaker owns.
    """
    if not 0.0 <= weight <= 1.0:
        raise MarketRoutesError(f"weight must be 0 to 1, got {weight}")
    if recorded < 0.0 or market < 0.0:
        raise MarketRoutesError(f"rates cannot be negative, got {recorded} and {market}")
    return (1.0 - weight) * recorded + weight * market


@dataclass(frozen=True)
class TeamTotalMismatch:
    """How far one club's player prices sat from its own team price.

    `exponent` is the power every player probability was raised to. Above one
    means the player market implied more goals than the team market did, and
    the longshots gave up most of the difference.
    """

    club: str
    player_events: float
    team_events: float
    exponent: float
    quoted_players: int


def reconcile_to_team_total(
    probabilities: Mapping[int, float],
    team_events: float,
    *,
    club: str,
) -> tuple[dict[int, float], TeamTotalMismatch]:
    """Fit one club's player prices onto the goals its own team book implies.

    Two prices in the same feed answer the same question. A club's expected
    goals is the sum of what each of its players is expected to score, so
    ``sum(lambda_player)`` and the team's expected goals are the same quantity
    read two ways. Measured on the 2026-08-20 artifact they disagreed by a
    median factor of 2.45, every club in the same direction.

    The team book is the one to trust. Home, draw, away and over/under are all
    quoted, so Shin's method has a complete book to take the margin out of. An
    anytime-scorer market publishes only the yes, so there is no complement to
    de-vig against and the margin stays in every price.

    The margin is not spread evenly. A book earns most of it on the longshots,
    which is why a flat rescale -- proportional de-vigging by another name --
    is the wrong correction: it takes the same fraction off the striker as off
    the third-choice full-back and leaves the favourite far too cheap. Measured
    on Manchester City against Bournemouth, a flat scale left Haaland with 0.48
    goals against a team total of 2.40, a fifth of his side's scoring, while the
    power fit gave him 0.75.

    So the exponent is fitted instead: every probability is raised to the same
    power `k` and `k` is chosen to make the goals add up. Raising to a power
    above one shrinks a long price far harder than a short one, which is the
    shape a bookmaker's margin actually has.

    What survives is the market's ordering. What is surrendered is its level.
    Assists are raised to the same power, because the margin being removed
    belongs to how a one-sided player market has to be read rather than to the
    particular market, and no team-level assist price exists to fit them
    against on their own.
    """
    if team_events < 0.0:
        raise MarketRoutesError(f"team events cannot be negative, got {team_events}")
    for value in probabilities.values():
        if not 0.0 <= value < 1.0:
            raise MarketRoutesError(f"a chance of at least one must be in [0, 1), got {value}")

    def total(exponent: float) -> float:
        return sum(implied_events(value**exponent) for value in probabilities.values())

    raw = total(1.0)
    unchanged = {element: implied_events(value) for element, value in probabilities.items()}
    if not probabilities or raw <= 0.0 or team_events <= 0.0:
        return unchanged, TeamTotalMismatch(
            club=club,
            player_events=raw,
            team_events=team_events,
            exponent=1.0,
            quoted_players=len(probabilities),
        )

    # Monotone decreasing in the exponent, so a plain bisection finds it. The
    # bracket is wide enough for a book quoting a squad three times over and for
    # one quoting fewer goals than the team price.
    low, high = _EXPONENT_BOUNDS
    if not total(high) <= team_events <= total(low):
        return unchanged, TeamTotalMismatch(
            club=club,
            player_events=raw,
            team_events=team_events,
            exponent=1.0,
            quoted_players=len(probabilities),
        )
    for _ in range(200):
        middle = (low + high) / 2.0
        if total(middle) > team_events:
            low = middle
        else:
            high = middle
    exponent = (low + high) / 2.0
    return {
        element: implied_events(value**exponent) for element, value in probabilities.items()
    }, TeamTotalMismatch(
        club=club,
        player_events=raw,
        team_events=team_events,
        exponent=exponent,
        quoted_players=len(probabilities),
    )


@dataclass(frozen=True)
class MarketCards:
    """Bookings the market expects of one player in one fixture.

    `cards` is every booking, because that is the market a book opens: "to be
    shown a card" does not say which colour. `red` is the separate market, open
    on fewer fixtures. FPL pays -1 and -3, so the split decides the points and
    the caller has to make it -- from the red market where there is one, and
    from the player's own recorded ratio where there is not.
    """

    cards: float
    red: float | None


def market_cards(any_card: float | None, red_card: float | None) -> MarketCards | None:
    """One fixture's booking expectation, or None where nothing is priced.

    A red-only quote is refused. Reds are a twentieth of bookings, so a rate
    built from them alone would describe almost none of the points at stake and
    would read as if the player were never booked otherwise.
    """
    if any_card is None:
        return None
    return MarketCards(
        cards=implied_events(any_card),
        red=None if red_card is None else implied_events(red_card),
    )
