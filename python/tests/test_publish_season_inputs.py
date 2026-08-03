"""The season-inputs publisher builds a fixture ladder the browser can trust.

The solver runs in a browser, so nothing on this side of the wire notices if the
ladder is wrong — a mis-shaped one produces a plausible plan built on nonsense.
These run the publisher against fixed payloads and check the arithmetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from fpl_andres.cli import publish_season_inputs

BOOTSTRAP: dict[str, Any] = {
    "teams": [
        {"id": 1, "code": 3, "short_name": "ARS", "name": "Arsenal"},
        {"id": 2, "code": 14, "short_name": "LIV", "name": "Liverpool"},
    ],
    "events": [
        {"id": 1, "deadline_time": "2026-08-21T17:30:00Z", "finished": False},
        {"id": 2, "deadline_time": "2026-08-28T17:30:00Z", "finished": False},
        {"id": 3, "deadline_time": "2026-09-04T17:30:00Z", "finished": True},
    ],
    "elements": [],
}

FIXTURES: list[dict[str, Any]] = [
    {"id": 1, "event": 1, "team_h": 1, "team_a": 2},
    # Gameweek 2 is a blank for Arsenal and a single away game for Liverpool.
    {"id": 2, "event": 2, "team_h": 2, "team_a": 1},
    {"id": 3, "event": 2, "team_h": 1, "team_a": 2},
    {"id": 4, "event": None, "team_h": 1, "team_a": 2},
]

PROJECTIONS: dict[str, Any] = {
    "season": "2025-26",
    "players": [
        {"code": 1001, "expectedPoints": 5.0, "probabilityStart": 0.9},
    ],
    "clubs": [
        {
            "code": 3,
            "shortName": "ARS",
            "attackHome": 1.2,
            "attackAway": 1.0,
            "defenceHome": 0.9,
            "defenceAway": 1.1,
        },
        {
            "code": 14,
            "shortName": "LIV",
            "attackHome": 1.3,
            "attackAway": 1.1,
            "defenceHome": 0.8,
            "defenceAway": 1.0,
        },
    ],
}


def _element(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 11,
        "code": 1001,
        "web_name": "Saka",
        "element_type": 3,
        "team": 1,
        "now_cost": 100,
        "status": "a",
        "chance_of_playing_next_round": None,
        "selected_by_percent": "12.3",
        "transfers_in_event": 0,
        "transfers_out_event": 0,
    }
    base.update(overrides)
    return base


def _run(tmp_path: Path, elements: list[dict[str, Any]]) -> dict[str, Any]:
    bootstrap = {**BOOTSTRAP, "elements": elements}
    projections = tmp_path / "projections.json"
    projections.write_text(json.dumps(PROJECTIONS), encoding="utf-8")
    output = tmp_path / "season-inputs.json"

    def fake_get(url: str) -> Any:
        return bootstrap if "bootstrap" in url else FIXTURES

    with patch.object(publish_season_inputs, "_get", fake_get):
        code = publish_season_inputs.main(
            ["--output", str(output), "--projections", str(projections)]
        )

    assert code == 0
    return json.loads(output.read_text(encoding="utf-8"))


def test_only_unfinished_gameweeks_are_published(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])

    # Gameweek 3 is finished; there is nothing left to plan for it.
    assert payload["events"] == [1, 2]
    assert payload["deadlines"] == [
        "2026-08-21T17:30:00Z",
        "2026-08-28T17:30:00Z",
    ]


def test_the_ladder_has_one_rung_per_club_per_gameweek(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])

    for club, ladder in payload["fixtureLadder"].items():
        assert len(ladder["defensive"]) == len(payload["events"]), club
        assert len(ladder["attacking"]) == len(payload["events"]), club


def test_an_attacker_is_rated_against_the_opponents_defence(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])
    arsenal = payload["fixtureLadder"]["ARS"]

    # Gameweek 1: Arsenal at home to Liverpool, so the attacking rung is
    # Liverpool's away defence.
    assert arsenal["attacking"][0] == pytest.approx(1.0)
    # And the defensive rung is Liverpool's away attack.
    assert arsenal["defensive"][0] == pytest.approx(1.1)


def test_a_double_gameweek_sums_both_fixtures(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])
    arsenal = payload["fixtureLadder"]["ARS"]

    # Gameweek 2 gives Arsenal two games: away then home. A double is worth both.
    assert arsenal["attacking"][1] == pytest.approx(0.8 + 1.0)


def test_a_fixture_with_no_gameweek_is_left_out(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])

    # Fixture 4 has event None — postponed, not yet rescheduled. Counting it
    # against any gameweek would invent a game.
    assert payload["fixtureLadder"]["ARS"]["attacking"][0] == pytest.approx(1.0)


def test_players_without_a_scoring_record_are_dropped(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element(), _element(id=12, code=9999)])

    codes = {player["code"] for player in payload["players"]}
    assert codes == {1001}


def test_unavailable_players_are_dropped(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element(status="i")])

    assert payload["players"] == []


def test_a_season_with_nothing_left_to_play_refuses(tmp_path: Path) -> None:
    finished = {
        **BOOTSTRAP,
        "elements": [_element()],
        "events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z", "finished": True}],
    }
    projections = tmp_path / "projections.json"
    projections.write_text(json.dumps(PROJECTIONS), encoding="utf-8")

    def fake_get(url: str) -> Any:
        return finished if "bootstrap" in url else FIXTURES

    with patch.object(publish_season_inputs, "_get", fake_get):
        code = publish_season_inputs.main(
            [
                "--output",
                str(tmp_path / "out.json"),
                "--projections",
                str(projections),
            ]
        )

    assert code == 1


def test_the_pool_is_trimmed_and_says_so(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])

    assert payload["poolPerPosition"] == publish_season_inputs.POOL_PER_POSITION
    assert payload["schemaVersion"] == publish_season_inputs.SCHEMA_VERSION
    assert payload["recordSeason"] == "2025-26"
