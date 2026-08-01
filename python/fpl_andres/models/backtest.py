"""Walk-forward backtesting for player-level projections.

The leak guard is structural rather than advisory: the harness hands a
prediction function nothing but the event and its cutoff, then rejects any
returned prediction whose evidence postdates that cutoff. A model cannot see
the future by construction, and an attempt to raises rather than quietly
inflating the score.

Metrics are reported per position as well as overall, because a model that
ranks forwards well and defenders badly is not a model that ranks well.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.stats import spearmanr

from fpl_andres.models.contracts import EvidenceLevel


class BacktestLeakError(RuntimeError):
    """Raised when a prediction depends on evidence from after its cutoff."""


@dataclass(frozen=True)
class EventWindow:
    """One event and the moment a decision for it had to be made."""

    season: str
    event: int
    prediction_cutoff: datetime

    def __post_init__(self) -> None:
        if self.prediction_cutoff.tzinfo is None or self.prediction_cutoff.utcoffset() != timedelta(
            0
        ):
            raise ValueError("prediction_cutoff must be an aware UTC timestamp")
        if not 1 <= self.event <= 38:
            raise ValueError("event must be between 1 and 38")


class PlayerPrediction(BaseModel):
    """What the model said, and when it could have said it."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    element_code: Annotated[int, Field(gt=0)]
    position_code: str
    predicted_points: float
    evidence_level: EvidenceLevel
    data_available_at: datetime

    @model_validator(mode="after")
    def validate_prediction(self) -> PlayerPrediction:
        if self.data_available_at.tzinfo is None or self.data_available_at.utcoffset() != timedelta(
            0
        ):
            raise ValueError("data_available_at must be an aware UTC timestamp")
        return self


class PredictionOutcome(BaseModel):
    """One scored prediction against its realised outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    season: str
    event: Annotated[int, Field(ge=1, le=38)]
    element_code: Annotated[int, Field(gt=0)]
    position_code: str
    predicted_points: float
    actual_points: float
    evidence_level: EvidenceLevel

    @property
    def error(self) -> float:
        return self.predicted_points - self.actual_points


class BacktestMetrics(BaseModel):
    """Scoring for one slice of predictions."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    label: str
    count: int
    mean_absolute_error: float | None
    root_mean_squared_error: float | None
    bias: float | None
    spearman: float | None
    top_n: int
    top_n_hit_rate: float | None
    # An event with fewer than top_n scored players cannot produce a top-N, so it
    # is skipped. Reported rather than silent: a rate averaged over the full
    # gameweeks only is a different measurement from one over all of them, and
    # nothing downstream could previously tell which it had been given.
    top_n_events_scored: int = 0
    top_n_events_skipped: int = 0


