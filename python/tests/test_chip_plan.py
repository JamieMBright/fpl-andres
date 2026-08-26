"""Chip timing across a season that hands out every chip twice.

FPL resets the set at the halfway point: four chips are available in gameweeks
1 to 19 and a fresh four from 20 to 38, and whatever is unplayed when the half
ends is simply lost. Each rule is the chip's own definition turned into a
measurement, so each is checked against a case where the right answer is obvious
by construction.

`ceiling` is the best eleven the whole budget could buy that week ignoring
transfers. Both unlimited-transfer chips are priced off the gap between it and
what the plan actually fields -- Free Hit for one week, Wildcard for the run.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from fpl_andres.cli.publish_season_plan import (
    Candidate,
    _chip_plan,
    _ChipRun,
    _data_gaps,
    _lineup_points_with_captain,
    _place_wildcards,
    _validate_published_armbands,
    _wildcard_turnover,
)


def _candidate(code: int, name: str, club: str = "ARS", position: int = 3) -> Candidate:
    return Candidate(
        element_id=code,
        code=code,
        name=name,
        position=position,
        team_id=1,
        club=club,
        price_tenths=100,
        record=5.0,
        best_match=12.0,
        squad_number=None,
    )


def _week(
    event: int,
    *,
    expected: dict[str, float],
    bench: list[int],
    projected: float = 50.0,
    captain: int | None = None,
) -> dict[str, Any]:
    starters = sorted(int(code) for code in expected if int(code) not in bench)
    published_captain = captain or max(starters, key=lambda code: expected[str(code)])
    return {
        "event": event,
        "expected": expected,
        "starters": starters,
        "captain": published_captain,
        "bench": bench,
        "squadElementIds": sorted(int(code) for code in expected),
        "benchElementIds": list(bench),
        "projectedPoints": projected,
    }


NAMED = {1: _candidate(1, "Salah"), 2: _candidate(2, "Haaland")}
CODES = {1: 1, 2: 2}


def _peak(weeks: list[dict[str, Any]], scale: float = 2.0) -> dict[tuple[int, int], float]:
    """A ceiling for every player in every week, at a fixed multiple of the mean."""
    return {
        (week["event"], int(code)): value * scale
        for week in weeks
        for code, value in week["expected"].items()
    }


def _plan(
    weeks: list[dict[str, Any]],
    ceiling: dict[int, float] | None = None,
) -> dict[str, dict[str, Any]]:
    """Chips keyed by name and half, since every chip now appears twice."""
    return {
        f"{chip['chip']}:{chip['half']}": chip
        for chip in _chip_plan(weeks, NAMED, ceiling, _peak(weeks), CODES)
    }


def test_triple_captain_lands_on_the_best_single_player_week() -> None:
    weeks = [
        _week(1, expected={"1": 4.0, "2": 3.0}, bench=[]),
        _week(2, expected={"1": 9.0, "2": 3.0}, bench=[]),
        _week(3, expected={"1": 5.0, "2": 5.0}, bench=[]),
    ]

    chips = _plan(weeks)

    assert chips["Triple Captain:first"]["event"] == 2
    assert "Salah" in str(chips["Triple Captain:first"]["note"])


def test_triple_captain_ignores_a_higher_scoring_goalkeeper() -> None:
    named = {
        1: _candidate(1, "Goalkeeper", position=1),
        2: _candidate(2, "Midfielder", position=3),
    }
    weeks = [_week(1, expected={"1": 20.0, "2": 8.0}, bench=[], captain=2)]
    chips = {chip["chip"]: chip for chip in _chip_plan(weeks, named, {}, _peak(weeks), CODES)}

    assert "Midfielder" in str(chips["Triple Captain"]["note"])


def test_triple_captain_ignores_a_higher_scoring_bench_midfielder() -> None:
    weeks = [_week(1, expected={"1": 20.0, "2": 8.0}, bench=[1])]
    chips = _plan(weeks)

    assert "Haaland" in str(chips["Triple Captain:first"]["note"])


def test_triple_captain_follows_the_published_captain() -> None:
    weeks = [_week(1, expected={"1": 6.0, "2": 9.0}, bench=[], captain=1)]
    chips = _plan(weeks)

    assert "Salah" in str(chips["Triple Captain:first"]["note"])


def test_publisher_refuses_an_ineligible_armband() -> None:
    named = {
        1: _candidate(1, "Goalkeeper", position=1),
        2: _candidate(2, "Midfielder", position=3),
        3: _candidate(3, "Forward", position=4),
    }

    with pytest.raises(ValueError, match="ineligible captain"):
        _validate_published_armbands([{"event": 2, "captain": 1, "viceCaptain": 2}], named)

    _validate_published_armbands([{"event": 2, "captain": 2, "viceCaptain": 3}], named)


def test_chip_ceiling_doubles_the_best_eligible_starter() -> None:
    named = {
        1: _candidate(1, "Goalkeeper", position=1),
        2: _candidate(2, "Midfielder", position=3),
        3: _candidate(3, "Forward", position=4),
    }

    assert _lineup_points_with_captain([1, 2, 3], {1: 20.0, 2: 8.0, 3: 7.0}, named) == 43.0


def test_the_triple_captain_is_judged_on_the_ceiling_not_the_average() -> None:
    """A chip is played for the afternoon he takes a goal, a clean sheet and a
    defensive contribution, not for his mean."""
    weeks = [_week(1, expected={"1": 6.0}, bench=[])]

    chip = _plan(weeks)["Triple Captain:first"]

    assert chip["gain"] == 6.0
    assert chip["ceiling"] == 12.0


def test_bench_boost_follows_the_bench_not_the_squad() -> None:
    # Gameweek 1 is the better squad; gameweek 3 is the better bench, which is
    # the only thing a bench boost scores.
    weeks = [
        _week(1, expected={"1": 20.0, "2": 1.0}, bench=[2]),
        _week(3, expected={"1": 5.0, "2": 8.0}, bench=[2]),
    ]

    assert _plan(weeks)["Bench Boost:first"]["event"] == 3


def test_free_hit_takes_the_largest_one_week_gain() -> None:
    weeks = [
        _week(1, expected={"1": 9.0, "2": 1.0}, bench=[2], projected=50.0),
        _week(2, expected={"1": 1.0, "2": 1.0}, bench=[2], projected=30.0),
        _week(3, expected={"1": 1.0, "2": 8.0}, bench=[2], projected=48.0),
    ]
    # Gameweek 2 is where the planned eleven falls furthest short of what the
    # budget could buy, which is exactly what one week of free transfers buys.
    ceiling = {1: 52.0, 2: 60.0, 3: 49.0}

    assert _plan(weeks, ceiling)["Free Hit:first"]["event"] == 2


def test_a_blank_needs_no_special_case_because_it_is_already_worth_zero() -> None:
    # Everyone blanks in gameweek 2, so the plan scores nothing and the ceiling
    # towers over it. The rule finds it without knowing what a blank is.
    weeks = [
        _week(1, expected={"1": 5.0, "2": 1.0}, bench=[2], projected=50.0),
        _week(2, expected={"1": 0.0, "2": 0.0}, bench=[2], projected=0.0),
        _week(3, expected={"1": 1.0, "2": 6.0}, bench=[2], projected=49.0),
    ]
    ceiling = {1: 51.0, 2: 40.0, 3: 50.0}

    assert _plan(weeks, ceiling)["Free Hit:first"]["event"] == 2


def test_a_chip_is_still_played_when_it_gains_nothing() -> None:
    """It expires at the half. A chip worth little beats a chip worth nothing,
    and the note says which of the two this is."""
    weeks = [_week(index, expected={"1": 4.0}, bench=[], projected=50.0) for index in range(1, 14)]
    ceiling = {index: 50.0 for index in range(1, 14)}

    chip = _plan(weeks, ceiling)["Free Hit:first"]

    assert chip["event"] is not None
    assert "worth almost nothing here" in str(chip["note"])


def test_only_one_chip_lands_in_any_gameweek() -> None:
    # Four chips and three weeks, so one of them has nowhere left to go.
    weeks = [_week(index, expected={"1": 4.0}, bench=[], projected=50.0) for index in range(1, 4)]

    assert len(_chip_plan(weeks, NAMED, {}, _peak(weeks), CODES)) == 3


def test_wildcard_takes_the_run_where_the_squad_is_furthest_behind() -> None:
    """A wildcard keeps its squad, so a long shortfall beats a single deep one.
    It lands on the first week of the run rather than the week before it: the
    credit tapers as one free transfer a week catches up, so a leading week of
    nothing is dead weight at full weight."""
    weeks = [_week(index, expected={"1": 1.0}, bench=[], projected=40.0) for index in range(1, 13)]
    ceiling = {index: 40.0 for index in range(1, 13)}
    for index in range(6, 13):
        ceiling[index] = 45.0

    assert _plan(weeks, ceiling)["Wildcard:first"]["event"] == 6


@pytest.mark.parametrize(
    ("ordered_events", "by_event", "expected_replacing"),
    [
        (
            [5, 6],
            {
                5: {"event": 5, "squadElementIds": [1, 2, 3], "netExpectedPoints": 10.0},
                6: {"event": 6, "squadElementIds": [4, 5, 6], "netExpectedPoints": 10.0},
            },
            {1, 2, 3},
        ),
        (
            [6],
            {6: {"event": 6, "squadElementIds": [4, 5, 6], "netExpectedPoints": 10.0}},
            {1, 2, 3},
        ),
    ],
)
def test_wildcard_publishes_the_exact_segment_squad(
    monkeypatch: pytest.MonkeyPatch,
    ordered_events: list[int],
    by_event: dict[int, dict[str, Any]],
    expected_replacing: set[int],
) -> None:
    solved_week = {
        "event": 6,
        "starters": [101, 102],
        "bench": [103],
        "squadElementIds": [11, 12, 13],
        "netExpectedPoints": 11.0,
    }
    run = cast(
        _ChipRun,
        SimpleNamespace(
            ordered_events=ordered_events,
            by_event=by_event,
            opening_squad=[1, 2, 3],
            detail={
                11: _candidate(101, "Solved one"),
                12: _candidate(102, "Solved two"),
                13: _candidate(103, "Solved three"),
            },
        ),
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._wildcard_turnover",
        lambda _event, _run: 5,
    )
    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._season_with_wildcards",
        lambda _events, _run: (
            {
                event: solved_week if event == 6 else run.by_event[event]
                for event in run.ordered_events
            },
            21.0,
        ),
    )
    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._wildcard_squad",
        lambda _event, _run: ([21, 22], [23]),
    )

    def capture_turnover(
        _week: dict[str, Any],
        starters: list[int],
        bench: list[int],
        _run: _ChipRun,
        replacing: set[int] | None = None,
    ) -> None:
        captured.update(starters=starters, bench=bench, replacing=replacing)

    monkeypatch.setattr("fpl_andres.cli.publish_season_plan._turnover", capture_turnover)

    _place_wildcards(
        [{"chip": "Wildcard", "event": 6, "_alternatives": []}],
        run,
    )

    assert captured == {
        "starters": [11, 12],
        "bench": [13],
        "replacing": expected_replacing,
    }


def test_first_remaining_wildcard_screen_compares_with_the_held_squad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = cast(
        _ChipRun,
        SimpleNamespace(
            ordered_events=[6],
            by_event={6: {"squadElementIds": [1, 2, 4]}},
            opening_squad=[1, 2, 3],
        ),
    )
    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._wildcard_squad",
        lambda _event, _run: ([1, 2], [4]),
    )

    assert _wildcard_turnover(6, run) == 1


def test_a_wildcard_is_never_played_before_the_squad_can_have_drifted() -> None:
    """Gameweeks one to three rebuild a squad that was chosen freely days ago."""
    weeks = [_week(index, expected={"1": 1.0}, bench=[], projected=10.0) for index in range(1, 13)]
    ceiling = {index: 90.0 for index in range(1, 13)}

    event = _plan(weeks, ceiling)["Wildcard:first"]["event"]

    assert isinstance(event, int)
    assert event >= 4


def test_a_free_hit_is_never_played_in_the_opening_week() -> None:
    """There is no squad to escape: the eleven on the pitch was picked for it."""
    weeks = [_week(index, expected={"1": 1.0}, bench=[], projected=10.0) for index in range(1, 13)]
    ceiling = {index: 90.0 for index in range(1, 13)}

    assert _plan(weeks, ceiling)["Free Hit:first"]["event"] != 1


def test_the_two_unlimited_transfer_chips_are_kept_apart() -> None:
    """A free hit next door to a wildcard hands back the squad the wildcard just
    built, which spends two chips to do the work of one."""
    weeks = [_week(index, expected={"1": 1.0}, bench=[], projected=10.0) for index in range(1, 20)]
    ceiling = {index: 90.0 for index in range(1, 20)}

    chips = _plan(weeks, ceiling)
    wildcard = chips["Wildcard:first"]["event"]
    free_hit = chips["Free Hit:first"]["event"]

    assert isinstance(wildcard, int)
    assert isinstance(free_hit, int)
    assert abs(wildcard - free_hit) >= 3


def test_a_flat_shortfall_is_not_a_free_hit_problem() -> None:
    """A squad behind every week wants rebuilding, not one borrowed afternoon,
    so the free hit scores it at nothing."""
    weeks = [_week(index, expected={"1": 1.0}, bench=[], projected=40.0) for index in range(1, 20)]
    ceiling = {index: 50.0 for index in range(1, 20)}

    assert _plan(weeks, ceiling)["Free Hit:first"]["gain"] == 0.0


def test_a_single_collapsed_week_is_exactly_a_free_hit_problem() -> None:
    weeks = [_week(index, expected={"1": 1.0}, bench=[], projected=50.0) for index in range(1, 20)]
    ceiling = {index: 50.0 for index in range(1, 20)}
    ceiling[11] = 90.0

    assert _plan(weeks, ceiling)["Free Hit:first"]["event"] == 11


def test_every_chip_is_offered_once_in_each_half() -> None:
    weeks = [
        _week(index, expected={"1": 9.0, "2": 9.0}, bench=[2], projected=10.0)
        for index in range(1, 39)
    ]
    ceiling = {index: 90.0 for index in range(1, 39)}

    chips = _chip_plan(weeks, NAMED, ceiling, _peak(weeks), CODES)
    pairs = sorted((str(chip["chip"]), str(chip["half"])) for chip in chips)

    assert len(chips) == 8
    assert pairs == sorted(
        (chip, half)
        for chip in ("Bench Boost", "Free Hit", "Triple Captain", "Wildcard")
        for half in ("first", "second")
    )


def test_a_first_half_chip_never_lands_in_the_second() -> None:
    weeks = [
        _week(index, expected={"1": 9.0, "2": 9.0}, bench=[2], projected=10.0)
        for index in range(1, 39)
    ]
    ceiling = {index: 90.0 for index in range(1, 39)}

    for chip in _chip_plan(weeks, NAMED, ceiling, _peak(weeks), CODES):
        event = int(str(chip["event"]))
        if chip["half"] == "first":
            assert event <= 19
        else:
            assert event > 19


def test_two_chips_never_land_on_the_same_gameweek() -> None:
    weeks = [
        _week(index, expected={"1": 9.0, "2": 9.0}, bench=[2], projected=10.0)
        for index in range(1, 39)
    ]
    ceiling = {index: 90.0 for index in range(1, 39)}

    events = [chip["event"] for chip in _chip_plan(weeks, NAMED, ceiling, _peak(weeks), CODES)]

    assert len(events) == len(set(events))


def test_a_season_with_only_a_first_half_plans_only_four() -> None:
    weeks = [_week(index, expected={"1": 5.0}, bench=[], projected=40.0) for index in range(1, 10)]

    assert len(_chip_plan(weeks, NAMED, {}, _peak(weeks), CODES)) == 4


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

    assert gaps["clubsWithoutRecord"] == ["COV", "HUL"]
    assert gaps["clubsInPool"] == 2
    assert gaps["clubsInLeague"] == 4
