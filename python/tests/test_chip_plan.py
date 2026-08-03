"""Chip timing, and the hole the promoted clubs leave.

Each chip rule is its own definition turned into a measurement, so each is
checked against a case where the right answer is obvious by construction.

`ceiling` is the best eleven the whole budget could buy that week ignoring
transfers. Both unlimited-transfer chips are priced off the gap between it and
what the plan actually fields — Free Hit for one week, Wildcard for the run.
"""

from __future__ import annotations

from typing import Any

from fpl_andres.cli.publish_season_plan import Candidate, _chip_plan, _data_gaps


def _candidate(code: int, name: str, club: str = "ARS") -> Candidate:
    return Candidate(
        element_id=code,
        code=code,
        name=name,
        position=3,
        team_id=1,
        club=club,
        price_tenths=100,
        record=5.0,
        squad_number=None,
    )


def _week(
    event: int,
    *,
    expected: dict[str, float],
    bench: list[int],
    projected: float = 50.0,
) -> dict[str, Any]:
    return {
        "event": event,
        "expected": expected,
        "bench": bench,
        "projectedPoints": projected,
    }


NAMED = {1: _candidate(1, "Salah"), 2: _candidate(2, "Haaland")}


def test_triple_captain_lands_on_the_best_single_player_week() -> None:
    weeks = [
        _week(1, expected={"1": 4.0, "2": 3.0}, bench=[]),
        _week(2, expected={"1": 9.0, "2": 3.0}, bench=[]),
        _week(3, expected={"1": 5.0, "2": 5.0}, bench=[]),
    ]

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED)}

    assert chips["Triple Captain"]["event"] == 2
    assert "Salah" in str(chips["Triple Captain"]["note"])


def test_bench_boost_follows_the_bench_not_the_squad() -> None:
    # Gameweek 1 is the better squad; gameweek 3 is the better bench, which is
    # the only thing a bench boost scores.
    weeks = [
        _week(1, expected={"1": 20.0, "2": 1.0}, bench=[2]),
        _week(3, expected={"1": 5.0, "2": 8.0}, bench=[2]),
    ]

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED)}

    assert chips["Bench Boost"]["event"] == 3


def test_free_hit_takes_the_largest_one_week_gain() -> None:
    weeks = [
        # Best single player, so the triple captain takes this one.
        _week(1, expected={"1": 9.0, "2": 1.0}, bench=[2], projected=50.0),
        _week(2, expected={"1": 1.0, "2": 1.0}, bench=[2], projected=30.0),
        # Best bench, so the bench boost takes this one.
        _week(3, expected={"1": 1.0, "2": 8.0}, bench=[2], projected=48.0),
    ]
    # Gameweek 2 is where the planned eleven falls furthest short of what the
    # budget could buy, which is exactly what one week of free transfers buys.
    ceiling = {1: 52.0, 2: 60.0, 3: 49.0}

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED, ceiling)}

    assert chips["Free Hit"]["event"] == 2


def test_a_blank_needs_no_special_case_because_it_is_already_worth_zero() -> None:
    # Everyone blanks in gameweek 2, so the plan scores nothing and the ceiling
    # towers over it. The rule finds it without knowing what a blank is.
    weeks = [
        _week(1, expected={"1": 5.0, "2": 1.0}, bench=[2], projected=50.0),
        _week(2, expected={"1": 0.0, "2": 0.0}, bench=[2], projected=0.0),
        _week(3, expected={"1": 1.0, "2": 6.0}, bench=[2], projected=49.0),
    ]
    ceiling = {1: 51.0, 2: 40.0, 3: 50.0}

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED, ceiling)}

    assert chips["Free Hit"]["event"] == 2


def test_free_hit_is_refused_when_the_plan_already_fields_the_best_eleven() -> None:
    weeks = [
        _week(1, expected={"1": 4.0}, bench=[], projected=50.0),
        _week(2, expected={"1": 5.0}, bench=[], projected=50.0),
    ]
    ceiling = {1: 50.0, 2: 50.0}

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED, ceiling)}

    assert chips["Free Hit"]["event"] is None


def test_wildcard_takes_the_run_where_the_squad_is_furthest_behind() -> None:
    # A wildcard keeps its squad, so a long shortfall beats a single deep one.
    weeks = [_week(index, expected={"1": 1.0}, bench=[], projected=40.0) for index in range(1, 13)]
    ceiling = {index: 40.0 for index in range(1, 13)}
    for index in range(6, 13):
        ceiling[index] = 45.0

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED, ceiling)}

    assert chips["Wildcard"]["event"] == 5


def test_wildcard_is_refused_when_the_plan_never_falls_behind() -> None:
    weeks = [_week(index, expected={"1": 1.0}, bench=[], projected=40.0) for index in range(1, 6)]
    ceiling = {index: 40.0 for index in range(1, 6)}

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED, ceiling)}

    assert chips["Wildcard"]["event"] is None


def test_two_chips_never_land_on_the_same_gameweek() -> None:
    weeks = [
        _week(index, expected={"1": 9.0, "2": 9.0}, bench=[2], projected=10.0)
        for index in range(1, 6)
    ]
    ceiling = {index: 90.0 for index in range(1, 6)}

    events = [chip["event"] for chip in _chip_plan(weeks, NAMED, ceiling) if chip["event"]]

    assert len(events) == len(set(events))


def test_an_empty_season_plans_no_chips() -> None:
    assert _chip_plan([], NAMED) == []


def test_the_clubs_with_no_record_are_named() -> None:
    pool = [_candidate(1, "Saka", club="ARS"), _candidate(2, "Salah", club="LIV")]
    clubs = {
        1: {"short_name": "ARS"},
        2: {"short_name": "LIV"},
        3: {"short_name": "HUL"},
        4: {"short_name": "COV"},
    }

    gaps = _data_gaps(pool, clubs)

    # A promoted club has no players in last season's record, so it is missing
    # from the pool entirely and its fixtures are rated as merely average.
    assert gaps["clubsWithoutRecord"] == ["COV", "HUL"]
    assert gaps["clubsInPool"] == 2
    assert gaps["clubsInLeague"] == 4
