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
from typing import Protocol

__all__ = [
    "CovarianceUnavailable",
    "EffectivePoints",
    "PointsCovariance",
    "RankModel",
    "SwingRisk",
    "effective_points",
    "swing_risk",
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


class CovarianceUnavailable(RuntimeError):
    """Raised when the spread of a squad's swing cannot be stated honestly.

    The module docstring already said that what ownership
    changes is the *spread* of outcomes, and then reported only expected values.
    This is the missing half, and it is only correct with a covariance that
    somebody measured.

    Refusing rather than assuming zero, for the reason that makes the whole item
    worth doing: two Arsenal defenders do not return independently. A clean
    sheet pays both, and a defeat pays neither. Treating them as independent
    understates the variance of a squad built around one defence -- which is the
    exact shape of squad this game rewards and punishes -- and would report a
    narrow spread for the riskiest thing a manager can do.
    """


class PointsCovariance(Protocol):
    """Covariance of two players' returns in one gameweek.

    Supplied by the caller because nothing here can derive it. A same-club pair
    covaries through the team's clean sheet and goals; a cross-club pair covaries
    through the gameweek's overall scoring. Both are measurable from the corpus,
    and neither is a number this module may invent.
    """

    def between(self, first: int, second: int) -> float | None:
        """Covariance, or None when it has not been measured for this pair."""
        ...


@dataclass(frozen=True)
class SwingRisk:
    """The spread of the swing a squad carries into a gameweek."""

    expected_swing: float
    variance: float

    def __post_init__(self) -> None:
        if self.variance < 0:
            # Only reachable from an inconsistent covariance -- one that is not
            # positive semi-definite. That is a fault in the measurement, and
            # rounding it up to zero would hide it.
            raise ValueError("a variance cannot be negative; the covariance is inconsistent")

    @property
    def standard_deviation(self) -> float:
        return math.sqrt(self.variance)

    def interval(self, model: RankModel, current_points: float) -> tuple[float, float]:
        """Rank at one standard deviation either side of the expected swing.

        Returned best-first, so the pair reads as a range rather than as two
        numbers whose order has to be worked out. Note the asymmetry is real:
        the rank curve is steepest in the middle of the field, so equal points
        either way are not equal places.
        """
        low = model.rank_of(current_points + self.expected_swing - self.standard_deviation)
        high = model.rank_of(current_points + self.expected_swing + self.standard_deviation)
        return (min(low, high), max(low, high))


def swing_risk(
    entries: Sequence[EffectivePoints],
    covariance: PointsCovariance,
) -> SwingRisk:
    """Expected swing and its variance across a squad, correlation included.

    Each player contributes his return weighted by the gap between owning him
    and the field owning him, so the total swing is

        sum over i of (mine_i - owned_by_field_i) * points_i

    and its variance is the full double sum

        sum over i, j of w_i * w_j * cov(i, j)

    which is where correlation enters. Dropping the off-diagonal terms -- which
    is what treating players as independent means -- removes exactly the effect
    that makes a squad built on one defence risky.

    The weights are not random: ownership is published and the holding is a
    decision. All the uncertainty is in the returns, which is why the covariance
    is over points alone.
    """
    weights = {
        entry.element_id: (1.0 if entry.owned else 0.0) - entry.effective_ownership
        for entry in entries
    }
    expected = sum(weights[entry.element_id] * entry.expected_points for entry in entries)

    variance = 0.0
    missing: list[tuple[int, int]] = []
    for first in entries:
        for second in entries:
            pair = covariance.between(first.element_id, second.element_id)
            if pair is None:
                missing.append((first.element_id, second.element_id))
                continue
            variance += weights[first.element_id] * weights[second.element_id] * pair

    if missing:
        # Named rather than counted: the caller has to know which measurement to
        # go and take, and a bare count sends them to look at all of them.
        shown = ", ".join(f"{one}/{other}" for one, other in sorted(set(missing))[:5])
        raise CovarianceUnavailable(
            f"{len(set(missing))} player pair(s) have no measured covariance, "
            f"so the spread of this squad's swing cannot be stated: {shown}"
        )

    return SwingRisk(expected_swing=expected, variance=variance)
