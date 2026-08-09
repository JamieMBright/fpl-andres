"""What a bookmaker's scoring price says about a player's minutes.

A model reading last season alone cannot know that a striker has lost his
place, or that a summer signing has taken it. A book can: it prices him to
score, and a price of 30-to-1 on a forward is not a statement about finishing,
it is a statement about whether he starts.

So the market is read as evidence about minutes and blended with the record,
never substituted for it. Three things make that honest rather than convenient:

* The positional scoring rate is required and must be positive. Without it the
  quotient below has no denominator and this refuses to produce a number.
* The blend weight is supplied by the caller. There is no default here, because
  a default weight is an unsourced parameter deciding how much of the
  projection the market owns.
* A player with no quoted price is left exactly as the record measured him.
  Silence from a bookmaker is not evidence that somebody will not play.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "MarketMinutesError",
    "MarketMinutesEvidence",
    "blend_start_rate",
    "market_start_probability",
]


class MarketMinutesError(ValueError):
    """Raised when a price cannot be read as evidence about minutes."""


@dataclass(frozen=True)
class MarketMinutesEvidence:
    """One player's scoring price, and what is needed to read it."""

    #: P(scores at least once), de-vigged, from the odds artifact.
    anytime_goal: float
    #: What a player of his position is projected to score in a match.
    positional_scoring_rate: float
    #: How much of the blended start rate the market owns, 0 to 1.
    weight: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.anytime_goal <= 1.0:
            raise MarketMinutesError(f"anytime_goal must be a probability, got {self.anytime_goal}")
        if self.positional_scoring_rate <= 0.0:
            raise MarketMinutesError(
                "positional_scoring_rate must be measured and positive; "
                f"got {self.positional_scoring_rate}"
            )
        if not 0.0 <= self.weight <= 1.0:
            raise MarketMinutesError(f"weight must be 0 to 1, got {self.weight}")


def market_start_probability(evidence: MarketMinutesEvidence) -> float:
    """
    The chance he starts, read off what he is quoted to score.

    A player priced at his position's per-match scoring rate is being treated as
    a certain starter; half of it reads as a coin toss. The quotient is capped
    at one because it is a ratio and not a probability, and a striker in form
    can out-price his positional rate without being more than certain to play.
    """
    return min(1.0, evidence.anytime_goal / evidence.positional_scoring_rate)


def blend_start_rate(recorded: float, evidence: MarketMinutesEvidence) -> float:
    """The record and the market, weighted, clamped to a probability."""
    if not 0.0 <= recorded <= 1.0:
        raise MarketMinutesError(f"recorded start rate must be a probability, got {recorded}")
    market = market_start_probability(evidence)
    blended = (1.0 - evidence.weight) * recorded + evidence.weight * market
    return min(1.0, max(0.0, blended))
