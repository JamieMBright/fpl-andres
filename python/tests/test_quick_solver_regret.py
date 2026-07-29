import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from fpl_andres.optimization.contracts import (
    CurrentSquadPlayer,
    OptimizationPlayer,
    OptimizationRequest,
    OptimizationRules,
    OptimizationStateEvidence,
    PositionConstraint,
    TransferRulesAddendum,
)
from fpl_andres.optimization.highs import HighsOptimizer

CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "quick-solver"
    / "fixtures"
    / "regret-cases.json"
)
FULL_SQUAD_CASE_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "quick-solver"
    / "fixtures"
    / "full-squad-regret-case.json"
)


def regret_cases() -> list[dict[str, Any]]:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    full = json.loads(FULL_SQUAD_CASE_PATH.read_text(encoding="utf-8"))
    full_input = {
        "season": full["season"],
        "event": full["event"],
        "predictionCutoff": full["predictionCutoff"],
        "players": [
            {
                "elementId": element_id,
                "teamId": team_id,
                "positionId": position_id,
                "buyPriceTenths": full["buyPriceTenths"],
                "expectedPoints": expected_points,
                "evidenceLevel": full["evidenceLevel"],
                "dataAvailableAt": full["dataAvailableAt"],
                "sourceHashes": [f"sha256:{element_id:064x}"],
            }
            for element_id, team_id, position_id, expected_points in full["playerRows"]
        ],
        "currentSquad": [
            {
                "elementId": element_id,
                "sellingPriceTenths": full["sellingPriceTenths"],
            }
            for element_id in full["currentElementIds"]
        ],
        "bankTenths": full["bankTenths"],
        "availableFreeTransfers": full["availableFreeTransfers"],
        "stateEvidence": full["stateEvidence"],
        "rules": full["rules"],
    }
    cases.append(
        {
            "name": full["name"],
            "input": full_input,
            "highsOptimalNetPoints": full["highsOptimalNetPoints"],
            "maxAllowedRegret": full["maxAllowedRegret"],
        }
    )
    return cases


@pytest.mark.parametrize("case", regret_cases(), ids=lambda case: str(case["name"]))
def test_stored_quick_solver_reference_is_highs_optimum(case: dict[str, Any]) -> None:
    input_value = case["input"]
    rule_value = input_value["rules"]
    state_value = input_value["stateEvidence"]
    transfer_rules = TransferRulesAddendum.model_validate(
        {
            "season": input_value["season"],
            "weekly_free_transfers": rule_value["weeklyFreeTransfers"],
            "maximum_free_transfers": rule_value["maximumFreeTransfers"],
            "transfer_cost_points": rule_value["transferCostPoints"],
            "source_reference": rule_value["transferRulesSourceReference"],
            "source_hash": rule_value["transferRulesHash"],
            "data_available_at": parse_timestamp(rule_value["dataAvailableAt"]),
        }
    )
    rules = OptimizationRules.model_validate(
        {
            "season": input_value["season"],
            "squad_size": rule_value["squadSize"],
            "lineup_size": rule_value["lineupSize"],
            "club_limit": rule_value["clubLimit"],
            "transfer_cap": rule_value["transferCap"],
            "positions": tuple(
                PositionConstraint(
                    position_id=position["positionId"],
                    squad_count=position["squadCount"],
                    lineup_minimum=position["lineupMinimum"],
                    lineup_maximum=position["lineupMaximum"],
                )
                for position in rule_value["positions"]
            ),
            "transfer_rules": transfer_rules,
            "published_rules_hash": rule_value["publishedRulesHash"],
            "data_available_at": parse_timestamp(rule_value["dataAvailableAt"]),
        }
    )
    players = tuple(
        OptimizationPlayer.model_validate(
            {
                "season": input_value["season"],
                "event": input_value["event"],
                "element_id": player["elementId"],
                "team_id": player["teamId"],
                "position_id": player["positionId"],
                "buy_price_tenths": player["buyPriceTenths"],
                "expected_points": player["expectedPoints"],
                "evidence_level": player["evidenceLevel"],
                "model_name": "quick-solver-regret-fixture",
                "model_version": "1",
                "data_available_at": parse_timestamp(player["dataAvailableAt"]),
                "source_hashes": tuple(player["sourceHashes"]),
            }
        )
        for player in input_value["players"]
    )
    request = OptimizationRequest.model_validate(
        {
            "event": input_value["event"],
            "prediction_cutoff": parse_timestamp(input_value["predictionCutoff"]),
            "players": players,
            "current_squad": tuple(
                CurrentSquadPlayer(
                    element_id=player["elementId"],
                    selling_price_tenths=player["sellingPriceTenths"],
                )
                for player in input_value["currentSquad"]
            ),
            "bank_tenths": input_value["bankTenths"],
            "available_free_transfers": input_value["availableFreeTransfers"],
            "state_evidence": OptimizationStateEvidence(
                public_state_as_of=parse_timestamp(state_value["publicStateAsOf"]),
                public_data_available_at=parse_timestamp(state_value["publicDataAvailableAt"]),
                overrides_updated_at=parse_timestamp(state_value["overridesUpdatedAt"]),
                public_source_hashes=tuple(state_value["publicSourceHashes"]),
                manager_overrides_hash=state_value["managerOverridesHash"],
            ),
            "rules": rules,
        }
    )

    result = HighsOptimizer(time_limit_seconds=5.0).solve(request)

    assert result.net_expected_points == pytest.approx(case["highsOptimalNetPoints"])


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
