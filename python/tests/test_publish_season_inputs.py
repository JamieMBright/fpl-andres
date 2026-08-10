"""The season-inputs publisher builds a fixture ladder the browser can trust.

The solver runs in a browser, so nothing on this side of the wire notices if the
ladder is wrong — a mis-shaped one produces a plausible plan built on nonsense.
These run the publisher against fixed payloads and check the arithmetic.
"""

from __future__ import annotations

import json
import math
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
    # The controlling rules the browser solver now reads rather than declares.
    "game_settings": {
        "squad_squadsize": 15,
        "squad_squadplay": 11,
        "squad_team_limit": 3,
        "transfers_cap": 20,
        "max_extra_free_transfers": 4,
    },
    "events": [
        {"id": 1, "deadline_time": "2026-08-21T17:30:00Z", "finished": False},
        {"id": 2, "deadline_time": "2026-08-28T17:30:00Z", "finished": False},
        {"id": 3, "deadline_time": "2026-09-04T17:30:00Z", "finished": True},
    ],
    "elements": [],
}

#: A route split that sums to the projection beside it.
ROUTES: dict[str, float] = {
    "appearance": 2.0,
    "attacking": 2.0,
    "cleanSheet": 0.5,
    "bonus": 0.2,
    "saves": 0.0,
    "conceding": -0.2,
    "yellowCards": -0.08,
    "redCards": -0.01,
    "ownGoals": 0.0,
    "penaltiesMissed": -0.01,
    "defensiveContribution": 0.6,
}

FIXTURES: list[dict[str, Any]] = [
    {"id": 1, "event": 1, "team_h": 1, "team_a": 2, "kickoff_time": "2026-08-22T14:00:00Z"},
    # Gameweek 2 is a blank for Arsenal and a single away game for Liverpool.
    {"id": 2, "event": 2, "team_h": 2, "team_a": 1, "kickoff_time": "2026-08-29T14:00:00Z"},
    {"id": 3, "event": 2, "team_h": 1, "team_a": 2, "kickoff_time": "2026-08-29T16:30:00Z"},
    {"id": 4, "event": None, "team_h": 1, "team_a": 2, "kickoff_time": None},
]

