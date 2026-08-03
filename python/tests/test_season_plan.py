"""The season planner chains window solves without losing squad state.

The failure this guards against is a plan that looks complete and is not: a
gameweek missing from the middle, a squad that teleports between windows because
the carry-forward dropped, or a bank that resets to its opening value every time
a new window starts.
"""

from __future__ import annotations

import random
from datetime import timedelta

import pytest
from test_highs_optimizer import CUTOFF, rules, state_evidence

from fpl_andres.optimization.contracts import (
    CurrentSquadPlayer,
    HorizonPlayerForecast,
    PositionConstraint,
)
from fpl_andres.planning.season_plan import (
    COMMIT_EVENTS,
    confidence_for,
    plan_season,
)

SQUAD_SHAPE = ((1, 2), (2, 5), (3, 5), (4, 3))
LINEUP_RANGE = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}


def _rules() -> object:
    return rules(
        squad_size=15,
        lineup_size=11,
        positions=tuple(
            PositionConstraint(
                position_id=position_id,
                squad_count=count,
                lineup_minimum=LINEUP_RANGE[position_id][0],
                lineup_maximum=LINEUP_RANGE[position_id][1],
            )
            for position_id, count in SQUAD_SHAPE
        ),
    )


def _scenario(*, per_position: int, events: tuple[int, ...]):
    rng = random.Random(11)
    players: list[tuple[int, int, int, int]] = []
    element_id = 1
    for position_id, _ in SQUAD_SHAPE:
        for _ in range(per_position):
            players.append((element_id, position_id, element_id % 20 + 1, rng.randint(40, 120)))
            element_id += 1

    cutoffs = {event: CUTOFF + timedelta(days=7 * index) for index, event in enumerate(events)}
    forecasts = tuple(
        HorizonPlayerForecast(
            season="2026-27",
            event=event,
            element_id=pid,
            team_id=team_id,
            position_id=position_id,
            buy_price_tenths=price,
            sell_price_tenths=price,
            expected_points=round(rng.uniform(0.0, 8.0), 2),
            evidence_level="experimental",
            model_name="season-plan-test",
            model_version="1",
            data_available_at=cutoffs[event],
            source_hashes=(f"sha256:{pid:064x}",),
        )
        for event in events
        for pid, position_id, team_id, price in players
    )

    squad = []
    for position_id, count in SQUAD_SHAPE:
        for player in [p for p in players if p[1] == position_id][:count]:
            squad.append(CurrentSquadPlayer(element_id=player[0], selling_price_tenths=player[3]))

    return cutoffs, forecasts, tuple(squad)


@pytest.mark.slow
def test_every_requested_gameweek_appears_exactly_once() -> None:
    events = tuple(range(1, 13))
    cutoffs, forecasts, squad = _scenario(per_position=6, events=events)

    plan = plan_season(
        events=events,
        cutoffs=cutoffs,
        forecasts=forecasts,
        opening_squad=squad,
        bank_tenths=0,
        free_transfers=1,
        rules=_rules(),
        state_evidence=state_evidence(),
    )

    assert [planned.event for planned in plan.events] == list(events)
    assert plan.windows_solved > 1, "twelve gameweeks should take more than one window"


@pytest.mark.slow
def test_the_squad_carries_across_a_window_boundary() -> None:
    events = tuple(range(1, 10))
    cutoffs, forecasts, squad = _scenario(per_position=6, events=events)

    plan = plan_season(
        events=events,
        cutoffs=cutoffs,
        forecasts=forecasts,
        opening_squad=squad,
        bank_tenths=0,
        free_transfers=1,
        rules=_rules(),
        state_evidence=state_evidence(),
    )

    # The boundary is where a dropped carry-forward would show: the squad on the
    # first event of a new window must be the previous event's squad, changed
    # only by that event's own transfers.
    by_event = {planned.event: planned.plan for planned in plan.events}
    for event in events[1:]:
        previous = set(by_event[event - 1].squad_element_ids)
        current = by_event[event]
        expected = (previous - set(current.transfers_out)) | set(current.transfers_in)
        assert set(current.squad_element_ids) == expected, f"squad jumped at gameweek {event}"


@pytest.mark.slow
def test_a_plan_is_a_legal_squad_in_every_gameweek() -> None:
    events = tuple(range(1, 10))
    cutoffs, forecasts, squad = _scenario(per_position=6, events=events)

    plan = plan_season(
        events=events,
        cutoffs=cutoffs,
        forecasts=forecasts,
        opening_squad=squad,
        bank_tenths=0,
        free_transfers=1,
        rules=_rules(),
        state_evidence=state_evidence(),
    )

    for planned in plan.events:
        assert len(planned.plan.squad_element_ids) == 15
        assert len(planned.plan.starter_element_ids) == 11
        assert len(planned.plan.bench_element_ids) == 4
        assert planned.plan.captain_element_id in set(planned.plan.starter_element_ids)
        assert planned.plan.vice_captain_element_id != planned.plan.captain_element_id


def test_confidence_falls_away_from_the_next_deadline() -> None:
    assert confidence_for(1, 1) == "firm"
    assert confidence_for(2, 1) == "projected"
    assert confidence_for(8, 1) == "projected"
    assert confidence_for(9, 1) == "provisional"
    assert confidence_for(38, 1) == "provisional"
    # Mid-season: the bands travel with the next deadline, not with gameweek 1.
    assert confidence_for(20, 20) == "firm"
    assert confidence_for(30, 20) == "provisional"


def test_a_two_gameweek_season_still_plans() -> None:
    events = (37, 38)
    cutoffs, forecasts, squad = _scenario(per_position=6, events=events)

    plan = plan_season(
        events=events,
        cutoffs=cutoffs,
        forecasts=forecasts,
        opening_squad=squad,
        bank_tenths=0,
        free_transfers=1,
        rules=_rules(),
        state_evidence=state_evidence(),
    )

    assert [planned.event for planned in plan.events] == [37, 38]
    assert plan.windows_solved == 1


def test_a_single_gameweek_is_refused_rather_than_half_planned() -> None:
    cutoffs, forecasts, squad = _scenario(per_position=6, events=(38,))
    try:
        plan_season(
            events=(38,),
            cutoffs=cutoffs,
            forecasts=forecasts,
            opening_squad=squad,
            bank_tenths=0,
            free_transfers=1,
            rules=_rules(),
            state_evidence=state_evidence(),
        )
    except ValueError as error:
        assert "at least two gameweeks" in str(error)
    else:
        raise AssertionError("a one-gameweek season should not plan")


def test_a_missing_gameweek_forecast_is_named_rather_than_skipped() -> None:
    events = tuple(range(1, 6))
    cutoffs, forecasts, squad = _scenario(per_position=6, events=events)
    without_three = tuple(f for f in forecasts if f.event != 3)

    try:
        plan_season(
            events=events,
            cutoffs=cutoffs,
            forecasts=without_three,
            opening_squad=squad,
            bank_tenths=0,
            free_transfers=1,
            rules=_rules(),
            state_evidence=state_evidence(),
        )
    except ValueError as error:
        assert "3" in str(error)
    else:
        raise AssertionError("a gameweek with no forecasts should fail loudly")


def test_the_commit_stride_is_smaller_than_the_window() -> None:
    """Overlap is the whole reason this is not just twelve independent solves."""
    from fpl_andres.planning.season_plan import WINDOW_EVENTS

    assert COMMIT_EVENTS < WINDOW_EVENTS
