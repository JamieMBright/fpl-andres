from datetime import timedelta
from itertools import combinations
from math import inf

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from test_highs_optimizer import CUTOFF, rules, state_evidence

from fpl_andres.optimization import horizon as horizon_module
from fpl_andres.optimization.contracts import (
    CurrentSquadPlayer,
    HorizonEvent,
    HorizonOptimizationRequest,
    HorizonPlayerForecast,
    PositionConstraint,
)
from fpl_andres.optimization.highs import HighsOptimizer
from fpl_andres.optimization.horizon import HighsHorizonOptimizer
from fpl_andres.positions import is_captain_eligible


def forecast(
    element_id: int,
    event: int,
    points: float,
    *,
    position_id: int = 3,
) -> HorizonPlayerForecast:
    cutoff = CUTOFF + timedelta(days=7 * (event - 6))
    return HorizonPlayerForecast(
        season="2026-27",
        event=event,
        element_id=element_id,
        team_id=element_id,
        position_id=position_id,
        buy_price_tenths=50,
        sell_price_tenths=50,
        expected_points=points,
        evidence_level="experimental",
        model_name="two-week-fixture",
        model_version="1",
        data_available_at=cutoff,
        source_hashes=(f"sha256:{event * 100 + element_id:064x}",),
    )


def horizon_request() -> HorizonOptimizationRequest:
    event_points = {
        6: (5.0, 5.0, 6.0, 0.0, 0.0),
        7: (0.0, 0.0, 0.0, 10.0, 10.0),
    }
    return HorizonOptimizationRequest(
        events=(
            HorizonEvent(event=6, prediction_cutoff=CUTOFF, objective_weight=1.0),
            HorizonEvent(
                event=7,
                prediction_cutoff=CUTOFF + timedelta(days=7),
                objective_weight=1.0,
            ),
        ),
        forecasts=tuple(
            forecast(element_id, event, points[element_id - 1])
            for event, points in event_points.items()
            for element_id in range(1, 6)
        ),
        current_squad=(
            CurrentSquadPlayer(element_id=1, selling_price_tenths=50),
            CurrentSquadPlayer(element_id=2, selling_price_tenths=50),
        ),
        bank_tenths=0,
        available_free_transfers=1,
        state_evidence=state_evidence(),
        price_scenario="provided_event_prices",
        objective="expected_value",
        chip_scenario="none",
        rules=rules(
            squad_size=2,
            lineup_size=2,
            positions=(
                PositionConstraint(
                    position_id=3,
                    squad_count=2,
                    lineup_minimum=2,
                    lineup_maximum=2,
                ),
            ),
        ),
    )


def test_horizon_banks_transfer_when_it_beats_greedy_first_event() -> None:
    request = horizon_request()

    result = HighsHorizonOptimizer(time_limit_seconds=5.0).solve(request)

    assert HighsOptimizer(time_limit_seconds=5.0).solve(request.first_event_request()).transfers_in
    assert result.weighted_net_expected_points == pytest.approx(exhaustive_horizon(request))
    first, second = result.events
    assert first.transfers_in == ()
    assert first.free_transfers_before == 1
    assert first.free_transfers_next_event == 2
    assert second.transfers_in == (4, 5)
    assert second.transfers_out == (1, 2)
    assert second.paid_transfers == 0
    assert second.squad_element_ids == (4, 5)
    assert result.weighted_net_expected_points == 45.0
    assert result.price_scenario == "provided_event_prices"
    assert result.chip_scenario == "none"
    assert result.evidence_level == "experimental"


