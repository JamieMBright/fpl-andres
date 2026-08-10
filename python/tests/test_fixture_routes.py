"""Applying a fixture to a published projection, route by route.

The bug this replaces: every scoring route was multiplied by one blended
difficulty number, so a defender facing the best attack in the league came out
better than average because the number used was that attack's *strength*.
"""

from __future__ import annotations

import pytest

from fpl_andres.backtesting.fixtures import TeamStrength
from fpl_andres.planning.fixture_routes import fixture_multiplier, fixture_points_from_routes

STRONG = TeamStrength(attack_home=1.4, attack_away=1.3, defence_home=0.7, defence_away=0.8)
WEAK = TeamStrength(attack_home=0.7, attack_away=0.6, defence_home=1.4, defence_away=1.5)
AVERAGE = TeamStrength(attack_home=1.0, attack_away=1.0, defence_home=1.0, defence_away=1.0)
# 1 is strong, 2 is weak, 3 is average.
STRENGTH = {1: STRONG, 2: WEAK, 3: AVERAGE}

# A forward: nearly all of his points come from goals and assists.
FORWARD = {
    "appearance": 2.0,
    "attacking": 3.0,
    "cleanSheet": 0.0,
    "bonus": 0.4,
    "saves": 0.0,
    "conceding": 0.0,
    "yellowCards": -0.08,
    "redCards": -0.01,
    "ownGoals": 0.0,
    "penaltiesMissed": -0.01,
    "defensiveContribution": 0.0,
}
# A defender: a clean sheet, a conceding deduction and defensive contributions.
DEFENDER = {
    "appearance": 2.0,
    "attacking": 0.5,
    "cleanSheet": 1.4,
    "bonus": 0.3,
    "saves": 0.0,
    "conceding": -0.5,
    "yellowCards": -0.09,
    "redCards": -0.01,
    "ownGoals": 0.0,
    "penaltiesMissed": 0.0,
    "defensiveContribution": 0.8,
}


def test_a_forward_prefers_the_weaker_opponent() -> None:
    against_weak = fixture_points_from_routes(
        FORWARD, team_id=3, opponent_id=2, home=True, strength=STRENGTH
    )
    against_strong = fixture_points_from_routes(
        FORWARD, team_id=3, opponent_id=1, home=True, strength=STRENGTH
    )

    assert against_weak > against_strong


def test_a_defender_prefers_the_weaker_opponent_too() -> None:
    """The regression. Facing the league's best attack must not read as a gift
    because that attack's multiplier happens to be the largest number around."""
    against_weak = fixture_points_from_routes(
        DEFENDER, team_id=3, opponent_id=2, home=True, strength=STRENGTH
    )
    against_strong = fixture_points_from_routes(
        DEFENDER, team_id=3, opponent_id=1, home=True, strength=STRENGTH
    )

    assert against_weak > against_strong


def test_the_routes_that_do_not_depend_on_the_opponent_are_left_alone() -> None:
    only_flat = {**FORWARD, "attacking": 0.0}

    adjusted = fixture_points_from_routes(
        only_flat, team_id=3, opponent_id=1, home=True, strength=STRENGTH
    )

    # Appearance, bonus and discipline: 2.0 + 0.4 - 0.1.
    assert adjusted == pytest.approx(2.3)


def test_a_fixture_against_an_average_side_changes_nothing() -> None:
    neutral = sum(float(value) for value in FORWARD.values())

    multiplier = fixture_multiplier(
        FORWARD,
        neutral_points=neutral,
        team_id=3,
        opponent_id=3,
        home=True,
        strength=STRENGTH,
    )

    assert multiplier == pytest.approx(1.0)


def test_a_player_worth_nothing_gets_no_multiplier() -> None:
    # A ratio against zero is not a measurement of anything.
    assert (
        fixture_multiplier(
            FORWARD,
            neutral_points=0.0,
            team_id=3,
            opponent_id=1,
            home=True,
            strength=STRENGTH,
        )
        == 1.0
    )


def test_an_unmeasured_opponent_leaves_the_projection_alone() -> None:
    neutral = sum(float(value) for value in DEFENDER.values())

    multiplier = fixture_multiplier(
        DEFENDER,
        neutral_points=neutral,
        team_id=3,
        opponent_id=99,
        home=True,
        strength=STRENGTH,
    )

    assert multiplier == pytest.approx(1.0)


def test_the_saves_route_pays_more_in_a_harder_fixture() -> None:
    """One difficulty number cannot serve every route: the same hard tie that
    kills a clean sheet raises the shot count."""
    saves_only = {key: 0.0 for key in DEFENDER} | {"saves": 1.0}

    hard = fixture_points_from_routes(
        saves_only, team_id=3, opponent_id=1, home=True, strength=STRENGTH
    )
    easy = fixture_points_from_routes(
        saves_only, team_id=3, opponent_id=2, home=True, strength=STRENGTH
    )

    assert hard > easy


def test_the_clean_sheet_route_runs_the_other_way() -> None:
    sheet_only = {key: 0.0 for key in DEFENDER} | {"cleanSheet": 1.0}

    hard = fixture_points_from_routes(
        sheet_only, team_id=3, opponent_id=1, home=True, strength=STRENGTH
    )
    easy = fixture_points_from_routes(
        sheet_only, team_id=3, opponent_id=2, home=True, strength=STRENGTH
    )

    assert easy > hard
