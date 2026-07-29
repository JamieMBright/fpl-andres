import json
from datetime import UTC, datetime, timedelta
from itertools import combinations
from math import inf
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from fpl_andres.optimization.contracts import (
    CurrentSquadPlayer,
    OptimizationPlayer,
    OptimizationRequest,
    OptimizationResult,
    OptimizationRules,
    OptimizationStateEvidence,
    PositionConstraint,
    TransferRulesAddendum,
    optimization_rules_from_snapshot,
)
from fpl_andres.optimization.highs import HighsOptimizer
from fpl_andres.rules import RulesSnapshot

CUTOFF = datetime(2026, 9, 12, 9, tzinfo=UTC)
HASH_A = f"sha256:{'a' * 64}"
HASH_B = f"sha256:{'b' * 64}"
HASH_C = f"sha256:{'c' * 64}"
HASH_D = f"sha256:{'d' * 64}"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fpl" / "bootstrap_rules_2026_27.json"


def transfer_rules(**updates: object) -> TransferRulesAddendum:
    values: dict[str, object] = {
        "season": "2026-27",
        "weekly_free_transfers": 1,
        "maximum_free_transfers": 2,
        "transfer_cost_points": 4,
        "source_reference": "https://fantasy.premierleague.com/help/rules",
        "source_hash": HASH_B,
        "data_available_at": CUTOFF - timedelta(days=1),
    }
    values.update(updates)
    return TransferRulesAddendum.model_validate(values)


def rules(
    *,
    squad_size: int = 4,
    lineup_size: int = 2,
    positions: tuple[PositionConstraint, ...] | None = None,
) -> OptimizationRules:
    constraints = positions or (
        PositionConstraint(position_id=1, squad_count=2, lineup_minimum=1, lineup_maximum=1),
        PositionConstraint(position_id=2, squad_count=2, lineup_minimum=1, lineup_maximum=1),
    )
    return OptimizationRules(
        season="2026-27",
        squad_size=squad_size,
        lineup_size=lineup_size,
        club_limit=2,
        transfer_cap=squad_size,
        positions=constraints,
        transfer_rules=transfer_rules(),
        published_rules_hash=HASH_A,
        data_available_at=CUTOFF - timedelta(days=1),
    )


def state_evidence(**updates: object) -> OptimizationStateEvidence:
    values: dict[str, object] = {
        "public_state_as_of": CUTOFF - timedelta(days=7),
        "public_data_available_at": CUTOFF - timedelta(hours=2),
        "overrides_updated_at": CUTOFF - timedelta(hours=1),
        "public_source_hashes": (HASH_C,),
        "manager_overrides_hash": HASH_D,
    }
    values.update(updates)
    return OptimizationStateEvidence.model_validate(values)


def player(
    element_id: int,
    *,
    team_id: int,
    position_id: int,
    points: float,
    price: int = 50,
    available_at: datetime | None = None,
) -> OptimizationPlayer:
    return OptimizationPlayer(
        season="2026-27",
        event=6,
        element_id=element_id,
        team_id=team_id,
        position_id=position_id,
        buy_price_tenths=price,
        expected_points=points,
        evidence_level="experimental",
        model_name="tiny-fixture",
        model_version="1",
        data_available_at=available_at or CUTOFF,
        source_hashes=(f"sha256:{element_id:064x}",),
    )


def test_highs_matches_independent_exhaustive_oracle() -> None:
    request = OptimizationRequest(
        event=6,
        prediction_cutoff=CUTOFF,
        players=(
            player(1, team_id=1, position_id=1, points=2.0),
            player(2, team_id=2, position_id=1, points=1.0),
            player(3, team_id=1, position_id=2, points=2.0),
            player(4, team_id=2, position_id=2, points=1.0),
            player(5, team_id=3, position_id=1, points=5.0),
            player(6, team_id=3, position_id=2, points=6.0),
        ),
        current_squad=tuple(
            CurrentSquadPlayer(element_id=element_id, selling_price_tenths=50)
            for element_id in range(1, 5)
        ),
        bank_tenths=0,
        available_free_transfers=1,
        state_evidence=state_evidence(),
        rules=rules(),
    )

    result = HighsOptimizer(time_limit_seconds=5.0).solve(request)

    assert result.net_expected_points == pytest.approx(exhaustive_optimum(request))
    assert result.squad_element_ids == (1, 2, 3, 6)
    assert result.starter_element_ids == (1, 6)
    assert result.captain_element_id == 6
    assert result.vice_captain_element_id == 1
    assert result.transfers_in == (6,)
    assert result.transfers_out == (4,)
    assert result.paid_transfers == 0
    assert result.bank_after_tenths == 0
    assert result.evidence_level == "experimental"
    assert HASH_A in result.source_hashes
    assert HASH_B in result.source_hashes
    assert HASH_C in result.source_hashes
    assert HASH_D in result.source_hashes


