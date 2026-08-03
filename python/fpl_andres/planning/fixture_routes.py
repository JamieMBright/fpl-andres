"""Applying a fixture to a published projection, route by route.

`projections.json` carries each player's expected points broken into the routes
that earned them. A fixture does not move those routes together: a hard away tie
suppresses clean sheets while raising saves, and the same match is good news for
a keeper and bad news for the defender in front of him.

Collapsing that into one difficulty number is what let a defender be rated
*better* for facing the best attack in the league. This applies the measured
per-route multipliers to the measured per-route points instead.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fpl_andres.backtesting.fixtures import TeamStrength, route_adjustment

__all__ = [
    "ROUTE_KEYS",
    "fixture_difficulty",
    "fixture_multiplier",
    "fixture_points_from_routes",
]

# Where a measured tie sits on the published one-to-five scale. Chosen so the
# twenty clubs spread across all five bands rather than piling into the middle.
DIFFICULTY_BANDS = (0.72, 0.90, 1.11, 1.39)


def fixture_difficulty(
    games: Sequence[tuple[int, bool]],
    team_id: int,
    strength: Mapping[int, TeamStrength],
) -> int | None:
    """One to five, where one is the softest tie and five the hardest.

    Rated on both halves of the fixture, at the venue it is played: what this
    side is likely to score against that opponent, over what it is likely to
    concede. A blank is None rather than three, because there is no fixture to
    be difficult.
    """
    rated = [
        route_adjustment(strength, team_id, opponent, home=home)
        for opponent, home in games
        if opponent in strength and team_id in strength
    ]
    if not rated:
        return None
    # A double gameweek averages its fixtures rather than summing them: two hard
    # games are still hard, not twice as hard.
    ease = sum(adjustment.attacking / adjustment.conceding for adjustment in rated) / len(rated)
    return 5 - sum(1 for band in DIFFICULTY_BANDS if ease >= band)


# The published route names, and whether a fixture moves them at all. Appearance
# points, bonus and discipline do not depend on who the opponent is.
ROUTE_KEYS = (
    "appearance",
    "attacking",
    "cleanSheet",
    "bonus",
    "saves",
    "conceding",
    "discipline",
    "defensiveContribution",
)


def fixture_points_from_routes(
    routes: Mapping[str, Any],
    *,
    team_id: int,
    opponent_id: int,
    home: bool,
    strength: Mapping[int, TeamStrength],
) -> float:
    """The published routes, each bent by what this fixture does to it."""
    adjustment = route_adjustment(strength, team_id, opponent_id, home=home)
    return (
        float(routes["appearance"])
        + float(routes["attacking"]) * adjustment.attacking
        + float(routes["cleanSheet"]) * adjustment.clean_sheet
        + float(routes["bonus"])
        + float(routes["saves"]) * adjustment.saves
        # Conceding points are negative, so a leakier fixture makes them worse.
        + float(routes["conceding"]) * adjustment.conceding
        + float(routes["discipline"])
        + float(routes["defensiveContribution"]) * adjustment.defensive_contribution
    )


def fixture_multiplier(
    routes: Mapping[str, Any],
    *,
    neutral_points: float,
    team_id: int,
    opponent_id: int,
    home: bool,
    strength: Mapping[int, TeamStrength],
) -> float:
    """The same thing as a ratio, for callers holding a scalar record.

    Falls back to one where the neutral projection is zero or negative, because
    a ratio against nothing is not a measurement of anything.
    """
    if neutral_points <= 0:
        return 1.0
    adjusted = fixture_points_from_routes(
        routes,
        team_id=team_id,
        opponent_id=opponent_id,
        home=home,
        strength=strength,
    )
    return adjusted / neutral_points
