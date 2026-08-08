"""The half of bootstrap-static that had no contract.

`validate_published_bootstrap_contract` reads `game_settings`,
`game_config`, `element_types` and `chips` field by field. It never looked at
`elements`, `teams` or `events` -- the three lists every publisher actually
indexes into.

`bootstrap.py` validates a player's own fields, but a per-row model cannot see
the payload around it. Each case below is something only a whole-payload check
can catch, and each one currently resolves as a `KeyError` inside a publisher or
as silently wrong output.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from fpl_andres.rules import RulesContractError, validate_published_squad_contract


def _team(team_id: int) -> dict[str, Any]:
    return {
        "id": team_id,
        "code": 100 + team_id,
        "name": f"Club {team_id}",
        "short_name": f"C{team_id:02d}",
    }


def _element(element_id: int, *, team: int = 1, element_type: int = 3) -> dict[str, Any]:
    return {
        "id": element_id,
        "code": 900_000 + element_id,
        "team": team,
        "element_type": element_type,
    }


def _event(event_id: int) -> dict[str, Any]:
    return {
        "id": event_id,
        "deadline_time": f"2025-08-{event_id:02d}T11:00:00Z",
        "finished": False,
    }


def _bootstrap() -> dict[str, Any]:
    return {
        "element_types": [{"id": position} for position in (1, 2, 3, 4)],
        "teams": [_team(team_id) for team_id in range(1, 21)],
        "elements": [_element(element_id) for element_id in range(1, 6)],
        "events": [_event(event_id) for event_id in range(1, 39)],
    }


class TestAValidPayloadPasses:
    def test_the_baseline_fixture_is_accepted(self) -> None:
        validate_published_squad_contract(_bootstrap())


class TestTheTwentyClubs:
    def test_a_missing_club_is_refused(self) -> None:
        payload = _bootstrap()
        payload["teams"] = payload["teams"][:19]
        with pytest.raises(RulesContractError, match="expected 20 teams, found 19"):
            validate_published_squad_contract(payload)

    def test_a_duplicate_short_name_is_refused(self) -> None:
        # `publish_season_inputs` keys ladder, ratings and opponents by short
        # name. A duplicate does not raise there; the second club overwrites the
        # first and the published ladder quietly loses a team.
        payload = _bootstrap()
        payload["teams"][7]["short_name"] = payload["teams"][3]["short_name"]
        with pytest.raises(RulesContractError, match="duplicate team short name"):
            validate_published_squad_contract(payload)

    def test_a_duplicate_code_is_refused(self) -> None:
        # Strength is joined by code. A duplicate assigns one club's attack and
        # defence to another.
        payload = _bootstrap()
        payload["teams"][7]["code"] = payload["teams"][3]["code"]
        with pytest.raises(RulesContractError, match="duplicate team code"):
            validate_published_squad_contract(payload)

    def test_a_club_without_a_name_is_refused(self) -> None:
        payload = _bootstrap()
        del payload["teams"][0]["name"]
        with pytest.raises(RulesContractError, match=r"missing required rule: teams\[0\].name"):
            validate_published_squad_contract(payload)


class TestEveryPlayerPointsSomewhere:
    def test_a_player_at_a_club_that_does_not_exist_is_refused(self) -> None:
        payload = _bootstrap()
        payload["elements"][2]["team"] = 21
        with pytest.raises(RulesContractError, match=r"elements\[2\].team names no club: 21"):
            validate_published_squad_contract(payload)

    def test_an_undeclared_position_is_refused(self) -> None:
        # FPL has shipped a fifth element type before. This does not refuse the
        # type -- it insists the type was declared in element_types, so a
        # publisher skipping it is a decision rather than an accident.
        payload = _bootstrap()
        payload["elements"][1]["element_type"] = 5
        with pytest.raises(RulesContractError, match="element_type is undeclared: 5"):
            validate_published_squad_contract(payload)

    def test_a_declared_fifth_position_is_accepted(self) -> None:
        payload = _bootstrap()
        payload["element_types"].append({"id": 5})
        payload["elements"][1]["element_type"] = 5
        validate_published_squad_contract(payload)

    def test_a_duplicate_element_id_is_refused(self) -> None:
        payload = _bootstrap()
        payload["elements"].append(copy.deepcopy(payload["elements"][0]))
        with pytest.raises(RulesContractError, match="duplicate element id: 1"):
            validate_published_squad_contract(payload)

    def test_an_empty_squad_is_refused(self) -> None:
        payload = _bootstrap()
        payload["elements"] = []
        with pytest.raises(RulesContractError, match="bootstrap carries no elements"):
            validate_published_squad_contract(payload)


class TestThirtyEightGameweeksInOrder:
    def test_a_short_season_is_refused(self) -> None:
        payload = _bootstrap()
        payload["events"] = payload["events"][:37]
        with pytest.raises(RulesContractError, match="expected 38 events, found 37"):
            validate_published_squad_contract(payload)

    def test_a_missing_deadline_is_refused(self) -> None:
        # Published as the string "None" by `publish_season_inputs` otherwise.
        payload = _bootstrap()
        del payload["events"][10]["deadline_time"]
        with pytest.raises(RulesContractError, match=r"events\[10\].deadline_time"):
            validate_published_squad_contract(payload)

    def test_a_null_deadline_is_refused(self) -> None:
        payload = _bootstrap()
        payload["events"][10]["deadline_time"] = None
        with pytest.raises(RulesContractError, match="must be a non-empty string"):
            validate_published_squad_contract(payload)

    def test_gameweeks_out_of_chronological_order_are_refused(self) -> None:
        payload = _bootstrap()
        payload["events"][10]["deadline_time"] = "2025-08-01T11:00:00Z"
        with pytest.raises(RulesContractError, match="does not deadline after event"):
            validate_published_squad_contract(payload)

    def test_two_gameweeks_sharing_a_deadline_are_refused(self) -> None:
        payload = _bootstrap()
        payload["events"][10]["deadline_time"] = payload["events"][9]["deadline_time"]
        with pytest.raises(RulesContractError, match="does not deadline after event"):
            validate_published_squad_contract(payload)


class TestTheRulesContractStaysSeparate:
    def test_a_rules_only_document_is_not_asked_for_a_squad(self) -> None:
        # An archived rules snapshot legitimately carries no roster. Coupling the
        # two would make `RulesSnapshot.from_bootstrap` unusable against it.
        from fpl_andres.rules import validate_published_squad_contract as squad

        payload = _bootstrap()
        del payload["teams"]
        with pytest.raises(RulesContractError, match="missing required rule: teams"):
            squad(payload)
