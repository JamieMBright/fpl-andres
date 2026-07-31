"""Effective points: what actually moves you up a table.

Expected points and rank movement are not the same objective, and conflating
them is the most common mistake in this game.

The arithmetic that matters: owning a player everyone else owns is worth nothing
to your rank, because every rival banks the same score. Missing him costs you his
full return. So a player's contribution to *rank* is his projection multiplied by
the gap between your ownership and the field's.

There is a subtlety worth stating plainly, because it changes what the number is
for. Effective ownership cancels out of the *expected* gain from a transfer:
buying a player raises your swing by his full projection whether or not the field
owns him. What ownership changes is the spread of outcomes. Covering the field
narrows it; taking differentials widens it. Which of those you want depends
entirely on whether you are ahead or behind, so this module reports both the
central estimate and the risk it carries rather than collapsing them into one
score.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "EffectivePoints",
    "RankModel",
    "effective_points",
]


@dataclass(frozen=True)
class RankModel:
    """How a points difference converts into a rank difference.

    Manager scores are roughly normal around the gameweek average, so the share
    of the field you overtake with a given points gain is the normal CDF. The
    spread is measured from the field rather than assumed.
    """

    mean_points: float
    standard_deviation: float
    field_size: int

    def __post_init__(self) -> None:
        if self.standard_deviation <= 0:
            raise ValueError("a field with no spread has no ranks to climb")
        if self.field_size <= 1:
            raise ValueError("a field of one has no ranks to climb")

    def share_below(self, points: float) -> float:
        """Share of the field this score finishes above."""
        z = (points - self.mean_points) / self.standard_deviation
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    def rank_of(self, points: float) -> float:
        """Expected overall rank for a score, one being best."""
        return max(1.0, (1.0 - self.share_below(points)) * self.field_size)

    def places_gained(self, points: float, extra: float) -> float:
        """How many places ``extra`` points is worth, from a given starting score."""
        return self.rank_of(points) - self.rank_of(points + extra)


@dataclass(frozen=True)
class EffectivePoints:
    """One player, scored for rank movement rather than raw return."""

    element_id: int
    expected_points: float
    effective_ownership: float
    owned: bool

    @property
    def swing(self) -> float:
        """Expected points gained on the average rival by the current holding."""
        mine = 1.0 if self.owned else 0.0
        return (mine - self.effective_ownership) * self.expected_points

    @property
    def cover(self) -> float:
        """What not owning him would cost. Always at or above zero."""
        return self.effective_ownership * self.expected_points

    @property
    def upside(self) -> float:
        """What owning him gains on the rivals who do not. Always at or above zero."""
        return (1.0 - self.effective_ownership) * self.expected_points

    def places(self, model: RankModel, current_points: float) -> float:
        """The swing expressed as places on the table."""
        return model.places_gained(current_points, self.swing)


def effective_points(
    projected: Mapping[int, float],
    ownership: Mapping[int, float],
    held: Sequence[int],
) -> list[EffectivePoints]:
    """Rank every candidate by what it does to your position, best first.

    Players absent from ``ownership`` are treated as unowned by the field, which
    is the correct reading for a differential rather than a missing value: the
    published aggregate lists everyone with any ownership at all.
    """
    mine = set(held)
    return sorted(
        (
            EffectivePoints(
                element_id=element_id,
                expected_points=points,
                effective_ownership=ownership.get(element_id, 0.0),
                owned=element_id in mine,
            )
            for element_id, points in projected.items()
        ),
        key=lambda entry: -entry.swing,
    )
