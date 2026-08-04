"""Playing a chip, which the optimizer does not model and the publisher does.

`chip_scenario` on the optimizer request is `Literal["none"]`: the solver has no
idea a chip exists, so the week a chip was chosen for still holds the squad the
plan was carrying. Every one of these covers the publisher putting that right,
and refusing to when the chip does not actually earn its place.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from fpl_andres.cli.publish_season_plan import (
    Candidate,
    _ChipRun,
    _play_chips,
    _turnover,
)


def _candidate(element_id: int, club: str, price: int = 50) -> Candidate:
    return Candidate(
        element_id=element_id,
        code=element_id,
        name=f"Player {element_id}",
        position=3,
        team_id=element_id,
        club=club,
        price_tenths=price,
        record=4.0,
        best_match=9.0,
        squad_number=None,
    )


# Thirty players: 1-15 are the squad the plan carries, 16-30 are the rest of the
# game. The second fifteen score better, so a chip that shops widely finds them.
DETAIL = {element_id: _candidate(element_id, f"C{element_id:02d}") for element_id in range(1, 31)}
CLUBS = {element_id: {"short_name": f"C{element_id:02d}"} for element_id in range(1, 31)}
HELD = list(range(1, 16))
FRESH = list(range(16, 31))


def _points(better: bool) -> dict[int, float]:
    return {element_id: (6.0 if better and element_id > 15 else 3.0) for element_id in DETAIL}


def _week(event: int, squad: list[int]) -> dict[str, Any]:
    return {
        "event": event,
        "squadElementIds": sorted(squad),
        "benchElementIds": squad[11:],
        "starters": squad[:11],
        "bench": squad[11:],
        "netExpectedPoints": 36.0,
        "projectedPoints": 36.0,
        "bankAfterTenths": 0,
        "transfersIn": [],
        "transfersOut": [],
    }


def _run(weeks: dict[int, dict[str, Any]], points: dict[int, float]) -> _ChipRun:
    named: dict[int, Candidate] = {}

    def ref(element_id: int) -> int:
        named[DETAIL[element_id].code] = DETAIL[element_id]
        return DETAIL[element_id].code

    return _ChipRun(
        by_event=weeks,
        ordered_events=sorted(weeks),
        event_points={event: points for event in weeks},
        pool=[DETAIL[element_id] for element_id in HELD],
        candidate_for={},
        free_squads={event: (FRESH[:11], FRESH[11:]) for event in weeks},
        detail=DETAIL,
        cutoffs={event: datetime(2026, 8, 1, tzinfo=UTC) for event in weeks},
        forecasts=(),
        rules=None,  # type: ignore[arg-type]
        now=datetime(2026, 8, 1, tzinfo=UTC),
        time_limit=1.0,
        schedule={},
        clubs=CLUBS,
        strength={},
        budget_tenths=1000,
        week_dict=lambda planned: {},  # type: ignore[arg-type,misc]
        ref=ref,
    )


def _free_hit(event: int | None = 2) -> dict[str, Any]:
    return {"chip": "Free Hit", "half": "first", "event": event, "gain": 0.0, "note": ""}


def test_a_free_hit_fields_a_completely_different_fifteen() -> None:
    """The chip buys anyone in the game, so all fifteen may change."""
    weeks = {2: _week(2, HELD)}
    chips = [_free_hit()]

    _play_chips(chips, _run(weeks, _points(better=True)))

    week = weeks[2]
    assert week["chip"] == "Free Hit"
    assert sorted(week["squadElementIds"]) == FRESH
    assert len(week["transfersIn"]) == 15
    assert len(week["transfersOut"]) == 15


def test_a_free_hit_charges_nothing_and_spends_no_free_transfer() -> None:
    weeks = {2: _week(2, HELD)}

    _play_chips([_free_hit()], _run(weeks, _points(better=True)))

    assert weeks[2]["paidTransfers"] == 0
    assert weeks[2]["transferCostPoints"] == 0


def test_a_free_hit_publishes_the_fifteen_the_plan_resumes_from() -> None:
    """The squad is handed back, so the chain has to be checkable across it."""
    weeks = {2: _week(2, HELD)}

    _play_chips([_free_hit()], _run(weeks, _points(better=True)))

    assert weeks[2]["revertsAfter"] is True
    assert sorted(weeks[2]["revertsTo"]) == HELD


def test_a_free_hit_that_buys_nothing_better_is_not_played() -> None:
    """Every player worth the same means the best fifteen is the one held."""
    weeks = {2: _week(2, HELD)}
    chips = [_free_hit()]

    _play_chips(chips, _run(weeks, _points(better=False)))

    assert chips[0]["event"] is None
    assert chips[0]["gain"] == 0.0
    assert "nothing to buy" in chips[0]["note"]
    # And the week is left exactly as the plan had it.
    assert sorted(weeks[2]["squadElementIds"]) == HELD
    assert "chip" not in weeks[2]


def test_a_chip_reports_the_gain_it_actually_measured() -> None:
    weeks = {2: _week(2, HELD)}
    chips = [_free_hit()]

    _play_chips(chips, _run(weeks, _points(better=True)))

    # Eleven starters at six plus the captain again, against the 36 it replaced.
    assert weeks[2]["netExpectedPoints"] == pytest.approx(72.0)
    assert chips[0]["gain"] == pytest.approx(36.0)


def test_the_turnover_captains_the_best_of_the_new_eleven() -> None:
    week = _week(2, HELD)
    points = {element_id: float(element_id) for element_id in DETAIL}
    starters, bench = FRESH[:11], FRESH[11:]

    _turnover(week, starters, bench, _run({2: week}, points))

    assert week["captain"] == max(starters)
    assert week["viceCaptain"] == sorted(starters)[-2]


def test_the_turnover_names_the_opponent_and_grades_the_week() -> None:
    """A card names who they play; the shirt beside it already says the club."""
    week = _week(2, HELD)
    run = _run({2: week}, _points(better=True))
    schedule = {(2, element_id): ((1, True),) for element_id in FRESH}
    run = replace(run, schedule=schedule)

    _turnover(week, FRESH[:11], FRESH[11:], run)

    assert week["opponents"]["C16"] == ["C01 (H)"]
    assert set(week["difficulty"]) == {DETAIL[element_id].club for element_id in FRESH}


def test_a_free_hit_on_a_week_with_no_priced_fifteen_is_left_alone() -> None:
    """The ceiling solve can fail, and a chip is not played on a guess."""
    weeks = {2: _week(2, HELD)}
    run = replace(_run(weeks, _points(better=True)), free_squads={})
    chips = [_free_hit()]

    _play_chips(chips, run)

    assert "chip" not in weeks[2]
    assert chips[0]["event"] == 2


def test_a_wildcard_with_no_season_left_to_re_solve_is_not_played() -> None:
    """It keeps what it buys, so a chip with nothing after it buys nothing."""
    weeks = {38: _week(38, HELD)}
    chips = [{"chip": "Wildcard", "half": "second", "event": 38, "gain": 0.0, "note": ""}]

    _play_chips(chips, _run(weeks, _points(better=True)))

    assert "chip" not in weeks[38]


def test_a_chip_pointed_at_a_gameweek_outside_the_plan_is_ignored() -> None:
    weeks = {2: _week(2, HELD)}
    chips = [_free_hit(event=99), {"chip": "Wildcard", "half": "first", "event": 99, "gain": 0.0}]

    _play_chips(chips, _run(weeks, _points(better=True)))

    assert "chip" not in weeks[2]
