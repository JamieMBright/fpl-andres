"""Yellow-card accumulation, and the suspension it eventually triggers.

A booking is worth minus one point. The accumulation behind it is worth far
more: crossing a threshold costs a whole gameweek, and for a nailed starter that
is the difference between five points and none. A model that prices the card and
ignores the ban has priced the small half.

Thresholds are **sourced, never assumed**. The Premier League resets cautions
partway through the season and the reset point is a rule, not a modelling
choice, so `SuspensionRules` must be supplied by a caller who has read the
handbook. Nothing here invents one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "CardRateUnavailable",
    "SuspensionRisk",
    "SuspensionRules",
    "SuspensionThreshold",
    "suspension_risk",
]


class CardRateUnavailable(ValueError):
    """Raised when there is too little evidence to estimate a booking rate."""


@dataclass(frozen=True)
class SuspensionThreshold:
    """One rung of the accumulation ladder."""

    cards: int
    # Matches the ban lasts once the rung is reached.
    matches_banned: int
    # The last gameweek at which this rung can still be triggered. Cautions are
    # wiped for the lower rungs partway through a season.
    applies_through_event: int

    def __post_init__(self) -> None:
        if self.cards <= 0:
            raise ValueError("threshold must be a positive number of cards")
        if self.matches_banned <= 0:
            raise ValueError("a threshold that bans nobody is not a threshold")
        if not 1 <= self.applies_through_event <= 60:
            raise ValueError("threshold must expire inside a season")


@dataclass(frozen=True)
class SuspensionRules:
    """The accumulation ladder for one season, as published.

    Deliberately has no default. The repository's standing rule is that a
    missing controlling rule fails visibly rather than being guessed, and the
    thresholds have changed before.
    """

    season: str
    thresholds: tuple[SuspensionThreshold, ...]
    source_reference: str

    def __post_init__(self) -> None:
        if not self.thresholds:
            raise ValueError("suspension rules require at least one threshold")
        if not self.source_reference.strip():
            raise ValueError("suspension rules must name the source they came from")
        rungs = [threshold.cards for threshold in self.thresholds]
        if rungs != sorted(rungs) or len(set(rungs)) != len(rungs):
            raise ValueError("thresholds must ascend and be distinct")


@dataclass(frozen=True)
class SuspensionRisk:
    """One player's exposure over a planning horizon."""

    cards_per_match: float
    cards_so_far: int
    # Chance of being banned for at least one match inside the horizon.
    probability_banned: float
    # Matches expected to be missed, which is what scales expected points.
    expected_matches_missed: float
    # The rung the player is closest to, for explaining the number.
    next_threshold: int | None
    cards_from_threshold: int | None

    def availability(self, horizon: int) -> float:
        """Share of the horizon the player is expected to be available for."""
        if horizon <= 0:
            return 1.0
        return max(0.0, 1.0 - self.expected_matches_missed / horizon)


# Below this a booking rate is noise, not a tendency.
_MINIMUM_MATCHES = 5


def suspension_risk(
    *,
    yellow_cards: Sequence[int],
    rules: SuspensionRules,
    current_event: int,
    horizon: int,
) -> SuspensionRisk:
    """Estimate a player's exposure to an accumulation ban over the horizon.

    Uses a Poisson-binomial approximation: bookings arrive at a steady per-match
    rate, and the player is banned once the running count reaches a rung that is
    still live at his current gameweek. Rungs that have already expired cannot
    be triggered, which is the whole point of the mid-season reset.
    """
    matches = len(yellow_cards)
    if matches < _MINIMUM_MATCHES:
        raise CardRateUnavailable(f"{matches} matches is too few to read a booking rate from")
    if horizon <= 0:
        raise ValueError("horizon must be positive")

    cards_so_far = sum(yellow_cards)
    rate = cards_so_far / matches

    live = [
        threshold
        for threshold in rules.thresholds
        if threshold.applies_through_event >= current_event and threshold.cards > cards_so_far
    ]
    if not live:
        return SuspensionRisk(
            cards_per_match=rate,
            cards_so_far=cards_so_far,
            probability_banned=0.0,
            expected_matches_missed=0.0,
            next_threshold=None,
            cards_from_threshold=None,
        )

    target = live[0]
    needed = target.cards - cards_so_far
    # Chance of collecting at least `needed` bookings in `horizon` matches,
    # from a Poisson with mean rate * horizon.
    probability = _poisson_tail(rate * horizon, needed)
    return SuspensionRisk(
        cards_per_match=rate,
        cards_so_far=cards_so_far,
        probability_banned=probability,
        expected_matches_missed=probability * target.matches_banned,
        next_threshold=target.cards,
        cards_from_threshold=needed,
    )


def _poisson_tail(mean: float, at_least: int) -> float:
    """P(X >= at_least) for a Poisson with the given mean."""
    if at_least <= 0:
        return 1.0
    if mean <= 0.0:
        return 0.0
    # Sum the head and subtract, which is stable for the small means here.
    from math import exp

    term = exp(-mean)
    head = term
    for k in range(1, at_least):
        term *= mean / k
        head += term
    return max(0.0, min(1.0, 1.0 - head))