@pytest.mark.parametrize(
    ("candidate_points", "expected_transfer"),
    ((4.9, ()), (5.1, (3,))),
)
def test_paid_transfer_requires_gain_above_explicit_hit_cost(
    candidate_points: float,
    expected_transfer: tuple[int, ...],
) -> None:
    compact_rules = rules(
        squad_size=2,
        lineup_size=2,
        positions=(
            PositionConstraint(
                position_id=1,
                squad_count=2,
                lineup_minimum=2,
                lineup_maximum=2,
            ),
        ),
    )
    request = OptimizationRequest(
        event=6,
        prediction_cutoff=CUTOFF,
        players=(
            player(1, team_id=1, position_id=1, points=10.0),
            player(2, team_id=2, position_id=1, points=1.0),
            player(3, team_id=3, position_id=1, points=candidate_points),
        ),
        current_squad=(
            CurrentSquadPlayer(element_id=1, selling_price_tenths=50),
            CurrentSquadPlayer(element_id=2, selling_price_tenths=50),
        ),
        bank_tenths=0,
        available_free_transfers=0,
        state_evidence=state_evidence(),
        rules=compact_rules,
    )

    result = HighsOptimizer(time_limit_seconds=5.0).solve(request)

    assert result.transfers_in == expected_transfer


def test_request_rejects_forecast_available_after_cutoff() -> None:
    with pytest.raises(ValidationError, match="after prediction_cutoff"):
        OptimizationRequest(
            event=6,
            prediction_cutoff=CUTOFF,
            players=(
                player(
                    1,
                    team_id=1,
                    position_id=1,
                    points=2.0,
                    available_at=CUTOFF + timedelta(seconds=1),
                ),
                player(2, team_id=2, position_id=1, points=1.0),
            ),
            current_squad=(
                CurrentSquadPlayer(element_id=1, selling_price_tenths=50),
                CurrentSquadPlayer(element_id=2, selling_price_tenths=50),
            ),
            bank_tenths=0,
            available_free_transfers=1,
            state_evidence=state_evidence(),
            rules=rules(
                squad_size=2,
                lineup_size=2,
                positions=(
                    PositionConstraint(
                        position_id=1,
                        squad_count=2,
                        lineup_minimum=2,
                        lineup_maximum=2,
                    ),
                ),
            ),
        )


def test_transfer_cost_is_required_source_contract() -> None:
    values = transfer_rules().model_dump()
    del values["transfer_cost_points"]

    with pytest.raises(ValidationError, match="transfer_cost_points"):
        TransferRulesAddendum.model_validate(values)


def test_request_rejects_manager_state_updated_after_cutoff() -> None:
    invalid = compact_request((10.0, 1.0, 6.0)).model_copy(
        update={
            "state_evidence": state_evidence(overrides_updated_at=CUTOFF + timedelta(seconds=1))
        }
    )
    with pytest.raises(ValidationError, match="manager state became available"):
        OptimizationRequest.model_validate(invalid.model_dump())


def test_builds_optimizer_rules_from_exact_published_and_addendum_sources() -> None:
    document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    published = RulesSnapshot.from_bootstrap(
        document["payload"],
        season="2026-27",
        source_hash=HASH_A,
        weekly_free_transfers=1,
    )

    optimizer_rules = optimization_rules_from_snapshot(
        published,
        transfer_rules=transfer_rules(maximum_free_transfers=5),
        published_data_available_at=CUTOFF - timedelta(hours=12),
    )

    assert optimizer_rules.squad_size == 15
    assert optimizer_rules.lineup_size == 11
    assert optimizer_rules.club_limit == 3
    assert optimizer_rules.positions[0].squad_count == 2
    assert optimizer_rules.data_available_at == CUTOFF - timedelta(hours=12)

    with pytest.raises(ValueError, match="weekly free-transfer"):
        optimization_rules_from_snapshot(
            published,
            transfer_rules=transfer_rules(weekly_free_transfers=2),
            published_data_available_at=CUTOFF - timedelta(hours=12),
        )


def test_rules_require_two_starters_for_captain_and_vice() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 2"):
        rules(
            squad_size=1,
            lineup_size=1,
            positions=(
                PositionConstraint(
                    position_id=1,
                    squad_count=1,
                    lineup_minimum=1,
                    lineup_maximum=1,
                ),
            ),
        )


