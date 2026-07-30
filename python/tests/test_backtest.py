from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.models.backtest import (
    BacktestLeakError,
    EventWindow,
    PlayerPrediction,
    run_backtest,
)

SEASON = "2024-25"
CUTOFF = datetime(2024, 8, 16, 17, 30, tzinfo=UTC)


def _window(event: int = 1) -> EventWindow:
    return EventWindow(
        season=SEASON,
        event=event,
        prediction_cutoff=CUTOFF + timedelta(days=7 * (event - 1)),
    )


def _prediction(
    element_code: int,
    predicted: float,
    *,
    position_code: str = "MID",
    evidence_level: str = "observed",
    available_at: datetime | None = None,
    window: EventWindow | None = None,
) -> PlayerPrediction:
    reference = window or _window()
    return PlayerPrediction(
        element_code=element_code,
        position_code=position_code,
        predicted_points=predicted,
        evidence_level=evidence_level,  # type: ignore[arg-type]
        data_available_at=available_at or reference.prediction_cutoff - timedelta(hours=1),
    )


def test_a_perfect_model_scores_zero_error_and_full_rank_correlation() -> None:
    windows = [_window()]
    truth = {code: float(code) for code in range(1, 12)}

    report = run_backtest(
        windows,
        predict=lambda w: [_prediction(code, float(code), window=w) for code in range(1, 12)],
        outcomes=lambda w: truth,
        top_n=3,
    )

    assert report.overall.mean_absolute_error == pytest.approx(0.0)
    assert report.overall.root_mean_squared_error == pytest.approx(0.0)
    assert report.overall.spearman == pytest.approx(1.0)
    assert report.overall.top_n_hit_rate == pytest.approx(1.0)
    assert report.predictions_scored == 11


def test_an_inverted_model_scores_negative_rank_correlation() -> None:
    windows = [_window()]
    truth = {code: float(code) for code in range(1, 12)}

    report = run_backtest(
        windows,
        predict=lambda w: [_prediction(code, float(12 - code), window=w) for code in range(1, 12)],
        outcomes=lambda w: truth,
        top_n=3,
    )

    assert report.overall.spearman == pytest.approx(-1.0)
    assert report.overall.top_n_hit_rate == pytest.approx(0.0)


def test_bias_separates_systematic_over_prediction_from_noise() -> None:
    windows = [_window()]
    truth = {code: 5.0 for code in range(1, 12)}

    optimistic = run_backtest(
        windows,
        predict=lambda w: [_prediction(code, 7.0, window=w) for code in range(1, 12)],
        outcomes=lambda w: truth,
    )

    assert optimistic.overall.bias == pytest.approx(2.0)
    assert optimistic.overall.mean_absolute_error == pytest.approx(2.0)


def test_a_prediction_using_post_cutoff_evidence_raises_rather_than_scoring() -> None:
    window = _window()

    with pytest.raises(BacktestLeakError, match="after the cutoff"):
        run_backtest(
            [window],
            predict=lambda w: [
                _prediction(
                    1,
                    9.0,
                    window=w,
                    available_at=w.prediction_cutoff + timedelta(seconds=1),
                )
            ],
            outcomes=lambda w: {1: 9.0},
        )


def test_evidence_available_exactly_at_the_cutoff_is_allowed() -> None:
    window = _window()

    report = run_backtest(
        [window],
        predict=lambda w: [_prediction(1, 9.0, window=w, available_at=w.prediction_cutoff)],
        outcomes=lambda w: {1: 9.0},
    )

    assert report.predictions_scored == 1


def test_unavailable_predictions_are_skipped_not_scored_as_zero() -> None:
    windows = [_window()]
    truth = {1: 8.0, 2: 6.0, 3: 2.0}

    report = run_backtest(
        windows,
        predict=lambda w: [
            _prediction(1, 7.5, window=w),
            _prediction(2, 5.5, window=w),
            _prediction(3, 0.0, window=w, evidence_level="unavailable"),
        ],
        outcomes=lambda w: truth,
    )

    # Scoring an unavailable projection as zero would punish honesty.
    assert report.predictions_scored == 2
    assert report.predictions_skipped_unavailable == 1


def test_a_player_without_a_realised_outcome_is_skipped() -> None:
    report = run_backtest(
        [_window()],
        predict=lambda w: [_prediction(1, 5.0, window=w), _prediction(99, 5.0, window=w)],
        outcomes=lambda w: {1: 4.0},
    )

    assert report.predictions_scored == 1
    assert report.predictions_skipped_unavailable == 1