PROJECTIONS: dict[str, Any] = {
    "season": "2025-26",
    "players": [
        {
            "code": 1001,
            "expectedPoints": 5.0,
            "probabilityStart": 0.9,
            # 0.34 * 5 + 0.1 * 3 = 2.0, the attacking route below.
            "expectedGoals": 0.34,
            "expectedAssists": 0.1,
            "routes": ROUTES,
        },
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


def _run(
    tmp_path: Path,
    elements: list[dict[str, Any]],
    odds: dict[str, Any] | None = None,
    fixture_odds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bootstrap = {**BOOTSTRAP, "elements": elements}
    projections = tmp_path / "projections.json"
    projections.write_text(json.dumps(PROJECTIONS), encoding="utf-8")
    opening = tmp_path / "opening-squad.json"
    opening.write_text(json.dumps({"picks": []}), encoding="utf-8")
    output = tmp_path / "season-inputs.json"
    player_odds = tmp_path / "player-odds.json"
    if odds is not None:
        player_odds.write_text(json.dumps(odds), encoding="utf-8")
    match_odds = tmp_path / "fixture-odds.json"
    if fixture_odds is not None:
        match_odds.write_text(json.dumps(fixture_odds), encoding="utf-8")

    def fake_get(url: str) -> Any:
        return bootstrap if "bootstrap" in url else FIXTURES

    with patch.object(publish_season_inputs, "_get", fake_get):
        code = publish_season_inputs.main(
            [
                "--output",
                str(output),
                "--projections",
                str(projections),
                "--opening-squad",
                str(opening),
                "--player-odds",
                str(player_odds),
                "--fixture-odds",
                str(match_odds),
            ]
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


def _odds(**overrides: Any) -> dict[str, Any]:
    row = {
        "element_id": 11,
        "quoted_name": "Bukayo Saka",
        "kickoff": "2026-08-22T14:00:00Z",
        "anytime_goal": 0.5,
        "anytime_assist": 0.2,
    }
    row.update(overrides)
    return {"season": "2026-27", "players": [row]}


def _attacking(payload: dict[str, Any]) -> float:
    return float(payload["players"][0]["routes"]["attacking"])


def payload_multiplier(payload: dict[str, Any]) -> float:
    """Arsenal's attacking rung in gameweek one, the divisor under test."""
    return float(payload["fixtureLadder"]["ARS"]["attacking"][0])


class TestTheMarketPricingTheAttackingRoute:
    """A bookmaker's view of a player, folded into the route it speaks to.

    The blend that used to live here read a projection field the projector never
    published, so it returned nothing for everybody and nothing said so. These
    exist so that cannot happen quietly again: each one asserts the number moved.
    """

    def test_a_quoted_player_is_rated_above_his_record(self, tmp_path: Path) -> None:
        # Evens to score is far above the 0.34 the record projects.
        recorded = _attacking(_run(tmp_path, [_element()]))
        blended = _attacking(_run(tmp_path, [_element()], odds=_odds()))

        assert blended > recorded

    def test_a_player_the_book_ignored_keeps_his_record(self, tmp_path: Path) -> None:
        recorded = _attacking(_run(tmp_path, [_element()]))
        other = _attacking(_run(tmp_path, [_element()], odds=_odds(element_id=99)))

        assert other == recorded

    def test_a_scorer_price_alone_moves_goals_and_leaves_assists(self, tmp_path: Path) -> None:
        """Assist markets open on fewer fixtures, and half a view beats none."""
        recorded = _attacking(_run(tmp_path, [_element()]))
        both = _attacking(_run(tmp_path, [_element()], odds=_odds()))
        goals_only = _attacking(_run(tmp_path, [_element()], odds=_odds(anytime_assist=None)))

        assert recorded < goals_only < both

    def test_the_fixture_is_divided_back_out_before_publishing(self, tmp_path: Path) -> None:
        """The route is per average opponent; the browser applies the fixture.

        Publishing the quote as it stands would apply Arsenal's gameweek one
        multiplier twice -- once by the book and once by the solver. So the
        arithmetic is asserted in full rather than by direction: the market's
        Poisson rate, divided by the rung the solver will multiply it back by.
        """
        payload = _run(tmp_path, [_element()], odds=_odds())
        rung = payload_multiplier(payload)
        weight = 0.35
        goals = (1 - weight) * 0.34 + weight * -math.log(0.5) / rung
        assists = (1 - weight) * 0.1 + weight * -math.log(0.8) / rung

        assert _attacking(payload) == pytest.approx(goals * 5 + assists * 3, abs=0.001)

    def test_a_double_gameweek_is_left_to_the_record(self, tmp_path: Path) -> None:
        """Its rung sums two fixtures and the book priced one of them.

        Dividing a single fixture's quote by the pair's multiplier would halve
        the market's view of him, which is worse than not reading it.
        """
        recorded = _attacking(_run(tmp_path, [_element()]))
        doubled = _attacking(
            _run(tmp_path, [_element()], odds=_odds(kickoff="2026-08-29T16:30:00Z"))
        )

        assert doubled == recorded

    def test_a_price_for_a_day_nobody_plays_is_ignored(self, tmp_path: Path) -> None:
        recorded = _attacking(_run(tmp_path, [_element()]))
        stray = _attacking(_run(tmp_path, [_element()], odds=_odds(kickoff="2026-08-25T14:00:00Z")))

        assert stray == recorded

    def test_a_defender_is_paid_more_for_the_same_quoted_goal(self, tmp_path: Path) -> None:
        midfielder = _attacking(_run(tmp_path, [_element()], odds=_odds()))
        defender = _attacking(_run(tmp_path, [_element(element_type=2)], odds=_odds()))

        assert defender > midfielder


def _match_odds(**overrides: Any) -> dict[str, Any]:
    fixture = {
        "kickoff": "2026-08-22T14:00:00+00:00",
        "home": "ARS",
        "away": "LIV",
        "homeExpectedGoals": 2.4,
        "awayExpectedGoals": 0.6,
        "homeCleanSheet": 0.55,
        "awayCleanSheet": 0.09,
        "drawResidual": 0.0,
        "priceSource": "average",
    }
    fixture.update(overrides)
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-08-10T00:00:00+00:00",
        "season": "2026-27",
        "source": "football-data.co.uk",
        "priceTiming": "pre-match",
        "evidenceLevel": "observed",
        "fixtures": [fixture],
    }


def _rung(payload: dict[str, Any], club: str, route: str, slot: int) -> float:
    return float(payload["fixtureLadder"][club][route][slot])


class TestTheMarketPricingAFixture:
    """Clean sheets and goals conceded, taken off the match market.

    Four seasons of this artifact had been ingested, derived and committed
    while nothing read a single number out of it. Between them the two routes
    are about a sixth of every point FPL awards, and the fitted strength they
    were coming from is a shrunk season-long ratio that cannot know who is
    injured on the day.
    """

    def test_an_easy_fixture_lifts_the_clean_sheet_above_the_fitted_one(
        self, tmp_path: Path
    ) -> None:
        fitted = _run(tmp_path, [_element()])
        priced = _run(tmp_path, [_element()], fixture_odds=_match_odds())

        # Arsenal are priced to concede 0.6 against a round averaging 1.5.
        assert _rung(priced, "ARS", "defensive", 0) > _rung(fitted, "ARS", "defensive", 0)
        assert _rung(priced, "ARS", "conceding", 0) < _rung(fitted, "ARS", "conceding", 0)

    def test_the_opponent_gets_the_other_side_of_the_same_price(self, tmp_path: Path) -> None:
        priced = _run(tmp_path, [_element()], fixture_odds=_match_odds())

        assert _rung(priced, "LIV", "defensive", 0) < _rung(priced, "ARS", "defensive", 0)
        assert _rung(priced, "LIV", "conceding", 0) > _rung(priced, "ARS", "conceding", 0)

    def test_a_side_under_pressure_is_given_more_saves(self, tmp_path: Path) -> None:
        priced = _run(tmp_path, [_element()], fixture_odds=_match_odds())

        assert _rung(priced, "LIV", "saves", 0) > _rung(priced, "ARS", "saves", 0)

    def test_a_gameweek_the_market_did_not_price_keeps_the_fitted_rung(
        self, tmp_path: Path
    ) -> None:
        fitted = _run(tmp_path, [_element()])
        priced = _run(tmp_path, [_element()], fixture_odds=_match_odds())

        # Gameweek two is a double for both clubs and is priced by nobody.
        assert _rung(priced, "ARS", "defensive", 1) == _rung(fitted, "ARS", "defensive", 1)

    def test_an_absent_artifact_changes_nothing(self, tmp_path: Path) -> None:
        """The state between seasons, and any week the ingest has not run."""
        fitted = _run(tmp_path, [_element()])
        absent = _run(tmp_path, [_element()], fixture_odds=None)

        assert absent["fixtureLadder"] == fitted["fixtureLadder"]

    def test_a_double_gameweek_is_left_to_the_fitted_strength(self, tmp_path: Path) -> None:
        """One price cannot fill a rung that sums two fixtures."""
        fitted = _run(tmp_path, [_element()])
        doubled = _run(
            tmp_path,
            [_element()],
            fixture_odds={
                **_match_odds(),
                "fixtures": [
                    {**_match_odds()["fixtures"][0], "kickoff": "2026-08-29T14:00:00+00:00"},
                    {
                        **_match_odds()["fixtures"][0],
                        "kickoff": "2026-08-29T16:30:00+00:00",
                        "home": "LIV",
                        "away": "ARS",
                    },
                ],
            },
        )

        assert _rung(doubled, "ARS", "defensive", 1) == _rung(fitted, "ARS", "defensive", 1)

    def test_a_projection_with_no_split_to_blend_against_is_refused(self, tmp_path: Path) -> None:
        """The exact shape the previous blend failed silently in.

        It read a projection field the projector never published and took the
        absence as "no market view", so it returned nothing for everybody and
        nothing said so.
        """
        stale = {
            **PROJECTIONS,
            "players": [
                {key: value for key, value in row.items() if not key.startswith("expected")}
                | {"expectedPoints": row["expectedPoints"]}
                for row in PROJECTIONS["players"]
            ],
        }
        projections = tmp_path / "projections.json"
        projections.write_text(json.dumps(stale), encoding="utf-8")
        opening = tmp_path / "opening-squad.json"
        opening.write_text(json.dumps({"picks": []}), encoding="utf-8")
        player_odds = tmp_path / "player-odds.json"
        player_odds.write_text(json.dumps(_odds()), encoding="utf-8")
        bootstrap = {**BOOTSTRAP, "elements": [_element()]}

        def fake_get(url: str) -> Any:
            return bootstrap if "bootstrap" in url else FIXTURES

        with (
            patch.object(publish_season_inputs, "_get", fake_get),
            pytest.raises(ValueError, match="publishes no expectedGoals"),
        ):
            publish_season_inputs.main(
                [
                    "--output",
                    str(tmp_path / "out.json"),
                    "--projections",
                    str(projections),
                    "--opening-squad",
                    str(opening),
                    "--player-odds",
                    str(player_odds),
                ]
            )


def test_the_ladder_has_one_rung_per_club_per_gameweek(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])

    for club, ladder in payload["fixtureLadder"].items():
        assert len(ladder["defensive"]) == len(payload["events"]), club
        assert len(ladder["attacking"]) == len(payload["events"]), club


def test_an_attacker_is_rated_against_the_opponents_defence(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])
    arsenal = payload["fixtureLadder"]["ARS"]

    # Gameweek 1: Arsenal at home to Liverpool. Goals flow from Arsenal's home
    # attack meeting Liverpool's away leakiness, so 1.2 x 1.0.
    assert arsenal["attacking"][0] == pytest.approx(1.2)


def test_a_defender_is_rated_inversely_to_the_opponents_attack(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])
    arsenal = payload["fixtureLadder"]["ARS"]

    # A clean sheet gets *harder* as the pressure on it rises, so it is the
    # inverse of Liverpool's away attack meeting Arsenal's home leakiness:
    # 1 / (1.1 x 0.9). Applied the other way round it said a defender's best
    # fixture was against the league's best attack, and the plan
    # triple-captained Gabriel away at Manchester City for it.
    #
    # Three decimals, which is what the artifact carries: the fourth is well
    # past what a projection can support and it is paid for in every byte the
    # browser downloads.
    assert arsenal["defensive"][0] == pytest.approx(1.0 / (1.1 * 0.9), abs=1e-3)


