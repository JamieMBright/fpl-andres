"""Publishing completed seasons for the analysis scatter.

The live bootstrap carries one season and rewrites it when a new one starts, so
"what did this look like in 2022-23" is a question only this artifact answers.
Every rule below is about not inventing a number the corpus does not hold.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.cli.publish_analysis_seasons import (
    MINIMUM_MINUTES,
    PUBLISHED_MINUTES_FLOOR,
    _aggregate,
    _season,
    build_parser,
)


def _row(
    gameweek: int,
    *,
    minutes: int = 90,
    points: int = 5,
    price: int | None = 50,
    defcon: int | None = None,
    element_id: int = 1,
) -> ElementRow:
    return ElementRow(
        gameweek=gameweek,
        element_id=element_id,
        element_code=100 + element_id,
        fixture_id=gameweek,
        minutes=minutes,
        started=minutes > 0,
        goals=1,
        assists=1,
        expected_goals=0.4,
        expected_assists=0.2,
        total_points=points,
        price_tenths=price,
        selected=None,
        kickoff_time=datetime(2026, 8, 1, tzinfo=UTC),
        clean_sheets=1,
        saves=2,
        bonus=3,
        goals_conceded=1,
        yellow_cards=1,
        red_cards=0,
        defensive_contribution=defcon,
    )


def _corpus(rows: list[ElementRow], *, position: int = 3) -> SeasonCorpus:
    by_gameweek: dict[int, list[ElementRow]] = {}
    for row in rows:
        by_gameweek.setdefault(row.gameweek, []).append(row)
    elements = {row.element_id for row in rows}
    return SeasonCorpus(
        season="2023-24",
        rows_by_gameweek=by_gameweek,
        position_by_element={element_id: position for element_id in elements},
        team_by_element={element_id: 1 for element_id in elements},
        name_by_element={element_id: f"Player {element_id}" for element_id in elements},
        code_by_element={element_id: 100 + element_id for element_id in elements},
        short_name_by_team={1: "ARS"},
    )


def test_totals_are_summed_over_the_gameweeks_held() -> None:
    aggregate = _aggregate([_row(1), _row(2), _row(3)])

    assert aggregate["minutes"] == 270
    assert aggregate["appearances"] == 3
    assert aggregate["totalPoints"] == 15
    assert aggregate["goals"] == 3
    assert aggregate["bonus"] == 9


def test_a_blank_is_not_an_appearance() -> None:
    """Named on the bench and unused is a gameweek, not a match played."""
    aggregate = _aggregate([_row(1), _row(2, minutes=0, points=0)])

    assert aggregate["appearances"] == 1
    assert aggregate["minutes"] == 90


def test_the_price_published_is_what_he_closed_the_window_at() -> None:
    """Today's price against a 2021-22 return is a category error."""
    aggregate = _aggregate([_row(1, price=50), _row(2, price=55), _row(3, price=61)])

    assert aggregate["priceTenths"] == 61


def test_a_rate_over_too_few_minutes_is_withheld_rather_than_zeroed() -> None:
    """A per-90 from under a match is a small sample wearing a big number."""
    aggregate = _aggregate([_row(1, minutes=MINIMUM_MINUTES - 1, defcon=2)])

    assert aggregate["defensiveContributionPer90"] is None


def test_a_rate_is_published_once_there_are_minutes_behind_it() -> None:
    aggregate = _aggregate([_row(1, minutes=90, defcon=10), _row(2, minutes=90, defcon=8)])

    assert aggregate["defensiveContributionPer90"] == pytest.approx(9.0)


def test_expected_goal_involvements_are_the_two_parts_added() -> None:
    aggregate = _aggregate([_row(1), _row(2)])

    assert aggregate["expectedGoals"] == pytest.approx(0.8)
    assert aggregate["expectedAssists"] == pytest.approx(0.4)
    assert aggregate["expectedGoalInvolvements"] == pytest.approx(1.2)


def test_a_player_nobody_could_have_picked_is_left_out() -> None:
    """Under five matches is weight in the file without information in it."""
    season = _season(_corpus([_row(1), _row(2)]))

    assert season["players"] == []


def test_a_player_with_enough_football_is_published() -> None:
    rows = [_row(event) for event in range(1, 7)]

    season = _season(_corpus(rows))

    assert len(season["players"]) == 1
    player = season["players"][0]
    assert player["code"] == 101
    assert player["club"] == "ARS"
    assert player["position"] == "MID"
    assert player["minutes"] >= PUBLISHED_MINUTES_FLOOR


def test_gameweek_rows_are_ordered_tuples_and_omit_the_blanks() -> None:
    """Repeating the key names thirty-eight times a player is megabytes."""
    rows = [_row(event) for event in range(1, 7)] + [_row(7, minutes=0, points=0)]

    player = _season(_corpus(rows))["players"][0]

    assert player["byEvent"] == [[event, 90, 5, 50] for event in range(1, 7)]


def test_a_manager_is_not_a_footballer() -> None:
    """Position five is the manager chip, which has no place on the scatter."""
    season = _season(_corpus([_row(event) for event in range(1, 7)], position=5))

    assert season["players"] == []


def test_the_artifact_round_trips_as_json() -> None:
    season = _season(_corpus([_row(event) for event in range(1, 7)]))

    assert json.loads(json.dumps(season))["season"] == "2023-24"


def test_the_parser_defaults_to_the_static_asset_the_page_fetches() -> None:
    args = build_parser().parse_args([])

    assert Path(args.output).name == "analysis-seasons.json"
    assert "2025-26" in args.seasons
