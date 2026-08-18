from __future__ import annotations

import math
from collections import defaultdict
from typing import Literal

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from fpl_andres.optimization.contracts import (
    OptimizationPlayer,
    OptimizationRequest,
    OptimizationResult,
)


class OptimizationError(RuntimeError):
    """Raised when the optimizer cannot prove an optimal valid squad."""


# HiGHS proves a MIP optimum only to its own feasibility tolerance, which
# defaults to 1e-6. Pinning a follow-up solve tighter than that lets it declare
# infeasible against an optimum it produced itself, which is what happened on
# the generated case (0.0, 2.0, 7.0, 1e-07, 0.0, 8.125).
_MIP_FEASIBILITY_TOLERANCE = 1e-6

# Lexicographic tie-breaks, expressed as a single objective.
#
# When several squads score identically the solver may return any of them, and
# "any of them" means a different squad on a different machine or a different
# HiGHS build. That is unacceptable here: the same evidence must produce the
# same recommendation, or nothing downstream can be reproduced.
#
# The fix is a penalty on the element index, small enough that it can never
# outrank a real points difference. Three scales, because the tie-breaks are
# ordered: squad membership is decided first, then who starts, then who wears
# the armband. Each is a hundred times smaller than the one above it, so no
# accumulation of lower-priority terms can overturn a higher-priority one --
# fifteen players at 1e-11 sum to 1.5e-10, well under a single 1e-9 step.
#
# All three are far below _MIP_FEASIBILITY_TOLERANCE, so none of them can move
# a solution the solver would otherwise consider optimal.
_SQUAD_TIE_BREAK = 1e-9
_LINEUP_TIE_BREAK = 1e-11
_CAPTAIN_TIE_BREAK = 1e-13

# How much of the armband's value is read off the ceiling rather than the mean.
# Assumed, not fitted: it is a statement about what you are playing for, not a
# measurement. Measured on 2025-26 by `cli/backtest_ceiling.py`, a player beats
# his own published ceiling in 13.6% of appearances, so the ceiling is a real
# number rather than a flourish -- but how much to chase it is a strategy.
# A third leans the armband toward a haul without handing it to a lottery
# ticket who averages nothing.
CAPTAIN_CEILING_WEIGHT = 1.0 / 3.0


def optimum_handoff_slack(optimum: float) -> float:
    """Slack for re-solving against a proven optimum, scaled to its magnitude.

    Load-bearing for every optimality proof, and previously
    uncommented.

    The three-stage solve pins each stage against the previous stage's optimum.
    Pinning it exactly cannot work: HiGHS proved that optimum only to its own
    feasibility tolerance, so re-imposing it as an equality asks the solver to
    hit a number more precisely than it claimed to know it, and it answers
    infeasible against its own answer.

    Relative *and* absolute, because neither alone is right across the range.
    An absolute tolerance is far too loose for an objective near zero -- a
    bench-boost margin of 0.4 points would be swamped -- and far too tight for
    one in the hundreds, where 1e-6 is below the float spacing of the number
    itself. The max of the two tracks the magnitude and never drops below what
    the solver guarantees. The handoff needs two tolerances: the first optimum
    may already sit one tolerance from the mathematical bound, and the next
    solve applies its own feasibility tolerance when reading that bound.
    """
    return max(2.0 * _MIP_FEASIBILITY_TOLERANCE, abs(optimum) * _SQUAD_TIE_BREAK)


