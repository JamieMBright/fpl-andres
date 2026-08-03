"""Club strength from a fitted Dixon-Coles model.

Goal averaging charges a side for the fixtures it happened to draw. Dixon-Coles
fits attack, defence and home advantage jointly, so the strength it reports is
against an average opponent rather than against the ones already played.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.backtesting.fixtures import strength_from_goal_model
from fpl_andres.models.contracts import FixtureResult
from fpl_andres.models.dixon_coles import DixonColesModel

SEASON = "2025-26"
START = datetime(2025, 8, 15, 12, tzinfo=UTC)


def _result(
    event: int,
    home: int,
    away: int,
    home_goals: int,
    away_goals: int,
) -> FixtureResult:
    kickoff = START + timedelta(days=7 * event)
    return FixtureResult(
        season=SEASON,
        event=min(38, event),
        home_team_id=home,
        away_team_id=away,
        home_goals=home_goals,
        away_goals=away_goals,
        kickoff_time=kickoff,
        data_available_at=kickoff + timedelta(hours=3),
        source_hash=f"sha256:{event * 100 + home:064x}",
    )


def _league() -> list[FixtureResult]:
    """Four sides: 1 is strong, 4 is weak, 2 and 3 are middling."""
    scores = {
        (1, 2): (3, 0),
        (1, 3): (3, 1),
        (1, 4): (4, 0),
        (2, 1): (0, 2),
        (2, 3): (2, 1),
        (2, 4): (3, 0),
        (3, 1): (0, 2),
        (3, 2): (1, 1),
        (3, 4): (2, 0),
        (4, 1): (0, 3),
        (4, 2): (0, 2),
        (4, 3): (1, 2),
    }
    return [
        _result(index + 1, home, away, goals[0], goals[1])
        for index, ((home, away), goals) in enumerate(scores.items())
    ]


@pytest.fixture(scope="module")
def fitted() -> DixonColesModel:
    results = _league()
    return DixonColesModel.fit(
        results,
        season=SEASON,
        as_of=max(result.data_available_at for result in results),
        decay_rate=0.002,
        minimum_matches=3,
        max_iterations=200,
    )


def test_the_model_reports_the_teams_it_saw(fitted: DixonColesModel) -> None:
    assert fitted.teams == (1, 2, 3, 4)


def test_the_strongest_side_attacks_hardest(fitted: DixonColesModel) -> None:
    strength = strength_from_goal_model(fitted, [1, 2, 3, 4])

    assert strength[1].attack_home > strength[4].attack_home
    assert strength[1].attack_away > strength[4].attack_away


def test_the_weakest_side_is_the_leakiest(fitted: DixonColesModel) -> None:
    strength = strength_from_goal_model(fitted, [1, 2, 3, 4])

    # `defence` is a leakiness multiplier: above one concedes more than average.
    assert strength[4].defence_home > strength[1].defence_home
    assert strength[4].defence_away > strength[1].defence_away


def test_the_multipliers_sit_around_one(fitted: DixonColesModel) -> None:
    strength = strength_from_goal_model(fitted, [1, 2, 3, 4])
    attacks = [team.attack_home for team in strength.values()]

    # Normalised against the league, so the average side is about average.
    assert min(attacks) < 1.0 < max(attacks)


def test_a_team_the_fit_never_saw_is_left_out(fitted: DixonColesModel) -> None:
    strength = strength_from_goal_model(fitted, [1, 2, 3, 4, 99])

    assert 99 not in strength


def test_too_few_teams_yields_nothing(fitted: DixonColesModel) -> None:
    # One team has no opponents, so there is no average to measure against.
    assert strength_from_goal_model(fitted, [1]) == {}
