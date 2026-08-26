from __future__ import annotations

import math
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_array

from fpl_andres.optimization.contracts import (
    HorizonEventPlan,
    HorizonOptimizationRequest,
    HorizonOptimizationResult,
)
from fpl_andres.optimization.highs import (
    CAPTAIN_CEILING_WEIGHT,
    OptimizationError,
    optimum_handoff_slack,
)
from fpl_andres.optimization.horizon_model import HorizonModel, build_constraints
from fpl_andres.positions import is_captain_eligible

FloatArray = NDArray[np.float64]


class HighsHorizonOptimizer:
    def __init__(self, *, time_limit_seconds: float) -> None:
        if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds must be finite and positive")
        self._time_limit_seconds = time_limit_seconds

    def solve(self, request: HorizonOptimizationRequest) -> HorizonOptimizationResult:
        # The layout and every constraint block live in
        # `horizon_model`, one function per rule of the game. What remains here
        # is the three-stage solve, which is the part that is about
        # optimisation rather than about Fantasy Premier League.
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
        forecasts = {
            (forecast.event, forecast.element_id): forecast for forecast in request.forecasts
        }
        model = HorizonModel(request=request, player_ids=player_ids, forecasts=forecasts)
        build_constraints(model)

        player_index = model.player_index
        variable_count = model.variable_count
        block_size = model.block_size
        squad_offset = model.squad_offset
        lineup_offset = model.lineup_offset
        captain_offset = model.captain_offset
        transfer_in_offset = model.transfer_in_offset
        transfer_out_offset = model.transfer_out_offset
        paid_offset = model.paid_offset
        free_offset = model.free_offset
        free_used_offset = model.free_used_offset
        free_compare_offset = model.free_compare_offset
        bank_offset = model.bank_offset
        variable = model.variable
        add_constraint = model.add
        constraint_rows = model.rows
        constraint_columns = model.columns
        constraint_values = model.values
        lower_bounds = model.lower_bounds
        upper_bounds = model.upper_bounds

        objective = np.zeros(variable_count, dtype=np.float64)
        for event_index, event in enumerate(events):
            for element_id, index in player_index.items():
                forecast = forecasts[(event.event, element_id)]
                points = forecast.expected_points
                objective[variable(lineup_offset, event_index, index)] = (
                    -event.objective_weight * points
                )
                # The same armband valuation the single-event solver uses. On
                # the mean alone this picked one captain and the chip planner
                # then scored the armband on a mean/ceiling blend, so in any
                # week where the two rules disagreed the plan captained the man
                # its own scoring rule called second best.
                ceiling = forecast.expected_ceiling
                objective[variable(captain_offset, event_index, index)] = (
                    -event.objective_weight
                    * (
                        points * (1.0 - CAPTAIN_CEILING_WEIGHT)
                        + (points if ceiling is None else ceiling) * CAPTAIN_CEILING_WEIGHT
                    )
                )
            objective[paid_offset + event_index] = (
                # Full price, not the event's weight. A lookahead gameweek is
                # discounted because its points are speculative; the four
                # points a hit costs are not. Weighting the cost too made a
                # transfer in the second half of a window cost two points, so
                # the solver bought there and the next window inherited a squad
                # it had overpaid for.
                request.rules.transfer_rules.transfer_cost_points
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

        def optimize(stage_objective: FloatArray, stage: str) -> FloatArray:
            # Rebuilt per stage rather than hoisted: later stages append
            # constraints, and a matrix built once would silently solve the
            # earlier problem. Assembling from triples is cheap; getting this
            # wrong would not be visible in the answer.
            matrix = coo_array(
                (
                    np.asarray(constraint_values, dtype=np.float64),
                    (
                        np.asarray(constraint_rows, dtype=np.int64),
                        np.asarray(constraint_columns, dtype=np.int64),
                    ),
                ),
                shape=(model.constraint_count, variable_count),
            ).tocsr()
            result = milp(
                stage_objective,
                integrality=np.ones(variable_count, dtype=np.int32),
                bounds=Bounds(lower_variable_bounds, upper_variable_bounds),
                constraints=LinearConstraint(
                    matrix,
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
            upper=primary_optimum + optimum_handoff_slack(primary_optimum),
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
            if not is_captain_eligible(event_forecasts[captain].position_id):
                raise OptimizationError("HiGHS returned an ineligible horizon captain")
            vice = max(
                (
                    element_id
                    for element_id in starters
                    if element_id != captain
                    and is_captain_eligible(event_forecasts[element_id].position_id)
                ),
                key=lambda element_id: (
                    event_forecasts[element_id].expected_points,
                    -element_id,
                ),
            )
            if not is_captain_eligible(event_forecasts[vice].position_id):
                raise OptimizationError("HiGHS returned an ineligible horizon vice-captain")
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
    solution: FloatArray,
    offset: int,
    event_index: int,
    player_count: int,
) -> tuple[int, ...]:
    return tuple(
        element_id
        for index, element_id in enumerate(player_ids)
        if solution[offset + event_index * player_count + index] > 0.5
    )


__all__ = [
    "HighsHorizonOptimizer",
]