def test_metrics_are_broken_down_by_position() -> None:
    truth = {1: 9.0, 2: 8.0, 3: 2.0, 4: 1.0}

    report = run_backtest(
        [_window()],
        predict=lambda w: [
            _prediction(1, 9.0, position_code="FWD", window=w),
            _prediction(2, 8.0, position_code="FWD", window=w),
            _prediction(3, 7.0, position_code="DEF", window=w),
            _prediction(4, 6.0, position_code="DEF", window=w),
        ],
        outcomes=lambda w: truth,
    )

    labels = {metrics.label: metrics for metrics in report.by_position}
    assert set(labels) == {"DEF", "FWD"}
    assert labels["FWD"].mean_absolute_error == pytest.approx(0.0)
    # Defenders were over-predicted by five points each.
    assert labels["DEF"].bias == pytest.approx(5.0)


def test_metrics_are_broken_down_by_evidence_level() -> None:
    truth = {1: 5.0, 2: 5.0, 3: 5.0, 4: 5.0}

    report = run_backtest(
        [_window()],
        predict=lambda w: [
            _prediction(1, 5.0, window=w),
            _prediction(2, 5.0, window=w),
            _prediction(3, 9.0, evidence_level="inferred", window=w),
            _prediction(4, 9.0, evidence_level="inferred", window=w),
        ],
        outcomes=lambda w: truth,
    )

    labels = {metrics.label: metrics for metrics in report.by_evidence_level}
    assert labels["observed"].mean_absolute_error == pytest.approx(0.0)
    # Carried-forward projections being worse is exactly what we want to detect.
    assert labels["inferred"].mean_absolute_error == pytest.approx(4.0)


def test_the_harness_walks_every_supplied_event() -> None:
    windows = [_window(event) for event in range(1, 6)]
    seen: list[int] = []

    def predict(window: EventWindow) -> Sequence[PlayerPrediction]:
        seen.append(window.event)
        return [_prediction(1, 5.0, window=window)]

    def outcomes(window: EventWindow) -> Mapping[int, float]:
        return {1: 5.0}

    report = run_backtest(windows, predict=predict, outcomes=outcomes)

    assert seen == [1, 2, 3, 4, 5]
    assert report.events_evaluated == 5
    assert report.predictions_scored == 5


def test_top_n_hit_rate_is_computed_per_event_not_across_the_pool() -> None:
    windows = [_window(1), _window(2)]

    # Event 1 ranked perfectly, event 2 ranked backwards.
    def predict(window: EventWindow) -> Sequence[PlayerPrediction]:
        if window.event == 1:
            return [_prediction(code, float(code), window=window) for code in range(1, 5)]
        return [_prediction(code, float(5 - code), window=window) for code in range(1, 5)]

    def outcomes(window: EventWindow) -> Mapping[int, float]:
        return {code: float(code) for code in range(1, 5)}

    report = run_backtest(windows, predict=predict, outcomes=outcomes, top_n=2)

    assert report.overall.top_n_hit_rate == pytest.approx(0.5)


def test_an_empty_backtest_reports_no_metrics_rather_than_zeroes() -> None:
    report = run_backtest([_window()], predict=lambda w: [], outcomes=lambda w: {})

    assert report.overall.count == 0
    assert report.overall.mean_absolute_error is None
    assert report.overall.spearman is None
    assert report.overall.top_n_hit_rate is None


def test_a_constant_prediction_column_reports_no_rank_correlation() -> None:
    truth = {code: float(code) for code in range(1, 6)}

    report = run_backtest(
        [_window()],
        predict=lambda w: [_prediction(code, 5.0, window=w) for code in range(1, 6)],
        outcomes=lambda w: truth,
    )

    # Every prediction tied, so there is no ranking to score.
    assert report.overall.spearman is None


def test_an_event_outside_the_season_is_rejected() -> None:
    with pytest.raises(ValueError, match="event must be between"):
        EventWindow(season=SEASON, event=39, prediction_cutoff=CUTOFF)


def test_a_naive_cutoff_is_rejected() -> None:
    with pytest.raises(ValueError, match="aware UTC"):
        EventWindow(season=SEASON, event=1, prediction_cutoff=datetime(2024, 8, 16, 17, 30))
