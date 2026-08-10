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

import math
from collections.abc import Mapping, Sequence
from typing import Any

from fpl_andres.backtesting.fixtures import TeamStrength, route_adjustment

__all__ = [
    "ROUTE_KEYS",
    "fixture_difficulty",
    "fixture_multiplier",
    "fixture_points_from_routes",
    "published_strength",
]

# A newly promoted side has no Premier League record, so there is nothing to
# rate it on from results. FPL publishes its own strength for every club,
# including the promoted ones, and `published_strength` below reads it. This
# constant is the last resort for a bootstrap that carries no strength at all:
# assumed soft, because promoted sides have finished bottom three in most
# recent seasons, so it is the honest prior rather than a flattering one.
# `_data_gaps` names every club it applies to.
PROMOTED_ATTACK = 0.80
PROMOTED_DEFENCE = 1.25
PROMOTED_STRENGTH = TeamStrength(
    attack_home=PROMOTED_ATTACK,
    attack_away=PROMOTED_ATTACK,
    defence_home=PROMOTED_DEFENCE,
    defence_away=PROMOTED_DEFENCE,
)

#: FPL's own strength fields, which it publishes for every club in the game.
_PUBLISHED_FIELDS = (
    "strength_attack_home",
    "strength_attack_away",
    "strength_defence_home",
    "strength_defence_away",
)


def published_strength(
    team: Mapping[str, object],
    teams: Sequence[Mapping[str, object]],
) -> TeamStrength | None:
    """
    One club rated on FPL's published strength, against the league's own mean.

    A hand-picked constant for every promoted side is a default standing in for
    a source that exists: FPL rates all twenty clubs before a ball is kicked,
    promoted ones included, and those numbers are already ingested and were
    read by nothing.

    Attack is the club over the league mean, so above one is a stronger attack.
    Defence is inverted -- FPL's higher is better and this module's higher is
    leakier -- so the league mean over the club. Returns None when the bootstrap
    carries no strength, which is the one case the constant above is for.
    """
    means: dict[str, float] = {}
    for field_name in _PUBLISHED_FIELDS:
        values: list[float] = []
        for other in teams:
            reading = other.get(field_name)
            if isinstance(reading, (int, float)) and float(reading) > 0:
                values.append(float(reading))
        if not values:
            return None
        means[field_name] = sum(values) / len(values)

    read: dict[str, float] = {}
    for field_name in _PUBLISHED_FIELDS:
        value = team.get(field_name)
        if not isinstance(value, (int, float)) or float(value) <= 0:
            return None
        read[field_name] = float(value)

    return TeamStrength(
        attack_home=read["strength_attack_home"] / means["strength_attack_home"],
        attack_away=read["strength_attack_away"] / means["strength_attack_away"],
        defence_home=means["strength_defence_home"] / read["strength_defence_home"],
        defence_away=means["strength_defence_away"] / read["strength_defence_away"],
    )


# Difficulty is a ratio, so it is read on a log scale: twice as easy and half as
# easy sit the same distance either side of even. The scale is chosen so a tie
# two and a half times easier than average lands on 1 and the reverse lands on
# 5, which is the full published range.
DIFFICULTY_LOG_SCALE = 2.18
DIFFICULTY_MIDPOINT = 3.0
DIFFICULTY_HARDEST = 5.0
DIFFICULTY_EASIEST = 1.0


def fixture_difficulty(
    games: Sequence[tuple[int, bool]],
    team_id: int,
    strength: Mapping[int, TeamStrength],
) -> float | None:
    """Where this tie sits between one and five, to a tenth.

    Rated on both halves of the fixture, at the venue it is played: what this
    side is likely to score against that opponent, over what it is likely to
    concede. A blank is None rather than three, because there is no fixture to
    be difficult.

    Continuous rather than banded. Five buckets threw away most of what the
    route model had measured and made a run of fixtures look flat when it was
    not: every Arsenal tie came out a 1 because the whole top of the range
    collapsed into one number.
    """
    if team_id not in strength:
        return None
    rated = [
        route_adjustment(
            strength,
            team_id,
            opponent,
            home=home,
        )
        if opponent in strength
        else route_adjustment(
            {**strength, opponent: PROMOTED_STRENGTH},
            team_id,
            opponent,
            home=home,
        )
        for opponent, home in games
    ]
    if not rated:
        return None
    # A double gameweek averages its fixtures rather than summing them: two hard
    # games are still hard, not twice as hard.
    ease = sum(adjustment.attacking / adjustment.conceding for adjustment in rated) / len(rated)
    if ease <= 0:
        return DIFFICULTY_HARDEST
    rating = DIFFICULTY_MIDPOINT - DIFFICULTY_LOG_SCALE * math.log(ease)
    return round(min(DIFFICULTY_HARDEST, max(DIFFICULTY_EASIEST, rating)), 1)


# The published route names, and whether a fixture moves them at all. Appearance
# points, bonus and the four discipline routes do not depend on who the opponent
# is -- not because a booking is opponent-blind, but because nothing here
# measures that yet. A card price will.
ROUTE_KEYS = (
    "appearance",
    "attacking",
    "cleanSheet",
    "bonus",
    "saves",
    "conceding",
    "yellowCards",
    "redCards",
    "ownGoals",
    "penaltiesMissed",
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
        + float(routes["yellowCards"])
        + float(routes["redCards"])
        + float(routes["ownGoals"])
        + float(routes["penaltiesMissed"])
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
