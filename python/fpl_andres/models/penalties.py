"""How much of a player's expected goals comes from the penalty spot.

FPL's own `expected_goals` includes penalties, so projecting a player's scoring
from it quietly assumes he keeps the duty. Duty moves: between seasons, on a
transfer, and sometimes after one miss. Measured on 2025-26, penalties are only
5.9% of league xG but 44.5% of Cole Palmer's and 38.3% of Bruno Fernandes's,
and 24 regulars sit above 15%. That is a concentrated, nameable risk rather
than a rounding error, so it is worth carrying next to the projection.

Nothing here predicts who will take penalties. It measures exposure to the
assumption already being made.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PenaltyExposure",
    "PenaltySplitUnavailable",
    "penalty_exposure",
]

# Understat reports xG to full float precision, so allow for float noise only.
_CONTRADICTION_TOLERANCE = 1e-6
_MINUTES_PER_90 = 90.0


class PenaltySplitUnavailable(ValueError):
    """Raised when the penalty and open-play split cannot be trusted."""


@dataclass(frozen=True)
class PenaltyExposure:
    """One player's dependence on penalties, over a measured period."""

    expected_goals: float
    non_penalty_expected_goals: float
    goals: int
    non_penalty_goals: int
    minutes: int

    @property
    def penalty_expected_goals(self) -> float:
        return self.expected_goals - self.non_penalty_expected_goals

    @property
    def penalties_scored(self) -> int:
        return self.goals - self.non_penalty_goals

    @property
    def share(self) -> float:
        """Fraction of expected goals that comes from the spot."""
        if self.expected_goals <= 0.0:
            return 0.0
        return self.penalty_expected_goals / self.expected_goals

    def expected_goals_at_risk_per_90(self) -> float:
        """Open-play xG is unaffected by duty; this is what duty is worth."""
        if self.minutes <= 0:
            return 0.0
        return self.penalty_expected_goals / (self.minutes / _MINUTES_PER_90)

    def points_at_risk_per_90(self, goal_points: int) -> float:
        """Points a 90 that depend on keeping the duty, at this position's rate."""
        return self.expected_goals_at_risk_per_90() * goal_points


def penalty_exposure(
    *,
    expected_goals: float,
    non_penalty_expected_goals: float,
    goals: int,
    non_penalty_goals: int,
    minutes: int,
) -> PenaltyExposure:
    """Split a scoring record into penalty and open-play parts.

    Refuses rather than repairing a contradictory split: non-penalty totals
    above the overall total mean the two figures came from different places,
    and silently clamping would hide that.
    """
    if expected_goals < 0.0 or non_penalty_expected_goals < 0.0:
        raise PenaltySplitUnavailable("expected goals cannot be negative")
    if goals < 0 or non_penalty_goals < 0:
        raise PenaltySplitUnavailable("goals cannot be negative")
    if minutes < 0:
        raise PenaltySplitUnavailable("minutes cannot be negative")
    if non_penalty_expected_goals > expected_goals + _CONTRADICTION_TOLERANCE:
        raise PenaltySplitUnavailable(
            f"non-penalty xG {non_penalty_expected_goals} exceeds total {expected_goals}"
        )
    if non_penalty_goals > goals:
        raise PenaltySplitUnavailable(
            f"non-penalty goals {non_penalty_goals} exceeds total {goals}"
        )

    return PenaltyExposure(
        expected_goals=expected_goals,
        non_penalty_expected_goals=min(non_penalty_expected_goals, expected_goals),
        goals=goals,
        non_penalty_goals=non_penalty_goals,
        minutes=minutes,
    )
