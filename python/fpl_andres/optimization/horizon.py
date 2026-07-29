from __future__ import annotations

import math
from collections import defaultdict
from typing import Literal

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from fpl_andres.optimization.contracts import (
    HorizonEventPlan,
    HorizonOptimizationRequest,
    HorizonOptimizationResult,
)
from fpl_andres.optimization.highs import OptimizationError


class HighsHorizonOptimizer:
    def __init__(self, *, time_limit_seconds: float) -> None:
        if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds must be finite and positive")
        self._time_limit_seconds = time_limit_seconds

    def solve(self, request: HorizonOptimizationRequest) -> HorizonOptimizationResult:
        events = request.events
        event_count = len(events)
        player_ids = tuple(
            sorted(
                forecast.element_id
                for forecast in request.forecasts
                if forecast.event == events[0].event
            )
        )
        player_count = len(player_ids)
        player_index = {element_id: index for index, element_id in enumerate(player_ids)}
        forecasts = {
            (forecast.event, forecast.element_id): forecast for forecast in request.forecasts
        }
        block_size = event_count * player_count
        squad_offset = 0
        lineup_offset = block_size
        captain_offset = 2 * block_size
        transfer_in_offset = 3 * block_size
        transfer_out_offset = 4 * block_size
        paid_offset = 5 * block_size
        free_offset = paid_offset + event_count
        free_used_offset = free_offset + event_count + 1
        free_compare_offset = free_used_offset + event_count
        cap_compare_offset = free_compare_offset + event_count
        bank_offset = cap_compare_offset + event_count
        variable_count = bank_offset + event_count + 1
        current = {player.element_id: player for player in request.current_squad}

        def variable(offset: int, event_index: int, player: int) -> int:
            return offset + event_index * player_count + player

        rows: list[np.ndarray] = []
        lower_bounds: list[float] = []
        upper_bounds: list[float] = []

        def add_constraint(
            coefficients: dict[int, float],
            *,
            lower: float = -np.inf,
            upper: float = np.inf,
        ) -> None:
            row = np.zeros(variable_count, dtype=np.float64)
            for index, coefficient in coefficients.items():
                row[index] = coefficient
            rows.append(row)
            lower_bounds.append(lower)
            upper_bounds.append(upper)

        objective = np.zeros(variable_count, dtype=np.float64)
        for event_index, event in enumerate(events):
            for element_id, index in player_index.items():
                points = forecasts[(event.event, element_id)].expected_points
                objective[variable(lineup_offset, event_index, index)] = (
                    -event.objective_weight * points
                )
                objective[variable(captain_offset, event_index, index)] = (
                    -event.objective_weight * points
                )
            objective[paid_offset + event_index] = (
                event.objective_weight * request.rules.transfer_rules.transfer_cost_points
            )

        for event_index, event in enumerate(events):
            add_constraint(
                {variable(squad_offset, event_index, index): 1.0 for index in range(player_count)},
                lower=request.rules.squad_size,
                upper=request.rules.squad_size,
            )
            add_constraint(
                {variable(lineup_offset, event_index, index): 1.0 for index in range(player_count)},
                lower=request.rules.lineup_size,
                upper=request.rules.lineup_size,
            )
            add_constraint(
                {
                    variable(captain_offset, event_index, index): 1.0
                    for index in range(player_count)
                },
                lower=1.0,
                upper=1.0,
            )
            for element_id, index in player_index.items():
                squad_variable = variable(squad_offset, event_index, index)
                lineup_variable = variable(lineup_offset, event_index, index)
                captain_variable = variable(captain_offset, event_index, index)
                incoming_variable = variable(transfer_in_offset, event_index, index)
                outgoing_variable = variable(transfer_out_offset, event_index, index)
                add_constraint(
                    {lineup_variable: 1.0, squad_variable: -1.0},
                    upper=0.0,
                )
                add_constraint(
                    {captain_variable: 1.0, lineup_variable: -1.0},
                    upper=0.0,
                )
                flow = {
                    squad_variable: 1.0,
                    incoming_variable: -1.0,
                    outgoing_variable: 1.0,
                }
                if event_index == 0:
                    current_value = 1.0 if element_id in current else 0.0
                    add_constraint(flow, lower=current_value, upper=current_value)
                else:
                    flow[variable(squad_offset, event_index - 1, index)] = -1.0
                    add_constraint(flow, lower=0.0, upper=0.0)
                add_constraint(
                    {incoming_variable: 1.0, outgoing_variable: 1.0},
                    upper=1.0,
                )

            for position in request.rules.positions:
                position_indices = [
                    index
                    for element_id, index in player_index.items()
                    if forecasts[(event.event, element_id)].position_id == position.position_id
                ]
                add_constraint(
                    {variable(squad_offset, event_index, index): 1.0 for index in position_indices},
                    lower=position.squad_count,
                    upper=position.squad_count,
                )
                add_constraint(
                    {
                        variable(lineup_offset, event_index, index): 1.0
                        for index in position_indices
                    },
                    lower=position.lineup_minimum,
                    upper=position.lineup_maximum,
                )

            team_indices: defaultdict[int, list[int]] = defaultdict(list)
            for element_id, index in player_index.items():
                team_indices[forecasts[(event.event, element_id)].team_id].append(index)
            for indices in team_indices.values():
                add_constraint(
                    {variable(squad_offset, event_index, index): 1.0 for index in indices},
                    upper=request.rules.club_limit,
                )

            incoming_variables = {
                variable(transfer_in_offset, event_index, index): 1.0
                for index in range(player_count)
            }
            outgoing_variables = {
                variable(transfer_out_offset, event_index, index): 1.0
                for index in range(player_count)
            }
            add_constraint(
                incoming_variables,
                upper=request.rules.transfer_cap,
            )
            add_constraint(
                {
                    **incoming_variables,
                    **{key: -value for key, value in outgoing_variables.items()},
                },
                lower=0.0,
                upper=0.0,
            )

            bank_flow = {
                bank_offset + event_index + 1: 1.0,
                bank_offset + event_index: -1.0,
            }
            for element_id, index in player_index.items():
                event_forecast = forecasts[(event.event, element_id)]
                bank_flow[
                    variable(transfer_out_offset, event_index, index)
                ] = -event_forecast.sell_price_tenths
                bank_flow[variable(transfer_in_offset, event_index, index)] = (
                    event_forecast.buy_price_tenths
                )
            add_constraint(bank_flow, lower=0.0, upper=0.0)

            free_before = free_offset + event_index
            free_after = free_offset + event_index + 1
            free_used = free_used_offset + event_index
            free_compare = free_compare_offset + event_index
            cap_compare = cap_compare_offset + event_index
            paid = paid_offset + event_index
            transfer_count = incoming_variables
            big_m = float(
                request.rules.transfer_cap
                + request.rules.transfer_rules.maximum_free_transfers
                + request.rules.transfer_rules.weekly_free_transfers
            )
            add_constraint(
                {free_used: 1.0, **{key: -value for key, value in transfer_count.items()}},
                upper=0.0,
            )
            add_constraint({free_used: 1.0, free_before: -1.0}, upper=0.0)
            add_constraint(
                {
                    free_used: 1.0,
                    **{key: -value for key, value in transfer_count.items()},
                    free_compare: big_m,
                },
                lower=0.0,
            )
            add_constraint(
                {
                    free_used: 1.0,
                    free_before: -1.0,
                    free_compare: -big_m,
                },
                lower=-big_m,
            )
            add_constraint(
                {
                    paid: 1.0,
                    free_used: 1.0,
                    **{key: -value for key, value in transfer_count.items()},
                },
                lower=0.0,
                upper=0.0,
            )
            weekly_award = request.rules.transfer_rules.weekly_free_transfers
            maximum_free = request.rules.transfer_rules.maximum_free_transfers
            add_constraint(
                {free_after: 1.0, free_before: -1.0, free_used: 1.0},
                upper=weekly_award,
            )
            add_constraint(
                {
                    free_after: 1.0,
                    free_before: -1.0,
                    free_used: 1.0,
                    cap_compare: big_m,
                },
                lower=weekly_award,
            )
            add_constraint(
                {free_after: 1.0, cap_compare: -big_m},
                lower=maximum_free - big_m,
            )

        for element_id, index in player_index.items():
            add_constraint(
                {
                    variable(transfer_out_offset, event_index, index): 1.0
                    for event_index in range(event_count)
                },
                upper=1.0 if element_id in current else 0.0,
            )

        add_constraint(
            {free_offset: 1.0},
            lower=request.available_free_transfers,
            upper=request.available_free_transfers,
        )
        add_constraint(
            {bank_offset: 1.0},
            lower=request.bank_tenths,
            upper=request.bank_tenths,
        )

        lower_variable_bounds = np.zeros(variable_count, dtype=np.float64)
        upper_variable_bounds = np.full(variable_count, np.inf, dtype=np.float64)
        upper_variable_bounds[: 5 * block_size] = 1.0
        upper_variable_bounds[paid_offset:free_offset] = request.rules.transfer_cap
        upper_variable_bounds[free_offset:free_used_offset] = (
            request.rules.transfer_rules.maximum_free_transfers
        )
        upper_variable_bounds[free_used_offset:free_compare_offset] = (
            request.rules.transfer_rules.maximum_free_transfers
        )
        upper_variable_bounds[free_compare_offset:bank_offset] = 1.0

        def optimize(stage_objective: np.ndarray, stage: str) -> np.ndarray:
            result = milp(
                stage_objective,
                integrality=np.ones(variable_count, dtype=np.int32),
                bounds=Bounds(lower_variable_bounds, upper_variable_bounds),
                constraints=LinearConstraint(
                    np.vstack(rows),
                    np.asarray(lower_bounds),
                    np.asarray(upper_bounds),
                ),
                options={
                    "time_limit": self._time_limit_seconds,
                    "mip_rel_gap": 0.0,
                    "presolve": True,
                },
            )
            if result.status != 0 or result.x is None:
                raise OptimizationError(
                    f"HiGHS did not prove the horizon {stage} optimum: {result.message}"
                )
            return result.x

        primary_solution = optimize(objective, "primary")
        primary_optimum = float(np.dot(objective, primary_solution))
        add_constraint(
            {
                index: float(coefficient)
                for index, coefficient in enumerate(objective)
                if coefficient != 0
            },
            upper=primary_optimum + 1e-8,
        )
        transfer_objective = np.zeros(variable_count, dtype=np.float64)
        for event_index in range(event_count):
            for index in range(player_count):
                transfer_objective[variable(transfer_in_offset, event_index, index)] = 1.0
        transfer_solution = optimize(transfer_objective, "minimum-transfer")
        minimum_transfers = round(float(np.dot(transfer_objective, transfer_solution)))
        add_constraint(
            {
                index: float(coefficient)
                for index, coefficient in enumerate(transfer_objective)
                if coefficient != 0
            },
            lower=minimum_transfers,
            upper=minimum_transfers,
        )
        quality_objective = np.zeros(variable_count, dtype=np.float64)
        for event_index, event in enumerate(events):
            for element_id, index in player_index.items():
                quality_objective[variable(squad_offset, event_index, index)] = (
                    -event.objective_weight * forecasts[(event.event, element_id)].expected_points
                    + index * 1e-9
                )
        solution = optimize(quality_objective, "squad-quality")

        plans: list[HorizonEventPlan] = []
        for event_index, event in enumerate(events):
            event_forecasts = {
                element_id: forecasts[(event.event, element_id)] for element_id in player_ids
            }
            squad = _selected(
                player_ids,
                solution,
                squad_offset,
                event_index,
                player_count,
            )
            starters = _selected(
                player_ids,
                solution,
                lineup_offset,
                event_index,
                player_count,
            )
            captain = _selected(
                player_ids,
                solution,
                captain_offset,
                event_index,
                player_count,
            )[0]
            vice = max(
                (element_id for element_id in starters if element_id != captain),
                key=lambda element_id: (
                    event_forecasts[element_id].expected_points,
                    -element_id,
                ),
            )
            incoming = _selected(
                player_ids,
                solution,
                transfer_in_offset,
                event_index,
                player_count,
            )
            outgoing = _selected(
                player_ids,
                solution,
                transfer_out_offset,
                event_index,
                player_count,
            )
            paid = round(solution[paid_offset + event_index])
            free_before = round(solution[free_offset + event_index])
            free_used = round(solution[free_used_offset + event_index])
            free_next = round(solution[free_offset + event_index + 1])
            transfer_cost = paid * request.rules.transfer_rules.transfer_cost_points
            projected = (
                sum(event_forecasts[element_id].expected_points for element_id in starters)
                + event_forecasts[captain].expected_points
            )
            plans.append(
                HorizonEventPlan(
                    event=event.event,
                    objective_weight=event.objective_weight,
                    squad_element_ids=squad,
                    starter_element_ids=starters,
                    bench_element_ids=tuple(
                        sorted(
                            set(squad) - set(starters),
                            key=lambda element_id: (
                                -event_forecasts[element_id].expected_points,
                                element_id,
                            ),
                        )
                    ),
                    captain_element_id=captain,
                    vice_captain_element_id=vice,
                    transfers_in=incoming,
                    transfers_out=outgoing,
                    free_transfers_before=free_before,
                    free_transfers_used=free_used,
                    paid_transfers=paid,
                    free_transfers_next_event=free_next,
                    transfer_cost_points=transfer_cost,
                    projected_points_before_cost=projected,
                    net_expected_points=projected - transfer_cost,
                    bank_after_tenths=round(solution[bank_offset + event_index + 1]),
                )
            )

        evidence_level: Literal["inferred", "experimental"] = (
            "experimental"
            if any(forecast.evidence_level == "experimental" for forecast in request.forecasts)
            else "inferred"
        )
        source_hashes = tuple(
            sorted(
                {
                    request.rules.published_rules_hash,
                    request.rules.transfer_rules.source_hash,
                    request.state_evidence.manager_overrides_hash,
                    *request.state_evidence.public_source_hashes,
                    *(
                        source_hash
                        for forecast in request.forecasts
                        for source_hash in forecast.source_hashes
                    ),
                }
            )
        )
        return HorizonOptimizationResult(
            solver="scipy-highs",
            solver_status="optimal",
            objective=request.objective,
            price_scenario=request.price_scenario,
            chip_scenario=request.chip_scenario,
            events=tuple(plans),
            weighted_net_expected_points=sum(
                plan.objective_weight * plan.net_expected_points for plan in plans
            ),
            evidence_level=evidence_level,
            data_available_at=max(
                request.rules.data_available_at,
                request.state_evidence.public_data_available_at,
                request.state_evidence.overrides_updated_at,
                *(forecast.data_available_at for forecast in request.forecasts),
            ),
            source_hashes=source_hashes,
            reason_codes=(
                "scipy_highs_horizon_optimal",
                f"events={event_count}",
                f"transfers={sum(len(plan.transfers_in) for plan in plans)}",
            ),
        )


def _selected(
    player_ids: tuple[int, ...],
    solution: np.ndarray,
    offset: int,
    event_index: int,
    player_count: int,
) -> tuple[int, ...]:
    return tuple(
        element_id
        for index, element_id in enumerate(player_ids)
        if solution[offset + event_index * player_count + index] > 0.5
    )