def test_a_double_gameweek_sums_both_fixtures(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])
    arsenal = payload["fixtureLadder"]["ARS"]

    # Gameweek 2 gives Arsenal two games: away then home. A double is worth both.
    # Away, 1.0 x 0.8; at home, 1.2 x 1.0.
    assert arsenal["attacking"][1] == pytest.approx(0.8 + 1.2)


def test_a_fixture_with_no_gameweek_is_left_out(tmp_path: Path) -> None:
    payload = _run(tmp_path, [_element()])

    # Fixture 4 has event None — postponed, not yet rescheduled. Counting it
    # against any gameweek would invent a game.
    assert payload["fixtureLadder"]["ARS"]["attacking"][0] == pytest.approx(1.2)


def test_players_without_a_scoring_record_are_kept_on_a_role_prior(
    tmp_path: Path,
) -> None:
    # Somebody will own a promoted-club debutant, so he has to be pickable. The
    # numbers are what players of his position and depth rank do, and the row
    # says so rather than passing a prior off as a measurement.
    payload = _run(tmp_path, [_element(), _element(id=12, code=9999)])

    by_code = {player["code"]: player for player in payload["players"]}
    assert set(by_code) == {1001, 9999}
    assert by_code[1001]["rated"] is True
    assert by_code[9999]["rated"] is False
    assert by_code[9999]["basePoints"] == by_code[1001]["basePoints"]


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


