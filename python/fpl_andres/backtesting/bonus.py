"""Project BPS from sourced actions and each player's unexplained residual."""

from __future__ import annotations

import math
from collections.abc import Sequence

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.scoring import (
    CLEAN_SHEET_POINTS,
    OWN_GOAL_POINTS,
    PENALTY_MISS_POINTS,
    RED_CARD_POINTS,
    YELLOW_CARD_POINTS,
    PointsBreakdown,
)
from fpl_andres.models.market_evidence import (
    BpsInputs,
    BpsObservation,
    BpsProjection,
    project_bps_from_history,
)
from fpl_andres.models.minutes import MinutesProjection
from fpl_andres.models.player_rates import PlayerRateProjection

_MINUTES_PER_90 = 90.0


def observed_bps_inputs(row: ElementRow, *, position: int) -> BpsInputs:
    """Every official BPS action retained by the history corpus."""
    appeared = row.minutes > 0
    return BpsInputs(
        probability_appear=1.0 if appeared else 0.0,
        probability_sixty=1.0 if row.minutes >= 60 else 0.0,
        goals=float(row.goals),
        assists=float(row.assists),
        clean_sheets=float(row.clean_sheets),
        penalties_saved=float(row.penalties_saved),
        clearances_blocks_interceptions=_optional_float(row.clearances_blocks_interceptions),
        recoveries=_optional_float(row.recoveries),
        tackles=_optional_float(row.tackles),
        goals_conceded=float(row.goals_conceded) if position in (1, 2) else None,
        penalties_missed=float(row.penalties_missed),
        yellow_cards=float(row.yellow_cards),
        red_cards=float(row.red_cards),
        own_goals=float(row.own_goals),
    )


def project_player_bps(
    rows: Sequence[ElementRow],
    *,
    position: int,
    minutes: MinutesProjection,
    rates: PlayerRateProjection,
    breakdown: PointsBreakdown,
) -> BpsProjection | None:
    """Expected BPS for a neutral next match, with unavailable actions carried.

    Goals, assists, minutes, clean sheets, conceded goals, cards, penalty
    events and the complete CBIT/CBIRT family are projected explicitly. Opta
    inputs not retained by the corpus -- pass completion, errors, shot location
    and similar -- survive as the player's mean historical residual rather than
    being silently set to zero.
    """
    appearances = [row for row in rows if row.minutes > 0]
    if not appearances:
        return None
    observations = [
        BpsObservation(
            inputs=observed_bps_inputs(row, position=position),
            observed_bps=float(row.bps),
        )
        for row in appearances
    ]
    ninety = minutes.expected_minutes / _MINUTES_PER_90
    clean_sheet_points = CLEAN_SHEET_POINTS.get(position, 0)
    clean_sheets = (
        max(0.0, breakdown.clean_sheet / clean_sheet_points) if clean_sheet_points else None
    )
    goals_conceded = _expected_goals_conceded(
        clean_sheets,
        minutes.probability_sixty_minutes,
        position,
    )
    projected = BpsInputs(
        probability_appear=minutes.probability_appear,
        probability_sixty=minutes.probability_sixty_minutes,
        goals=ninety * rates.goals_per_90,
        assists=ninety * rates.assists_per_90,
        clean_sheets=clean_sheets,
        penalties_saved=_component_rate(
            appearances,
            "penalties_saved",
            minutes.expected_minutes,
        ),
        clearances_blocks_interceptions=_component_rate(
            appearances,
            "clearances_blocks_interceptions",
            minutes.expected_minutes,
        ),
        recoveries=_component_rate(
            appearances,
            "recoveries",
            minutes.expected_minutes,
        ),
        tackles=_component_rate(
            appearances,
            "tackles",
            minutes.expected_minutes,
        ),
        goals_conceded=goals_conceded,
        penalties_missed=_points_to_events(
            breakdown.penalties_missed,
            PENALTY_MISS_POINTS,
        ),
        yellow_cards=_points_to_events(
            breakdown.yellow_cards,
            YELLOW_CARD_POINTS,
        ),
        red_cards=_points_to_events(breakdown.red_cards, RED_CARD_POINTS),
        own_goals=_points_to_events(breakdown.own_goals, OWN_GOAL_POINTS),
    )
    return project_bps_from_history(observations, projected, position=position)


def _component_rate(
    rows: Sequence[ElementRow],
    field: str,
    expected_minutes: float,
) -> float | None:
    values = [getattr(row, field) for row in rows]
    if any(value is None for value in values):
        return None
    played = sum(row.minutes for row in rows)
    if played <= 0:
        return None
    return sum(float(value) for value in values) * expected_minutes / played


def _expected_goals_conceded(
    clean_sheets: float | None,
    probability_sixty: float,
    position: int,
) -> float | None:
    if position not in (1, 2) or clean_sheets is None or probability_sixty <= 0.0:
        return None
    conditional_sheet = min(1.0, max(1e-4, clean_sheets / probability_sixty))
    return probability_sixty * -math.log(conditional_sheet)


def _points_to_events(points: float, points_per_event: int) -> float:
    if points_per_event == 0:
        raise ValueError("points_per_event cannot be zero")
    return max(0.0, points / points_per_event)


def _optional_float(value: int | None) -> float | None:
    return float(value) if value is not None else None


__all__ = ["observed_bps_inputs", "project_player_bps"]