class HighsOptimizer:
    def __init__(self, *, time_limit_seconds: float) -> None:
        if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds must be finite and positive")
        self._time_limit_seconds = time_limit_seconds

    def solve(self, request: OptimizationRequest) -> OptimizationResult:
        players = tuple(sorted(request.players, key=lambda player: player.element_id))
        player_count = len(players)
        # `*_offset` is the first column of a block, and a
        # player's column within it is `offset + index`. `paid_transfer_column`
        # is a single column, not the start of a block, and was previously
        # named `paid_transfer_index` -- which read like a player index and sat
        # in the same arithmetic as one.
        squad_offset = 0
        lineup_offset = player_count
        captain_offset = 2 * player_count
        paid_transfer_column = 3 * player_count
        variable_count = paid_transfer_column + 1
        current = {player.element_id: player for player in request.current_squad}

        objective = np.zeros(variable_count, dtype=np.float64)
        for index, player in enumerate(players):
            objective[lineup_offset + index] = -player.expected_points
            # The armband is the one pick where upside matters more than the
            # average. Doubling a steady four-point return gains four points;
            # doubling a man capable of fifteen is what wins a mini-league, and
            # a season of averages finishes mid-table. So the *extra* copy the
            # captaincy buys is valued partly at his ceiling.
            ceiling = player.expected_ceiling
            objective[captain_offset + index] = -(
                player.expected_points * (1.0 - CAPTAIN_CEILING_WEIGHT)
                + (ceiling if ceiling is not None else player.expected_points)
                * CAPTAIN_CEILING_WEIGHT
            )
        objective[paid_transfer_column] = request.rules.transfer_rules.transfer_cost_points

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
            for variable, coefficient in coefficients.items():
                row[variable] = coefficient
            rows.append(row)
            lower_bounds.append(lower)
            upper_bounds.append(upper)

        add_constraint(
            {squad_offset + index: 1.0 for index in range(player_count)},
            lower=request.rules.squad_size,
            upper=request.rules.squad_size,
        )
        add_constraint(
            {lineup_offset + index: 1.0 for index in range(player_count)},
            lower=request.rules.lineup_size,
            upper=request.rules.lineup_size,
        )
        add_constraint(
            {captain_offset + index: 1.0 for index in range(player_count)},
            lower=1.0,
            upper=1.0,
        )
        for index in range(player_count):
            add_constraint(
                {lineup_offset + index: 1.0, squad_offset + index: -1.0},
                upper=0.0,
            )
            add_constraint(
                {captain_offset + index: 1.0, lineup_offset + index: -1.0},
                upper=0.0,
            )

        for position in request.rules.positions:
            position_indices = [
                index
                for index, player in enumerate(players)
                if player.position_id == position.position_id
            ]
            add_constraint(
                {squad_offset + index: 1.0 for index in position_indices},
                lower=position.squad_count,
                upper=position.squad_count,
            )
            add_constraint(
                {lineup_offset + index: 1.0 for index in position_indices},
                lower=position.lineup_minimum,
                upper=position.lineup_maximum,
            )

        team_indices: defaultdict[int, list[int]] = defaultdict(list)
        for index, player in enumerate(players):
            team_indices[player.team_id].append(index)
        for indices in team_indices.values():
            add_constraint(
                {squad_offset + index: 1.0 for index in indices},
                upper=request.rules.club_limit,
            )

        budget_coefficients: dict[int, float] = {}
        total_current_sale_value = 0
        for index, player in enumerate(players):
            current_player = current.get(player.element_id)
            if current_player is None:
                budget_coefficients[squad_offset + index] = player.buy_price_tenths
            else:
                budget_coefficients[squad_offset + index] = current_player.selling_price_tenths
                total_current_sale_value += current_player.selling_price_tenths
        add_constraint(
            budget_coefficients,
            upper=request.bank_tenths + total_current_sale_value,
        )

        incoming_indices = [
            index for index, player in enumerate(players) if player.element_id not in current
        ]
        transfer_coefficients = {squad_offset + index: 1.0 for index in incoming_indices}
        transfer_coefficients[paid_transfer_column] = -1.0
        add_constraint(
            transfer_coefficients,
            upper=request.available_free_transfers,
        )
        add_constraint(
            {squad_offset + index: 1.0 for index in incoming_indices},
            upper=request.rules.transfer_cap,
        )

        lower_variable_bounds = np.zeros(variable_count, dtype=np.float64)
        upper_variable_bounds = np.ones(variable_count, dtype=np.float64)
        upper_variable_bounds[paid_transfer_column] = request.rules.transfer_cap

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
                    f"HiGHS did not prove the {stage} optimum: {result.message}"
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
        for index in incoming_indices:
            transfer_objective[squad_offset + index] = 1.0
        transfer_solution = optimize(transfer_objective, "minimum-transfer")
        minimum_transfers = round(float(np.dot(transfer_objective, transfer_solution)))
        add_constraint(
            {squad_offset + index: 1.0 for index in incoming_indices},
            lower=minimum_transfers,
            upper=minimum_transfers,
        )

        squad_quality_objective = np.zeros(variable_count, dtype=np.float64)
        for index, player in enumerate(players):
            # Lexicographic, highest priority first. See the constants: each
            # scale is a hundred times smaller than the one above it, so no
            # accumulation of lower-priority terms can overturn a higher one.
            squad_quality_objective[squad_offset + index] = (
                -player.expected_points + index * _SQUAD_TIE_BREAK
            )
            squad_quality_objective[lineup_offset + index] = index * _LINEUP_TIE_BREAK
            squad_quality_objective[captain_offset + index] = index * _CAPTAIN_TIE_BREAK
        solution = optimize(squad_quality_objective, "squad-quality")

        selected = _selected(players, solution, squad_offset)
        starters = _selected(players, solution, lineup_offset)
        captains = _selected(players, solution, captain_offset)
        if len(captains) != 1:
            raise OptimizationError("HiGHS returned an invalid captain selection")
        captain = captains[0]
        vice = max(
            (player for player in starters if player.element_id != captain.element_id),
            key=lambda player: (player.expected_points, -player.element_id),
        )
        bench = tuple(
            sorted(
                (player for player in selected if player not in starters),
                key=lambda player: (-player.expected_points, player.element_id),
            )
        )
        selected_ids = {player.element_id for player in selected}
        current_ids = set(current)
        transfers_in = tuple(sorted(selected_ids - current_ids))
        transfers_out = tuple(sorted(current_ids - selected_ids))
        paid_transfers = max(
            0,
            len(transfers_in) - request.available_free_transfers,
        )
        transfer_cost = paid_transfers * request.rules.transfer_rules.transfer_cost_points
        projected_points = sum(player.expected_points for player in starters) + (
            captain.expected_points
        )
        bank_after = (
            request.bank_tenths
            + sum(current[element_id].selling_price_tenths for element_id in transfers_out)
            - sum(
                next(
                    player.buy_price_tenths for player in players if player.element_id == element_id
                )
                for element_id in transfers_in
            )
        )
        source_hashes = tuple(
            sorted(
                {
                    request.rules.published_rules_hash,
                    request.rules.transfer_rules.source_hash,
                    request.state_evidence.manager_overrides_hash,
                    *request.state_evidence.public_source_hashes,
                    *(source_hash for player in players for source_hash in player.source_hashes),
                }
            )
        )
        evidence_level: Literal["inferred", "experimental"] = (
            "experimental"
            if any(player.evidence_level == "experimental" for player in players)
            else "inferred"
        )
        return OptimizationResult(
            solver="scipy-highs",
            solver_status="optimal",
            objective=request.objective,
            price_scenario=request.price_scenario,
            chip_scenario=request.chip_scenario,
            squad_element_ids=tuple(sorted(selected_ids)),
            starter_element_ids=tuple(sorted(player.element_id for player in starters)),
            bench_element_ids=tuple(player.element_id for player in bench),
            captain_element_id=captain.element_id,
            vice_captain_element_id=vice.element_id,
            transfers_in=transfers_in,
            transfers_out=transfers_out,
            free_transfers_available=request.available_free_transfers,
            paid_transfers=paid_transfers,
            transfer_cost_points=transfer_cost,
            projected_points_before_cost=projected_points,
            net_expected_points=projected_points - transfer_cost,
            bank_after_tenths=bank_after,
            evidence_level=evidence_level,
            data_available_at=max(
                request.rules.data_available_at,
                request.state_evidence.public_data_available_at,
                request.state_evidence.overrides_updated_at,
                *(player.data_available_at for player in players),
            ),
            source_hashes=source_hashes,
            reason_codes=(
                "scipy_highs_optimal",
                f"transfers={len(transfers_in)}",
                f"paid_transfers={paid_transfers}",
            ),
        )


def _selected(
    players: tuple[OptimizationPlayer, ...],
    solution: np.ndarray,
    offset: int,
) -> tuple[OptimizationPlayer, ...]:
    return tuple(player for index, player in enumerate(players) if solution[offset + index] > 0.5)


__all__ = [
    "HighsOptimizer",
    "OptimizationError",
    "optimum_handoff_slack",
]