def test_the_opening_squad_survives_the_trim(tmp_path: Path) -> None:
    """The browser solve starts from the published squad, so a cheap bench
    enabler who would never make a top-forty-by-points cut still has to be in
    the pool. Leaving him out started the solve with fourteen men."""
    bootstrap = {**BOOTSTRAP, "elements": [_element(), _element(id=12, code=1002)]}
    projections = tmp_path / "projections.json"
    projections.write_text(
        json.dumps(
            {
                **PROJECTIONS,
                "players": [
                    {
                        "code": 1001,
                        "expectedPoints": 5.0,
                        "probabilityStart": 0.9,
                        "routes": ROUTES,
                    },
                    {
                        "code": 1002,
                        "expectedPoints": 0.1,
                        "probabilityStart": 0.4,
                        "routes": ROUTES,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    opening = tmp_path / "opening-squad.json"
    opening.write_text(json.dumps({"picks": [{"code": 1002}]}), encoding="utf-8")
    output = tmp_path / "season-inputs.json"

    def fake_get(url: str) -> Any:
        return bootstrap if "bootstrap" in url else FIXTURES

    with (
        patch.object(publish_season_inputs, "_get", fake_get),
        patch.object(publish_season_inputs, "POOL_PER_POSITION", 1),
    ):
        assert (
            publish_season_inputs.main(
                [
                    "--output",
                    str(output),
                    "--projections",
                    str(projections),
                    "--opening-squad",
                    str(opening),
                ]
            )
            == 0
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert {player["code"] for player in payload["players"]} == {1001, 1002}


def test_an_opening_squad_player_the_game_no_longer_lists_is_refused(tmp_path: Path) -> None:
    opening = tmp_path / "opening-squad.json"
    opening.write_text(json.dumps({"picks": [{"code": 424242}]}), encoding="utf-8")
    projections = tmp_path / "projections.json"
    projections.write_text(json.dumps(PROJECTIONS), encoding="utf-8")
    bootstrap = {**BOOTSTRAP, "elements": [_element()]}

    def fake_get(url: str) -> Any:
        return bootstrap if "bootstrap" in url else FIXTURES

    with (
        patch.object(publish_season_inputs, "_get", fake_get),
        pytest.raises(ValueError, match="missing from the solver pool"),
    ):
        publish_season_inputs.main(
            [
                "--output",
                str(tmp_path / "out.json"),
                "--projections",
                str(projections),
                "--opening-squad",
                str(opening),
            ]
        )