def test_horizon_captain_and_vice_are_midfielders_or_forwards() -> None:
    positions = tuple(
        PositionConstraint(
            position_id=position_id,
            squad_count=1,
            lineup_minimum=1,
            lineup_maximum=1,
        )
        for position_id in range(1, 5)
    )
    request = HorizonOptimizationRequest(
        events=(
            HorizonEvent(event=6, prediction_cutoff=CUTOFF, objective_weight=1.0),
            HorizonEvent(
                event=7,
                prediction_cutoff=CUTOFF + timedelta(days=7),
                objective_weight=1.0,
            ),
        ),
        forecasts=tuple(
            forecast(element_id, event, points, position_id=position_id)
            for event in (6, 7)
            for element_id, position_id, points in (
                (1, 1, 12.0),
                (2, 2, 11.0),
                (3, 3, 6.0),
                (4, 4, 5.0),
            )
        ),
        current_squad=tuple(
            CurrentSquadPlayer(element_id=element_id, selling_price_tenths=50)
            for element_id in range(1, 5)
        ),
        bank_tenths=0,
        available_free_transfers=0,
        state_evidence=state_evidence(),
        price_scenario="provided_event_prices",
        objective="expected_value",
        chip_scenario="none",
        rules=rules(squad_size=4, lineup_size=4, positions=positions),
    )

    result = HighsHorizonOptimizer(time_limit_seconds=5.0).solve(request)

    assert result.events[0].captain_element_id == 3
    assert result.events[0].vice_captain_element_id == 4


def test_horizon_free_transfers_never_exceed_sourced_cap() -> None:
    request = horizon_request().model_copy(
        update={
            "available_free_transfers": 2,
            "forecasts": tuple(
                row.model_copy(update={"expected_points": 5.0})
                for row in horizon_request().forecasts
            ),
        }
    )

    result = HighsHorizonOptimizer(time_limit_seconds=5.0).solve(request)

    assert all(event.free_transfers_before <= 2 for event in result.events)
    assert all(event.free_transfers_next_event <= 2 for event in result.events)


def test_horizon_does_not_resell_players_acquired_inside_plan() -> None:
    request = horizon_request()
    points = {
        6: (1.0, 1.0, 10.0, 0.0, 0.0),
        7: (1.0, 1.0, 0.0, 12.0, 11.0),
    }
    request = HorizonOptimizationRequest.model_validate(
        {
            **request.model_dump(),
            "forecasts": tuple(
                row.model_copy(update={"expected_points": points[row.event][row.element_id - 1]})
                for row in request.forecasts
            ),
        }
    )

    result = HighsHorizonOptimizer(time_limit_seconds=5.0).solve(request)

    acquired: set[int] = set()
    for event in result.events:
        assert acquired.isdisjoint(event.transfers_out)
        acquired.update(event.transfers_in)


def test_horizon_rejects_future_or_inconsistent_forecasts() -> None:
    request = horizon_request()
    late = tuple(
        row.model_copy(
            update={
                "data_available_at": (
                    CUTOFF + timedelta(days=7, seconds=1)
                    if row.event == 7 and row.element_id == 1
                    else row.data_available_at
                )
            }
        )
        for row in request.forecasts
    )
    with pytest.raises(ValidationError, match="after its prediction cutoff"):
        HorizonOptimizationRequest.model_validate({**request.model_dump(), "forecasts": late})

    missing = tuple(
        row for row in request.forecasts if not (row.event == 7 and row.element_id == 5)
    )
    with pytest.raises(ValidationError, match="same candidate elements"):
        HorizonOptimizationRequest.model_validate({**request.model_dump(), "forecasts": missing})


@settings(max_examples=20, deadline=None)
@given(
    event_six=st.tuples(*(st.integers(min_value=0, max_value=12) for _ in range(5))),
    event_seven=st.tuples(*(st.integers(min_value=0, max_value=12) for _ in range(5))),
)
def test_horizon_matches_dynamic_programming_oracle_across_generated_points(
    event_six: tuple[int, int, int, int, int],
    event_seven: tuple[int, int, int, int, int],
) -> None:
    request = horizon_request()
    points = {6: event_six, 7: event_seven}
    generated = HorizonOptimizationRequest.model_validate(
        {
            **request.model_dump(),
            "forecasts": tuple(
                row.model_copy(
                    update={"expected_points": float(points[row.event][row.element_id - 1])}
                )
                for row in request.forecasts
            ),
        }
    )

    result = HighsHorizonOptimizer(time_limit_seconds=5.0).solve(generated)

    assert result.weighted_net_expected_points == pytest.approx(
        exhaustive_horizon(generated),
        abs=1e-6,
    )


