"""Playing a chip, which the optimizer does not model and the publisher does.

`chip_scenario` on the optimizer request is `Literal["none"]`: the solver has no
idea a chip exists, so the week a chip was chosen for still holds the squad the
plan was carrying. Every one of these covers the publisher putting that right,
and refusing to when the chip does not actually earn its place.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from fpl_andres.cli.publish_season_plan import (
    MINIMUM_FREE_HIT_CHANGES,
    MINIMUM_WILDCARD_CHANGES,
    Candidate,
    _ChipRun,
    _free_hit_squad,
    _place_wildcards,
    _play_chips,
    _play_free_hit,
    _solved_wildcard_turnover,
    _turnover,
    _wildcard_turnover,
)
from fpl_andres.simulation.squad import Candidate as SquadCandidate


def test_final_wildcard_turnover_reads_the_replanned_predecessor() -> None:
    weeks = {
        4: {"squadElementIds": list(range(1, 16))},
        5: {"squadElementIds": [*range(1, 12), 20, 21, 22, 23]},
    }

    assert _solved_wildcard_turnover(5, weeks, [4, 5], list(range(1, 16))) == 4


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
        rules=SimpleNamespace(transfer_rules=SimpleNamespace(weekly_free_transfers=1)),  # type: ignore[arg-type]
        now=datetime(2026, 8, 1, tzinfo=UTC),
        time_limit=1.0,
        schedule={},
        clubs=CLUBS,
        strength={},
        budget_tenths=1000,
        opening_squad=HELD,
        opening_bank_tenths=0,
        opening_free_transfers=1,
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


def test_a_free_hit_preserves_the_best_xi_and_cheapens_the_bench(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    positions = [1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 1, 2, 3, 2]
    expensive = [
        SquadCandidate(
            element_id=index,
            element_code=index,
            position=position,
            team_id=index,
            price_tenths=50,
        )
        for index, position in enumerate(positions, start=1)
    ]
    cheap = [
        SquadCandidate(
            element_id=16 + index,
            element_code=16 + index,
            position=position,
            team_id=16 + index,
            price_tenths=40 if position != 3 else 45,
        )
        for index, position in enumerate((1, 2, 3, 2))
    ]
    starters = tuple(expensive[:11])
    bench = tuple(expensive[11:])
    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan.choose_opening_squad",
        lambda *_args, **_kwargs: SimpleNamespace(
            squad=tuple(expensive),
            starters=starters,
            bench=bench,
        ),
    )
    points = {candidate.element_id: 10.0 for candidate in starters}
    points.update({candidate.element_id: 0.0 for candidate in [*bench, *cheap]})

    selected_starters, selected_bench = _free_hit_squad([*expensive, *cheap], points)

    assert set(selected_starters) == {candidate.element_id for candidate in starters}
    assert set(selected_bench) == {candidate.element_id for candidate in cheap}


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


def test_a_free_hit_restores_the_previous_squad_and_resets_to_one_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ordinary_transfer = [*HELD[:-1], 16]
    weeks = {1: _week(1, HELD), 2: _week(2, ordinary_transfer), 3: _week(3, ordinary_transfer)}
    run = _run(weeks, _points(better=True))
    resumed = _week(3, HELD)
    captured: dict[str, object] = {}

    def solve_after(
        events: list[int],
        squad: list[int],
        bank_tenths: int,
        free_transfers: int,
        _run: _ChipRun,
    ) -> dict[int, dict[str, Any]]:
        captured.update(
            events=events,
            squad=squad,
            bank_tenths=bank_tenths,
            free_transfers=free_transfers,
        )
        return {3: resumed}

    monkeypatch.setattr("fpl_andres.cli.publish_season_plan._solve_segment", solve_after)

    _play_chips([_free_hit()], run)

    assert len(weeks[2]["transfersIn"]) >= MINIMUM_FREE_HIT_CHANGES
    assert weeks[2]["revertsTo"] == HELD
    assert captured == {
        "events": [3],
        "squad": HELD,
        "bank_tenths": 0,
        "free_transfers": 1,
    }
    assert weeks[3]["squadElementIds"] == HELD
    assert 16 not in weeks[3]["squadElementIds"]


def test_a_wildcard_after_a_free_hit_rebuilds_from_the_restored_squad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ordinary_transfer = [*HELD[:-1], 16]
    rebuilt = [*HELD[:10], *FRESH[:5]]
    weeks = {
        1: _week(1, HELD),
        2: _week(2, ordinary_transfer),
        3: {**_week(3, rebuilt), "chip": "Wildcard"},
    }
    run = _run(weeks, _points(better=True))
    captured: list[set[int] | None] = []

    def capture_turnover(
        week: dict[str, Any],
        starters: list[int],
        bench: list[int],
        _run: _ChipRun,
        replacing: set[int] | None = None,
    ) -> None:
        captured.append(replacing)
        week["squadElementIds"] = sorted(set(starters) | set(bench))
        week["netExpectedPoints"] = 72.0

    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._turnover",
        capture_turnover,
    )

    _play_free_hit(_free_hit(), run)

    assert captured == [set(HELD), set(HELD)]


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


def test_a_free_hit_is_refused_when_the_transfer_reset_loses_more_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weeks = {2: _week(2, HELD), 3: _week(3, HELD)}
    weeks[3]["netExpectedPoints"] = 100.0
    resumed = _week(3, HELD)
    resumed["netExpectedPoints"] = 20.0
    run = _run(weeks, _points(better=True))
    chip = _free_hit()
    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._solve_segment",
        lambda *_args, **_kwargs: {3: resumed},
    )

    _play_chips([chip], run)

    assert chip["event"] is None
    assert chip["gain"] == 0.0
    assert "resetting to one free transfer" in chip["note"]
    assert weeks[3]["netExpectedPoints"] == 100.0


def test_the_turnover_captains_the_best_of_the_new_eleven() -> None:
    week = _week(2, HELD)
    points = {element_id: float(element_id) for element_id in DETAIL}
    starters, bench = FRESH[:11], FRESH[11:]

    _turnover(week, starters, bench, _run({2: week}, points))

    assert week["captain"] == max(starters)
    assert week["viceCaptain"] == sorted(starters)[-2]


def _wildcard(event: int | None = 3) -> dict[str, Any]:
    return {"chip": "Wildcard", "half": "first", "event": event, "gain": 0.0, "note": ""}


def test_a_rebuild_that_moves_almost_nobody_is_not_a_wildcard() -> None:
    """The report that motivated it: a Wildcard offered against one transfer.

    The pool here is the squad the plan already holds, so the best fifteen it
    can shop for is the fifteen it has. A chip that buys nothing the free
    transfer could not is a chip thrown away.
    """
    weeks = {2: _week(2, HELD), 3: _week(3, HELD)}
    run = _run(weeks, _points(better=False))
    chips = [_wildcard(3)]

    assert _wildcard_turnover(3, run) < MINIMUM_WILDCARD_CHANGES

    _place_wildcards(chips, run)

    assert chips[0]["event"] is None
    assert chips[0]["gain"] == 0.0
    assert str(MINIMUM_WILDCARD_CHANGES) in chips[0]["note"]
    assert "chip" not in weeks[3]


def test_a_played_wildcard_is_a_permanent_meaningful_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebuilt = [*HELD[:10], *FRESH[:5]]
    weeks = {2: _week(2, HELD), 3: _week(3, HELD), 4: _week(4, rebuilt)}
    run = _run(weeks, _points(better=True))
    solved = {2: weeks[2], 3: _week(3, rebuilt), 4: _week(4, rebuilt)}

    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._wildcard_turnover",
        lambda _event, _run: MINIMUM_WILDCARD_CHANGES,
    )
    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._solved_wildcard_turnover",
        lambda _event, _weeks, _ordered, _opening: MINIMUM_WILDCARD_CHANGES,
    )
    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._season_with_wildcards",
        lambda _events, _run: (solved, 120.0),
    )
    monkeypatch.setattr(
        "fpl_andres.cli.publish_season_plan._wildcard_horizon_cliff",
        lambda _event, _run: (5, (5, 7)),
    )

    _place_wildcards([_wildcard(3)], run)

    assert weeks[3]["chip"] == "Wildcard"
    assert len(weeks[3]["transfersIn"]) >= MINIMUM_WILDCARD_CHANGES
    assert weeks[4]["squadElementIds"] == rebuilt


def test_the_turnover_is_measured_against_the_week_before_the_rebuild() -> None:
    """Not against the rebuild itself, which would always report zero moves."""
    weeks = {2: _week(2, HELD), 3: _week(3, HELD)}
    run = _run(weeks, _points(better=True))

    # The pool is the held fifteen, so a rebuild in gameweek 3 can only reshuffle
    # what is already there and the turnover against gameweek 2 is nil.
    assert _wildcard_turnover(3, run) == 0


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
