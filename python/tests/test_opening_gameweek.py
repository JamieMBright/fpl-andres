"""Opening gameweek, projected from last season's record.

A new season has no football in it. Without a cross-season read there is nothing
to recommend until several gameweeks have been played, which is exactly when a
manager most wants advice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.fixtures import Fixture
from fpl_andres.backtesting.projector import project_gameweek

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
RETURNING = 101
DEPARTED = 102
DEBUTANT = 103


def last_season() -> SeasonCorpus:
    """One regular starter and one player who will leave the league."""
    corpus = SeasonCorpus(season="2025-26")
    for element_id, code in ((1, RETURNING), (2, DEPARTED)):
        corpus.position_by_element[element_id] = 4
        corpus.team_by_element[element_id] = 1
        corpus.name_by_element[element_id] = f"P{code}"

    for gameweek in range(1, 21):
        corpus.rows_by_gameweek[gameweek] = [
            ElementRow(
                gameweek=gameweek,
                element_id=element_id,
                element_code=code,
                fixture_id=gameweek * 10 + element_id,
                minutes=90,
                started=True,
                goals=1 if gameweek % 2 == 0 else 0,
                assists=0,
                expected_goals=0.5,
                expected_assists=0.2,
                total_points=8 if gameweek % 2 == 0 else 2,
                price_tenths=90,
                selected=500_000,
                kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
                clean_sheets=0,
                saves=0,
                bonus=1,
            )
            for element_id, code in ((1, RETURNING), (2, DEPARTED))
        ]
    return corpus


def new_season() -> SeasonCorpus:
    """No football played. One returning player and one promoted debutant."""
    corpus = SeasonCorpus(season="2026-27")
    # Element ids are reassigned; only the code survives the rollover.
    for element_id, code in ((7, RETURNING), (8, DEBUTANT)):
        corpus.position_by_element[element_id] = 4
        corpus.team_by_element[element_id] = 1 if code == RETURNING else 2
        corpus.name_by_element[element_id] = f"P{code}"
        corpus.code_by_element[element_id] = code
        corpus.price_by_element[element_id] = 90

    corpus.fixtures_by_event[1] = [
        Fixture(
            fixture_id=1,
            event=1,
            team_h=1,
            team_a=2,
            kickoff_time=KICKOFF + timedelta(days=365),
        )
    ]
    return corpus


def test_an_opening_gameweek_projects_from_last_season() -> None:
    projections = project_gameweek(new_season(), 1, previous=last_season())

    returning = [entry for entry in projections if entry.element_id == 7]
    assert len(returning) == 1
    assert returning[0].expected_points > 0


def test_a_debutant_with_no_league_history_is_skipped_not_guessed() -> None:
    projections = project_gameweek(new_season(), 1, previous=last_season())

    assert all(entry.element_id != 8 for entry in projections)


def test_a_departed_player_never_appears_in_the_new_season() -> None:
    projections = project_gameweek(new_season(), 1, previous=last_season())

    # Element 2 played last season but is not in this season's element list.
    assert all(entry.element_id != 2 for entry in projections)


def test_without_last_season_an_opening_gameweek_yields_nothing() -> None:
    assert project_gameweek(new_season(), 1) == []


def test_the_carried_season_is_named_on_the_projection() -> None:
    projections = project_gameweek(new_season(), 1, previous=last_season())
    returning = next(entry for entry in projections if entry.element_id == 7)

    assert returning.rates.carried_season == "2025-26"
    assert returning.rates.carried_weight > 0.0
