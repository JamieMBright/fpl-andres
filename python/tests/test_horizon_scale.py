"""The horizon MILP was left unwired for being intractable. At live scale it is not.

The roadmap's reason was that it cannot go in the backtest: eleven thousand
binaries times twenty managers times three seeds times four seasons times
thirty-two gameweeks. That is true and stays true. It says nothing about the
live path, which solves one squad once a week.

Measured on this machine: 100 players over 3 events in 0.23s, 200 over 3 in
0.52s, 200 over 5 in 6.30s, 400 over 5 in 10.46s. The blocker for a live
transfer plan is the season, not the solver.
"""

from __future__ import annotations

import random
import time
from datetime import timedelta

from test_highs_optimizer import CUTOFF, rules, state_evidence

from fpl_andres.optimization.contracts import (
    CurrentSquadPlayer,
    HorizonEvent,
    HorizonOptimizationRequest,
    HorizonPlayerForecast,
    PositionConstraint,
)
from fpl_andres.optimization.horizon import HighsHorizonOptimizer

SQUAD_SHAPE = ((1, 2), (2, 5), (3, 5), (4, 3))
LINEUP_RANGE = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}
# Generous against the measured 0.23s so a slower CI box cannot flake it, while
# still failing loudly if the problem stops being tractable at all.
SOLVE_BUDGET_SECONDS = 20.0


def _request(*, per_position: int, event_count: int) -> HorizonOptimizationRequest:
    rng = random.Random(7)
    players: list[tuple[int, int, int, int]] = []
    element_id = 1
    for position_id, _ in SQUAD_SHAPE:
        for _ in range(per_position):
            players.append((element_id, position_id, element_id % 20 + 1, rng.randint(40, 145)))
            element_id += 1

    events = tuple(
        HorizonEvent(
            event=1 + index,
            prediction_cutoff=CUTOFF + timedelta(days=7 * index),
            objective_weight=1.0,
        )
        for index in range(event_count)
    )

    forecasts = tuple(
        HorizonPlayerForecast(
            season="2026-27",
            event=event.event,
            element_id=pid,
            team_id=team_id,
            position_id=position_id,
            buy_price_tenths=price,
            sell_price_tenths=price,
            expected_points=round(rng.uniform(0.0, 9.0), 2),
            evidence_level="experimental",
            model_name="scale-guard",
            model_version="1",
            data_available_at=event.prediction_cutoff,
            source_hashes=(f"sha256:{pid:064x}",),
        )
        for event in events
        for pid, position_id, team_id, price in players
    )

    squad: list[CurrentSquadPlayer] = []
    for position_id, count in SQUAD_SHAPE:
        for player in [p for p in players if p[1] == position_id][:count]:
            squad.append(CurrentSquadPlayer(element_id=player[0], selling_price_tenths=player[3]))

    return HorizonOptimizationRequest(
        events=events,
        forecasts=forecasts,
        current_squad=tuple(squad),
        bank_tenths=10,
        available_free_transfers=1,
        state_evidence=state_evidence(),
        price_scenario="provided_event_prices",
        objective="expected_value",
        chip_scenario="none",
        rules=rules(
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
        ),
    )


def test_a_full_squad_over_a_three_week_horizon_solves_inside_the_budget() -> None:
    request = _request(per_position=25, event_count=3)

    started = time.perf_counter()
    result = HighsHorizonOptimizer(time_limit_seconds=60.0).solve(request)
    elapsed = time.perf_counter() - started

    assert elapsed < SOLVE_BUDGET_SECONDS, f"took {elapsed:.2f}s"
    assert len(result.events) == 3


def test_the_plan_obeys_squad_shape_in_every_event() -> None:
    result = HighsHorizonOptimizer(time_limit_seconds=60.0).solve(
        _request(per_position=25, event_count=3)
    )

    for event in result.events:
        assert len(event.squad_element_ids) == 15
        assert len(set(event.squad_element_ids)) == 15


def test_free_transfers_never_exceed_the_sourced_cap_at_scale() -> None:
    result = HighsHorizonOptimizer(time_limit_seconds=60.0).solve(
        _request(per_position=25, event_count=3)
    )

    for event in result.events:
        assert event.free_transfers_before <= 5
        assert event.free_transfers_next_event <= 5
