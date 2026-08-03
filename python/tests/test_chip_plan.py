"""Chip timing, and the hole the promoted clubs leave.

Each chip rule is its own definition turned into a measurement, so each one is
checked against a case where the right answer is obvious by construction.
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
    transfers_in: int = 0,
) -> dict[str, Any]:
    return {
        "event": event,
        "expected": expected,
        "bench": bench,
        "transfersIn": list(range(transfers_in)),
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
    # Gameweek 1 is the better squad; gameweek 2 is the better bench, which is
    # the only thing a bench boost scores.
    weeks = [
        _week(1, expected={"1": 20.0, "2": 1.0}, bench=[2]),
        _week(3, expected={"1": 5.0, "2": 8.0}, bench=[2]),
    ]

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED)}

    assert chips["Bench Boost"]["event"] == 3


def test_free_hit_goes_to_the_week_with_most_blanks() -> None:
    weeks = [
        # Best single player, so the triple captain takes this one.
        _week(1, expected={"1": 9.0, "2": 5.0}, bench=[2]),
        # Nobody plays.
        _week(2, expected={"1": 0.0, "2": 0.0}, bench=[2]),
        # Best bench, so the bench boost takes this one.
        _week(3, expected={"1": 4.0, "2": 7.0}, bench=[2]),
    ]

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED)}

    assert chips["Free Hit"]["event"] == 2


def test_free_hit_is_refused_when_no_gameweek_blanks() -> None:
    weeks = [
        _week(1, expected={"1": 4.0}, bench=[]),
        _week(2, expected={"1": 5.0}, bench=[]),
    ]

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED)}

    # No blank is scheduled until the cups postpone fixtures, so a free hit has
    # nothing to buy. Saying so beats naming a week at random.
    assert chips["Free Hit"]["event"] is None
    assert "no blank gameweek" in str(chips["Free Hit"]["note"])


def test_wildcard_fires_where_five_transfers_are_wanted_in_five_weeks() -> None:
    # The last two weeks carry the best player and the best bench, so the other
    # chips take those and leave the early run to the wildcard.
    weeks = [
        _week(index, expected={"1": 4.0, "2": 1.0}, bench=[2], transfers_in=1)
        for index in range(1, 9)
    ]
    weeks.append(_week(9, expected={"1": 4.0, "2": 9.0}, bench=[2]))
    weeks.append(_week(10, expected={"1": 20.0, "2": 1.0}, bench=[2]))

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED)}

    assert chips["Triple Captain"]["event"] == 10
    assert chips["Bench Boost"]["event"] == 9
    assert chips["Wildcard"]["event"] == 1


def test_wildcard_is_refused_when_the_plan_never_wants_that_many() -> None:
    weeks = [_week(index, expected={"1": 4.0}, bench=[], transfers_in=0) for index in range(1, 7)]

    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, NAMED)}

    assert chips["Wildcard"]["event"] is None


def test_two_chips_never_land_on_the_same_gameweek() -> None:
    weeks = [
        _week(1, expected={"1": 9.0, "2": 9.0}, bench=[2], transfers_in=2),
        _week(2, expected={"1": 1.0, "2": 1.0}, bench=[2], transfers_in=2),
        _week(3, expected={"1": 1.0, "2": 1.0}, bench=[2], transfers_in=2),
    ]

    events = [chip["event"] for chip in _chip_plan(weeks, NAMED) if chip["event"]]

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
