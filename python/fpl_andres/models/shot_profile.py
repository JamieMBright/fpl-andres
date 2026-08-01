"""Shot volume and shot quality, separated.

A player's non-penalty xG per 90 is volume times quality: how often he shoots,
and how good the chances are. The two behave differently. Measured across four
Understat seasons on players with 900+ minutes in both, shot volume repeats at
**0.890** year to year, npxG/90 at **0.860**, and shot quality at only
**0.455**. Volume is the durable part.

Quality is noisy but it is not noise. Replacing a player's own quality with the
league mean makes prediction worse, not better: MAE rises from 0.0561 to 0.0666.
Shrinking it toward the league in proportion to the shots behind it wins, with
the optimum near ten shots of prior.

The honest size of the win: MAE 0.05608 to 0.05417, a 3.4% reduction, which is
about 0.0076 FPL points a 90 for a forward, or **0.29 points across a season**.
Real and measured, but small enough that it does not on its own justify moving
the projector off FPL's own expected goals.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "ShotProfile",
    "ShotProfileUnavailable",
    "league_shot_quality",
    "shot_profile",
]

# Shots of league-average quality mixed into every player's own rate. Fitted on
# 553 season pairs: MAE by k was 0.05608 at 0, 0.05435 at 10, 0.05502 at 30,
# 0.05821 at 100. Chosen by measurement, not judgement.
_QUALITY_PRIOR_SHOTS = 10.0
# Volume repeats well but not perfectly, and a touch of regression helped:
# 0.05435 to 0.05417.
_VOLUME_REGRESSION = 0.1
_MINUTES_PER_90 = 90.0


class ShotProfileUnavailable(ValueError):
    """Raised when there is too little shooting to read a profile from."""


@dataclass(frozen=True)
class ShotProfile:
    """One player's shooting, split into how often and how good."""

    shots: int
    minutes: int
    non_penalty_expected_goals: float
    shots_per_90: float
    # Shrunk toward the league, so a nine-shot season cannot claim elite quality.
    expected_goals_per_shot: float
    raw_expected_goals_per_shot: float
    quality_weight: float

    @property
    def expected_goals_per_90(self) -> float:
        return self.shots_per_90 * self.expected_goals_per_shot


def league_shot_quality(
    profiles: Sequence[tuple[float, int]],
) -> float:
    """Mean non-penalty xG per shot across the league.

    Takes (non_penalty_expected_goals, shots) pairs. Pooled rather than averaged
    per player, so a fringe player with four shots cannot move it.
    """
    total_shots = sum(shots for _, shots in profiles)
    if total_shots <= 0:
        raise ShotProfileUnavailable("no shots to measure league quality from")
    total_xg = sum(expected for expected, _ in profiles)
    return total_xg / total_shots


def shot_profile(
    *,
    shots: int,
    minutes: int,
    non_penalty_expected_goals: float,
    league_quality: float,
    volume_regression: float = _VOLUME_REGRESSION,
    league_shots_per_90: float | None = None,
) -> ShotProfile:
    """Split a shooting record into volume and shrunk quality."""
    if shots < 0:
        raise ShotProfileUnavailable("shots cannot be negative")
    if minutes <= 0:
        raise ShotProfileUnavailable("a profile needs minutes to divide by")
    if non_penalty_expected_goals < 0.0:
        raise ShotProfileUnavailable("expected goals cannot be negative")
    if league_quality <= 0.0:
        raise ShotProfileUnavailable("league quality must be positive")

    nineties = minutes / _MINUTES_PER_90
    raw_volume = shots / nineties
    volume = raw_volume
    if league_shots_per_90 is not None:
        volume = (1.0 - volume_regression) * raw_volume + volume_regression * league_shots_per_90

    if shots == 0:
        return ShotProfile(
            shots=0,
            minutes=minutes,
            non_penalty_expected_goals=non_penalty_expected_goals,
            shots_per_90=volume,
            expected_goals_per_shot=league_quality,
            raw_expected_goals_per_shot=0.0,
            quality_weight=0.0,
        )

    raw_quality = non_penalty_expected_goals / shots
    weight = shots / (shots + _QUALITY_PRIOR_SHOTS)
    quality = weight * raw_quality + (1.0 - weight) * league_quality
    return ShotProfile(
        shots=shots,
        minutes=minutes,
        non_penalty_expected_goals=non_penalty_expected_goals,
        shots_per_90=volume,
        expected_goals_per_shot=quality,
        raw_expected_goals_per_shot=raw_quality,
        quality_weight=weight,
    )
