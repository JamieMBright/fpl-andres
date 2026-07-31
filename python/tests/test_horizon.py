"""Horizon projection: doubles, blanks and the planning ladder.

A blank gameweek must project zero rather than a normal week, and a double must
pay twice. Getting either wrong is invisible in a season average and decisive in
the week it happens.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.fixtures import Fixture
from fpl_andres.backtesting.projector import project_gameweek, project_horizon

KICKOFF = datetime(2024, 8, 17, 14, 0, tzinfo=UTC)
PLAYER = 1
TEAM = 1
OPPONENT = 2


def corpus_with(schedule: dict[int, list[tuple[int, int]]]) -> SeasonCorpus:
    """Ten gameweeks of steady returns, with a caller-supplied fixture list."""
    corpus = SeasonCorpus(season="2024-25")
    for element_id, team_id in ((PLAYER, TEAM), (2, OPPONENT), (3, TEAM), (4, OPPONENT)):
        corpus.position_by_element[element_id] = 4
        corpus.team_by_element[element_id] = team_id
        corpus.name_by_element[element_id] = f"P{element_id}"

    for gameweek in range(1, 11):
        corpus.rows_by_gameweek[gameweek] = [
            ElementRow(
                gameweek=gameweek,
                element_id=element_id,
                element_code=element_id,
                fixture_id=gameweek * 10 + element_id,
                minutes=90,
                started=True,
                goals=1,
                assists=0,
                expected_goals=0.5,
                expected_assists=0.2,
                total_points=6,
                price_tenths=70,
                selected=1000,
                kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
                clean_sheets=0,
                saves=0,
                bonus=1,
            )
            for element_id in corpus.position_by_element
        ]

    fixture_id = 1
    for event, pairings in schedule.items():
        for home, away in pairings:
            corpus.fixtures_by_event.setdefault(event, []).append(
                Fixture(
                    fixture_id=fixture_id,
                    event=event,
                    team_h=home,
                    team_a=away,
                    kickoff_time=KICKOFF + timedelta(days=7 * event),
                    team_h_score=1 if event < 8 else None,
                    team_a_score=1 if event < 8 else None,
                    finished=event < 8,
                )
            )
            fixture_id += 1
    return corpus


def points_for(projections: list, element_id: int) -> float:
    for projection in projections:
        if projection.element_id == element_id:
            return projection.expected_points
    raise AssertionError(f"element {element_id} was not projected")


def test_a_blank_gameweek_projects_zero() -> None:
    schedule = {event: [(TEAM, OPPONENT)] for event in range(1, 10)}
    schedule[9] = []
    corpus = corpus_with(schedule)

    assert points_for(project_gameweek(corpus, 9), PLAYER) == 0.0


def test_a_double_gameweek_pays_about_twice() -> None:
    single = {event: [(TEAM, OPPONENT)] for event in range(1, 10)}
    double = dict(single)
    double[9] = [(TEAM, OPPONENT), (OPPONENT, TEAM)]

    one = points_for(project_gameweek(corpus_with(single), 9), PLAYER)
    two = points_for(project_gameweek(corpus_with(double), 9), PLAYER)

    assert one > 0
    assert 1.8 < two / one < 2.2


def test_the_ladder_is_cumulative_and_counts_its_fixtures() -> None:
    corpus = corpus_with({event: [(TEAM, OPPONENT)] for event in range(1, 11)})

    projection = next(
        entry for entry in project_horizon(corpus, 8, horizons=(1, 3)) if entry.element_id == PLAYER
    )

    assert projection.points_over(3) > projection.points_over(1)
    assert projection.fixtures_by_horizon == {1: 1, 3: 3}


def test_a_blank_inside_the_horizon_lowers_the_longer_view() -> None:
    steady = {event: [(TEAM, OPPONENT)] for event in range(1, 11)}
    disrupted = dict(steady)
    disrupted[9] = []

    def three_week_view(schedule: dict[int, list[tuple[int, int]]]) -> float:
        projections = project_horizon(corpus_with(schedule), 8, horizons=(1, 3))
        entry = next(item for item in projections if item.element_id == PLAYER)
        return entry.points_over(3)

    assert three_week_view(disrupted) < three_week_view(steady)


def test_points_per_million_needs_a_price() -> None:
    corpus = corpus_with({event: [(TEAM, OPPONENT)] for event in range(1, 11)})

    projection = next(
        entry for entry in project_horizon(corpus, 8, horizons=(1,)) if entry.element_id == PLAYER
    )

    assert projection.price_tenths == 70
    per_million = projection.points_per_million(1)
    assert per_million is not None
    assert per_million == projection.points_over(1) / 7.0
