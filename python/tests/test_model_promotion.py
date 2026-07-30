from typing import cast

import pytest

from fpl_andres.models.metrics import mean_absolute_error
from fpl_andres.models.promotion import (
    MetricDirection,
    TripletPrediction,
    evaluate_promotion,
)


def test_equal_model_never_promotes() -> None:
    triplets = (
        TripletPrediction(baseline=1.0, candidate=1.0, observed=0.0),
        TripletPrediction(baseline=1.0, candidate=1.0, observed=2.0),
        TripletPrediction(baseline=1.0, candidate=1.0, observed=1.0),
    )

    decision = evaluate_promotion(
        triplets,
        metric_name="mae",
        metric=mean_absolute_error,
        metric_direction="lower_is_better",
        resamples=200,
        seed=17,
        confidence=0.95,
        minimum_sample_size=1,
    )

    assert decision.baseline.point_estimate == pytest.approx(2 / 3)
    assert decision.candidate.point_estimate == pytest.approx(2 / 3)
    assert decision.paired_improvement.point_estimate == 0.0
    assert decision.paired_improvement.lower == 0.0
    assert decision.paired_improvement.upper == 0.0
    assert not decision.promoted
    assert decision.reason_codes == ("no_improvement",)


def test_sample_floor_blocks_apparent_improvement_without_bootstrap_claim() -> None:
    decision = evaluate_promotion(
        (TripletPrediction(baseline=2.0, candidate=1.0, observed=1.0),),
        metric_name="mae",
        metric=mean_absolute_error,
        metric_direction="lower_is_better",
        resamples=200,
        seed=17,
        confidence=0.95,
        minimum_sample_size=30,
    )

    assert not decision.promoted
    assert decision.reason_codes == ("insufficient_sample",)
    assert decision.candidate.sample_size == 1
    assert decision.candidate.lower == decision.candidate.upper


def test_paired_improvement_promotes_only_when_lower_bound_is_positive() -> None:
    triplets = tuple(
        TripletPrediction(baseline=2.0, candidate=1.0, observed=1.0) for _ in range(50)
    )

    decision = evaluate_promotion(
        triplets,
        metric_name="mae",
        metric=mean_absolute_error,
        metric_direction="lower_is_better",
        resamples=500,
        seed=17,
        confidence=0.95,
        minimum_sample_size=30,
    )

    assert decision.baseline.point_estimate == 1.0
    assert decision.candidate.point_estimate == 0.0
    assert decision.paired_improvement.lower == 1.0
    assert decision.promoted
    assert decision.reason_codes == ("beat_baseline",)


def test_uncertain_paired_improvement_does_not_promote() -> None:
    triplets = (
        TripletPrediction(baseline=1.0, candidate=0.0, observed=0.0),
        TripletPrediction(baseline=1.0, candidate=0.0, observed=0.0),
        TripletPrediction(baseline=1.0, candidate=0.0, observed=0.0),
        TripletPrediction(baseline=0.0, candidate=2.0, observed=0.0),
    )

    decision = evaluate_promotion(
        triplets,
        metric_name="mae",
        metric=mean_absolute_error,
        metric_direction="lower_is_better",
        resamples=500,
        seed=17,
        confidence=0.95,
        minimum_sample_size=1,
    )

    assert decision.paired_improvement.point_estimate == 0.25
    assert decision.paired_improvement.lower < 0 < decision.paired_improvement.upper
    assert not decision.promoted
    assert decision.reason_codes == ("ci_includes_zero",)


@pytest.mark.parametrize(
    ("resamples", "minimum_sample_size"),
    ((cast(int, 1.5), 1), (100, cast(int, 1.5))),
)
def test_promotion_rejects_fractional_integer_parameters(
    resamples: int,
    minimum_sample_size: int,
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        evaluate_promotion(
            (TripletPrediction(baseline=1.0, candidate=0.0, observed=0.0),),
            metric_name="mae",
            metric=mean_absolute_error,
            metric_direction="lower_is_better",
            resamples=resamples,
            seed=17,
            confidence=0.95,
            minimum_sample_size=minimum_sample_size,
        )


def test_metric_rejects_empty_or_misaligned_inputs() -> None:
    with pytest.raises(ValueError, match="at least one"):
        mean_absolute_error((), ())
    with pytest.raises(ValueError, match="same length"):
        mean_absolute_error((1.0,), (1.0, 2.0))


def _mean_error_signed(
    predicted: "list[float] | tuple[float, ...]",
    observed: "list[float] | tuple[float, ...]",
) -> float:
    # Deliberately higher-is-better sentinel: returns raw signed mean so
    # a candidate that scores strictly higher than baseline should be promoted.
    if not predicted:
        raise ValueError("metric requires at least one observation")
    if len(predicted) != len(observed):
        raise ValueError("predicted and observed values must have the same length")
    return sum(predicted) / len(predicted) - sum(observed) / len(observed)


def test_higher_is_better_metric_promotes_when_candidate_scores_higher() -> None:
    triplets = tuple(
        TripletPrediction(baseline=1.0, candidate=2.0, observed=1.0) for _ in range(50)
    )

    decision = evaluate_promotion(
        triplets,
        metric_name="signed_mean",
        metric=_mean_error_signed,
        metric_direction="higher_is_better",
        resamples=500,
        seed=17,
        confidence=0.95,
        minimum_sample_size=30,
    )

    assert decision.paired_improvement.point_estimate == pytest.approx(1.0)
    assert decision.paired_improvement.lower > 0
    assert decision.promoted
    assert decision.reason_codes == ("beat_baseline",)


def test_promotion_rejects_invalid_metric_direction() -> None:
    with pytest.raises(ValueError, match="metric_direction"):
        evaluate_promotion(
            (TripletPrediction(baseline=1.0, candidate=0.0, observed=0.0),),
            metric_name="mae",
            metric=mean_absolute_error,
            metric_direction=cast("MetricDirection", "backwards"),
            resamples=200,
            seed=17,
            confidence=0.95,
            minimum_sample_size=1,
        )
