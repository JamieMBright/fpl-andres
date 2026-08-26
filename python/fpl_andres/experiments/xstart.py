"""Paired GW2 xStart comparison outside the production model path."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.projector import ProjectionSettings, project_next_match
from fpl_andres.models.promotion import TripletPrediction

__all__ = ["ChronologicalAppearance", "Gw2XStartScore", "score_gw2_xstart"]


@dataclass(frozen=True)
class ChronologicalAppearance:
    source_season: str
    event: int
    fixture_id: int
    events_before_prediction: int
    started: bool

    def __post_init__(self) -> None:
        if not re.fullmatch(r"20\d{2}-\d{2}", self.source_season):
            raise ValueError(f"invalid source season: {self.source_season}")
        if self.event < 1 or self.events_before_prediction < 1:
            raise ValueError("appearance event and chronological distance must be positive")


@dataclass(frozen=True)
class Gw2XStartScore:
    season: str
    event: int
    element_ids: tuple[int, ...]
    element_codes: tuple[int, ...]
    triplets: tuple[TripletPrediction, ...]
    shipped_p60: tuple[float, ...]
    shipped_p60_brier: float
    baseline_brier: float
    candidate_brier: float


def _next_season(season: str) -> str:
    start, _, end = season.partition("-")
    if len(start) != 4 or len(end) != 2:
        raise ValueError(f"invalid season label: {season}")
    year = int(start)
    return f"{year + 1}-{str(year + 2)[-2:]}"


def _brier(rows: tuple[TripletPrediction, ...], *, candidate: bool) -> float:
    return sum(
        ((row.candidate if candidate else row.baseline) - row.observed) ** 2 for row in rows
    ) / len(rows)


def _appearance(
    row: ElementRow,
    *,
    source_season: str,
    events_before_prediction: int,
) -> ChronologicalAppearance:
    return ChronologicalAppearance(
        source_season=source_season,
        event=row.gameweek,
        fixture_id=row.fixture_id,
        events_before_prediction=events_before_prediction,
        started=(row.started or row.minutes >= 60) and row.minutes > 0,
    )


def _candidate_probability_start(
    current_rows: list[ElementRow],
    prior_rows: list[ElementRow],
    *,
    current_season: str,
    prior_season: str,
    half_life_events: float,
    prior_strength_events: float,
    prior_start_rate: float,
) -> float:
    if half_life_events <= 0 or prior_strength_events < 0:
        raise ValueError("candidate half-life must be positive and prior strength non-negative")
    if not 0 <= prior_start_rate <= 1:
        raise ValueError("candidate prior start rate must be a probability")
    if not current_rows or not prior_rows:
        raise ValueError("candidate requires both current and carried appearances")
    prior_last_event = max(row.gameweek for row in prior_rows)
    observations = [
        *(
            _appearance(
                row,
                source_season=current_season,
                events_before_prediction=2 - row.gameweek,
            )
            for row in current_rows
        ),
        *(
            _appearance(
                row,
                source_season=prior_season,
                events_before_prediction=prior_last_event - row.gameweek + 2,
            )
            for row in prior_rows
        ),
    ]
    keys = {(row.source_season, row.event, row.fixture_id) for row in observations}
    if len(keys) != len(observations):
        raise ValueError("candidate appearances repeat a source-season fixture")
    weights = [
        math.pow(0.5, row.events_before_prediction / half_life_events) for row in observations
    ]
    total_weight = sum(weights)
    squared_weight = sum(weight * weight for weight in weights)
    if total_weight <= 0 or squared_weight <= 0:
        raise ValueError("candidate recency weights vanished")
    weighted_start_rate = (
        sum(weight for row, weight in zip(observations, weights, strict=True) if row.started)
        / total_weight
    )
    effective_sample = total_weight * total_weight / squared_weight
    return (weighted_start_rate * effective_sample + prior_start_rate * prior_strength_events) / (
        effective_sample + prior_strength_events
    )


def score_gw2_xstart(
    previous: SeasonCorpus,
    current: SeasonCorpus,
    *,
    half_life_events: float,
    prior_strength_events: float,
    prior_start_rate: float = 0.35,
) -> Gw2XStartScore:
    if _next_season(previous.season) != current.season:
        raise ValueError(
            f"GW2 xStart comparison requires adjacent seasons, got "
            f"{previous.season} and {current.season}"
        )
    if 1 not in current.rows_by_gameweek or 2 not in current.rows_by_gameweek:
        raise ValueError("GW2 xStart comparison requires settled GW1 and GW2 rows")
    gw2_counts: dict[int, int] = {}
    for row in current.rows_by_gameweek[2]:
        gw2_counts[row.element_id] = gw2_counts.get(row.element_id, 0) + 1
    repeated = sorted(element_id for element_id, count in gw2_counts.items() if count > 1)
    if repeated:
        raise ValueError(
            f"GW2 xStart comparison requires one fixture per player; repeated {repeated}"
        )

    baseline_projections = project_next_match(previous, settings=ProjectionSettings())
    baseline_by_code = {
        projection.code: projection.minutes.probability_start for projection in baseline_projections
    }
    shipped_p60_by_code = {
        projection.code: projection.minutes.probability_sixty_minutes
        for projection in baseline_projections
    }
    prior_by_code = previous.rows_by_element_code()
    current_history = current.before(2)
    current_by_element: dict[int, list[ElementRow]] = {}
    for row in current_history:
        current_by_element.setdefault(row.element_id, []).append(row)

    rows: list[tuple[int, int, TripletPrediction, float]] = []
    for actual_row in current.rows_by_gameweek[2]:
        element_id = actual_row.element_id
        code = current.code_by_element.get(element_id)
        baseline = baseline_by_code.get(code) if code is not None else None
        shipped_reference = shipped_p60_by_code.get(code) if code is not None else None
        prior_rows = prior_by_code.get(code, ()) if code is not None else ()
        current_rows = current_by_element.get(element_id, ())
        if (
            code is None
            or baseline is None
            or shipped_reference is None
            or not prior_rows
            or not current_rows
        ):
            continue
        candidate = _candidate_probability_start(
            list(current_rows),
            list(prior_rows),
            current_season=current.season,
            prior_season=previous.season,
            half_life_events=half_life_events,
            prior_strength_events=prior_strength_events,
            prior_start_rate=prior_start_rate,
        )
        rows.append(
            (
                element_id,
                code,
                TripletPrediction(
                    baseline=baseline,
                    candidate=candidate,
                    observed=1.0 if actual_row.started else 0.0,
                ),
                shipped_reference,
            )
        )
    rows.sort(key=lambda row: row[0])
    if not rows:
        raise ValueError("no GW2 players have paired baseline and candidate xStart forecasts")
    element_ids = tuple(row[0] for row in rows)
    element_codes = tuple(row[1] for row in rows)
    triplets = tuple(row[2] for row in rows)
    shipped_values = tuple(row[3] for row in rows)
    observed_values = tuple(row.observed for row in triplets)
    return Gw2XStartScore(
        season=current.season,
        event=2,
        element_ids=element_ids,
        element_codes=element_codes,
        triplets=triplets,
        shipped_p60=shipped_values,
        shipped_p60_brier=sum(
            (forecast - actual) ** 2
            for forecast, actual in zip(shipped_values, observed_values, strict=True)
        )
        / len(shipped_values),
        baseline_brier=_brier(triplets, candidate=False),
        candidate_brier=_brier(triplets, candidate=True),
    )