def test_result_contract_rejects_invalid_lineup_partition() -> None:
    request = compact_request((10.0, 1.0, 6.0))
    result = HighsOptimizer(time_limit_seconds=5.0).solve(request)
    invalid = result.model_dump()
    invalid["bench_element_ids"] = result.starter_element_ids

    with pytest.raises(ValidationError, match="partition"):
        OptimizationResult.model_validate(invalid)


@settings(max_examples=20, deadline=None)
@given(
    points=st.tuples(
        *(
            st.floats(
                min_value=0,
                max_value=12,
                allow_nan=False,
                allow_infinity=False,
                width=32,
            )
            for _ in range(6)
        )
    )
)
def test_highs_matches_exhaustive_oracle_across_generated_points(
    points: tuple[float, float, float, float, float, float],
) -> None:
    request = OptimizationRequest(
        event=6,
        prediction_cutoff=CUTOFF,
        players=tuple(
            player(
                element_id,
                team_id=(1, 2, 1, 2, 3, 3)[element_id - 1],
                position_id=1 if element_id in (1, 2, 5) else 2,
                points=points[element_id - 1],
            )
            for element_id in range(1, 7)
        ),
        current_squad=tuple(
            CurrentSquadPlayer(element_id=element_id, selling_price_tenths=50)
            for element_id in range(1, 5)
        ),
        bank_tenths=0,
        available_free_transfers=1,
        state_evidence=state_evidence(),
        rules=rules(),
    )

    result = HighsOptimizer(time_limit_seconds=5.0).solve(request)

    assert result.net_expected_points == pytest.approx(exhaustive_optimum(request), abs=1e-6)
    assert set(result.starter_element_ids) | set(result.bench_element_ids) == set(
        result.squad_element_ids
    )
    assert result.captain_element_id in result.starter_element_ids
    assert result.vice_captain_element_id in result.starter_element_ids
    assert len(result.transfers_in) == len(result.transfers_out)


def compact_request(points: tuple[float, float, float]) -> OptimizationRequest:
    return OptimizationRequest(
        event=6,
        prediction_cutoff=CUTOFF,
        players=(
            player(1, team_id=1, position_id=1, points=points[0]),
            player(2, team_id=2, position_id=1, points=points[1]),
            player(3, team_id=3, position_id=1, points=points[2]),
        ),
        current_squad=(
            CurrentSquadPlayer(element_id=1, selling_price_tenths=50),
            CurrentSquadPlayer(element_id=2, selling_price_tenths=50),
        ),
        bank_tenths=0,
        available_free_transfers=0,
        state_evidence=state_evidence(),
        rules=rules(
            squad_size=2,
            lineup_size=2,
            positions=(
                PositionConstraint(
                    position_id=1,
                    squad_count=2,
                    lineup_minimum=2,
                    lineup_maximum=2,
                ),
            ),
        ),
    )


def exhaustive_optimum(request: OptimizationRequest) -> float:
    players = {player.element_id: player for player in request.players}
    current = {player.element_id: player for player in request.current_squad}
    best = -inf
    for squad_ids in combinations(players, request.rules.squad_size):
        squad = tuple(players[element_id] for element_id in squad_ids)
        if any(
            sum(player.position_id == position.position_id for player in squad)
            != position.squad_count
            for position in request.rules.positions
        ):
            continue
        if any(
            sum(player.team_id == team_id for player in squad) > request.rules.club_limit
            for team_id in {player.team_id for player in squad}
        ):
            continue
        incoming = set(squad_ids) - set(current)
        outgoing = set(current) - set(squad_ids)
        spend = sum(players[element_id].buy_price_tenths for element_id in incoming)
        funds = request.bank_tenths + sum(
            current[element_id].selling_price_tenths for element_id in outgoing
        )
        if spend > funds:
            continue
        paid = max(0, len(incoming) - request.available_free_transfers)
        hit_cost = paid * request.rules.transfer_rules.transfer_cost_points
        for starter_ids in combinations(squad_ids, request.rules.lineup_size):
            starters = tuple(players[element_id] for element_id in starter_ids)
            if any(
                not position.lineup_minimum
                <= sum(player.position_id == position.position_id for player in starters)
                <= position.lineup_maximum
                for position in request.rules.positions
            ):
                continue
            starter_points = sum(player.expected_points for player in starters)
            for captain in starters:
                best = max(best, starter_points + captain.expected_points - hit_cost)
    return best
