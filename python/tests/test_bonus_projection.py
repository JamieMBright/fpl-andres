"""Expected BPS from sourced actions plus each player's historical residual."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fpl_andres.backtesting.bonus import observed_bps_inputs, project_player_bps
from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.scoring import PointsBreakdown
from fpl_andres.models.market_evidence import expected_bps
from fpl_andres.models.minutes import MinutesProjection
from fpl_andres.models.player_rates import PlayerRateProjection

AT = datetime(2026, 5, 24, 15, 0, tzinfo=UTC)
HASH = "sha256:" + "b" * 64


def _row(**overrides: object) -> ElementRow:
    values: dict[str, object] = {
        "gameweek": 38,
        "element_id": 1,
        "element_code": 101,
        "fixture_id": 3801,
        "minutes": 90,
        "started": True,
        "goals": 0,
        "assists": 0,
        "expected_goals": 0.1,
        "expected_assists": 0.1,
        "total_points": 4,
        "price_tenths": 50,
        "selected": 100,
        "kickoff_time": AT,
        "bps": 20,
        "clean_sheets": 1,
        "goals_conceded": 0,
        "clearances_blocks_interceptions": 4,
        "tackles": 2,
        "recoveries": 6,
    }
    values.update(overrides)
    return ElementRow(**values)  # type: ignore[arg-type]


def _minutes() -> MinutesProjection:
    return MinutesProjection(
        element_code=101,
        season="2025-26",
        event=38,
        probability_start=0.8,
        probability_appear=0.9,
        probability_sixty_minutes=0.75,
        expected_minutes=72.0,
        evidence_level="inferred",
        reason_codes=("test",),
        data_available_at=AT,
        source_hashes=(HASH,),
    )


def _rates(goals: float) -> PlayerRateProjection:
    return PlayerRateProjection(
        element_code=101,
        season="2025-26",
        event=38,
        goals_per_90=goals,
        assists_per_90=0.1,
        current_season_minutes=900.0,
        carried_season=None,
        carried_weight=0.0,
        evidence_level="inferred",
        reason_codes=("test",),
        data_available_at=AT,
        source_hashes=(HASH,),
    )


def _breakdown() -> PointsBreakdown:
    return PointsBreakdown(
        appearance=1.65,
        attacking=0.3,
        clean_sheet=2.4,
        bonus=0.5,
        saves=0.0,
        conceding=-0.1,
        yellow_cards=-0.1,
        red_cards=-0.01,
        own_goals=-0.01,
        penalties_missed=-0.01,
        defensive_contribution=0.8,
    )


def test_an_observed_row_reconstructs_every_available_defensive_action() -> None:
    inputs = observed_bps_inputs(_row(yellow_cards=1), position=2)
    estimate = expected_bps(inputs, position=2)

    assert inputs.clearances_blocks_interceptions == 4.0
    assert inputs.tackles == 2.0
    assert inputs.recoveries == 6.0
    assert inputs.yellow_cards == 1.0
    assert "saves_inside_box" in estimate.missing


def test_more_projected_goals_raise_expected_bps_by_the_official_weight() -> None:
    low = project_player_bps(
        [_row()],
        position=2,
        minutes=_minutes(),
        rates=_rates(0.0),
        breakdown=_breakdown(),
    )
    high = project_player_bps(
        [_row()],
        position=2,
        minutes=_minutes(),
        rates=_rates(0.5),
        breakdown=_breakdown(),
    )

    assert low is not None and high is not None
    assert high.expected_bps - low.expected_bps == pytest.approx(0.4 * 12.0)


def test_no_appearances_produce_no_bps_claim() -> None:
    assert (
        project_player_bps(
            [_row(minutes=0, started=False, bps=0)],
            position=2,
            minutes=_minutes(),
            rates=_rates(0.2),
            breakdown=_breakdown(),
        )
        is None
    )