class BacktestReport(BaseModel):
    """Full backtest outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    overall: BacktestMetrics
    by_position: tuple[BacktestMetrics, ...]
    by_evidence_level: tuple[BacktestMetrics, ...]
    events_evaluated: int
    predictions_scored: int
    predictions_skipped_unavailable: int


PredictFn = Callable[[EventWindow], Sequence[PlayerPrediction]]
OutcomeFn = Callable[[EventWindow], Mapping[int, float]]


def run_backtest(
    windows: Sequence[EventWindow],
    *,
    predict: PredictFn,
    outcomes: OutcomeFn,
    top_n: int = 10,
    score_unavailable: bool = False,
) -> BacktestReport:
    """Walk each event, predict from pre-cutoff evidence only, then reveal."""
    scored: list[PredictionOutcome] = []
    skipped = 0

    for window in windows:
        predictions = predict(window)
        realised = outcomes(window)

        for prediction in predictions:
            if prediction.data_available_at > window.prediction_cutoff:
                raise BacktestLeakError(
                    f"{window.season} event {window.event}: prediction for element "
                    f"{prediction.element_code} used evidence available at "
                    f"{prediction.data_available_at.isoformat()}, after the cutoff "
                    f"{window.prediction_cutoff.isoformat()}"
                )
            if prediction.evidence_level == "unavailable" and not score_unavailable:
                skipped += 1
                continue
            actual = realised.get(prediction.element_code)
            if actual is None:
                skipped += 1
                continue
            scored.append(
                PredictionOutcome(
                    season=window.season,
                    event=window.event,
                    element_code=prediction.element_code,
                    position_code=prediction.position_code,
                    predicted_points=prediction.predicted_points,
                    actual_points=actual,
                    evidence_level=prediction.evidence_level,
                )
            )

    positions = sorted({outcome.position_code for outcome in scored})
    levels = sorted({outcome.evidence_level for outcome in scored})

    return BacktestReport(
        overall=_metrics("overall", scored, top_n),
        by_position=tuple(
            _metrics(
                position,
                [outcome for outcome in scored if outcome.position_code == position],
                top_n,
            )
            for position in positions
        ),
        by_evidence_level=tuple(
            _metrics(
                level,
                [outcome for outcome in scored if outcome.evidence_level == level],
                top_n,
            )
            for level in levels
        ),
        events_evaluated=len(windows),
        predictions_scored=len(scored),
        predictions_skipped_unavailable=skipped,
    )


def _metrics(label: str, outcomes: Sequence[PredictionOutcome], top_n: int) -> BacktestMetrics:
    count = len(outcomes)
    if count == 0:
        return BacktestMetrics(
            label=label,
            count=0,
            mean_absolute_error=None,
            root_mean_squared_error=None,
            bias=None,
            spearman=None,
            top_n=top_n,
            top_n_hit_rate=None,
        )

    errors = [outcome.error for outcome in outcomes]
    mae = sum(abs(error) for error in errors) / count
    rmse = (sum(error * error for error in errors) / count) ** 0.5
    bias = sum(errors) / count
    hit_rate, scored_events, skipped_events = _top_n_hit_rate(outcomes, top_n)

    return BacktestMetrics(
        label=label,
        count=count,
        mean_absolute_error=mae,
        root_mean_squared_error=rmse,
        bias=bias,
        spearman=_spearman(outcomes),
        top_n=top_n,
        top_n_hit_rate=hit_rate,
        top_n_events_scored=scored_events,
        top_n_events_skipped=skipped_events,
    )


def _spearman(outcomes: Sequence[PredictionOutcome]) -> float | None:
    """Rank correlation, or None when the sample cannot support one."""
    if len(outcomes) < 3:
        return None
    predicted = [outcome.predicted_points for outcome in outcomes]
    actual = [outcome.actual_points for outcome in outcomes]
    # A constant column has no ranks to correlate.
    if len(set(predicted)) < 2 or len(set(actual)) < 2:
        return None
    correlation = float(spearmanr(predicted, actual).statistic)
    if correlation != correlation:  # NaN
        return None
    return correlation


def _top_n_hit_rate(
    outcomes: Sequence[PredictionOutcome], top_n: int
) -> tuple[float | None, int, int]:
    """Share of the top-N predicted that landed in the top-N actual.

    Computed per event, because ranking players across different gameweeks is
    not a question anyone asks. Returns the rate with the number of events that
    could and could not supply one, so the caller can see the coverage behind
    the number rather than inferring it.
    """
    if top_n <= 0:
        return None, 0, 0
    by_event: dict[tuple[str, int], list[PredictionOutcome]] = {}
    for outcome in outcomes:
        by_event.setdefault((outcome.season, outcome.event), []).append(outcome)

    rates: list[float] = []
    skipped = 0
    for event_outcomes in by_event.values():
        if len(event_outcomes) < top_n:
            skipped += 1
            continue
        predicted_top = {
            outcome.element_code
            for outcome in sorted(event_outcomes, key=lambda o: o.predicted_points, reverse=True)[
                :top_n
            ]
        }
        actual_top = {
            outcome.element_code
            for outcome in sorted(event_outcomes, key=lambda o: o.actual_points, reverse=True)[
                :top_n
            ]
        }
        rates.append(len(predicted_top & actual_top) / top_n)

    if not rates:
        return None, 0, skipped
    return sum(rates) / len(rates), len(rates), skipped


__all__ = [
    "BacktestLeakError",
    "BacktestMetrics",
    "BacktestReport",
    "EventWindow",
    "PlayerPrediction",
    "PredictionOutcome",
    "run_backtest",
]