def test_horizon_stages_accept_the_previous_optimum_at_solver_tolerance() -> None:
    request = horizon_request()
    points = {
        6: (1e-6, 10.0, 9.5, 1.0, 0.0),
        7: (0.0, 0.0, 0.0, 10.0, 10.0),
    }
    generated = HorizonOptimizationRequest.model_validate(
        {
            **request.model_dump(),
            "forecasts": tuple(
                row.model_copy(update={"expected_points": points[row.event][row.element_id - 1]})
                for row in request.forecasts
            ),
        }
    )

    result = HighsHorizonOptimizer(time_limit_seconds=5.0).solve(generated)

    assert result.weighted_net_expected_points == pytest.approx(
        exhaustive_horizon(generated),
        abs=2e-6,
    )


def test_horizon_reuses_the_shared_optimum_handoff_slack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[float] = []

    def record(optimum: float) -> float:
        calls.append(optimum)
        return 2e-6

    monkeypatch.setattr(horizon_module, "optimum_handoff_slack", record)

    HighsHorizonOptimizer(time_limit_seconds=5.0).solve(horizon_request())

    assert len(calls) == 1


def exhaustive_horizon(request: HorizonOptimizationRequest) -> float:
    by_event = {
        event.event: {
            forecast.element_id: forecast
            for forecast in request.forecasts
            if forecast.event == event.event
        }
        for event in request.events
    }
    states = {
        (
            tuple(sorted(player.element_id for player in request.current_squad)),
            request.bank_tenths,
            request.available_free_transfers,
            tuple(sorted(player.element_id for player in request.current_squad)),
        ): 0.0
    }
    for event in request.events:
        next_states: dict[tuple[tuple[int, ...], int, int, tuple[int, ...]], float] = {}
        candidates = by_event[event.event]
        for (current_ids, bank, free_transfers, sellable_ids), accumulated in states.items():
            current_sale = {
                element_id: candidates[element_id].sell_price_tenths for element_id in current_ids
            }
            for squad_ids in combinations(candidates, request.rules.squad_size):
                incoming = set(squad_ids) - set(current_ids)
                outgoing = set(current_ids) - set(squad_ids)
                if not outgoing <= set(sellable_ids):
                    continue
                if len(incoming) > request.rules.transfer_cap:
                    continue
                bank_after = (
                    bank
                    + sum(current_sale[element_id] for element_id in outgoing)
                    - sum(candidates[element_id].buy_price_tenths for element_id in incoming)
                )
                if bank_after < 0:
                    continue
                paid = max(0, len(incoming) - free_transfers)
                unused = free_transfers - min(len(incoming), free_transfers)
                next_free = min(
                    request.rules.transfer_rules.maximum_free_transfers,
                    unused + request.rules.transfer_rules.weekly_free_transfers,
                )
                points = sum(candidates[element_id].expected_points for element_id in squad_ids)
                points += max(
                    candidates[element_id].expected_points
                    for element_id in squad_ids
                    if is_captain_eligible(candidates[element_id].position_id)
                )
                net = event.objective_weight * (
                    points - paid * request.rules.transfer_rules.transfer_cost_points
                )
                next_sellable = tuple(sorted(set(sellable_ids) - outgoing))
                key = (tuple(sorted(squad_ids)), bank_after, next_free, next_sellable)
                next_states[key] = max(next_states.get(key, -inf), accumulated + net)
        states = next_states
    return max(states.values())
