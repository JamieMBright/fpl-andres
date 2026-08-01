from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

Metric = Callable[[Sequence[float], Sequence[float]], float]
MetricDirection = Literal["lower_is_better", "higher_is_better"]


@dataclass(frozen=True)
class TripletPrediction:
    baseline: float
    candidate: float
    observed: float

    def __post_init__(self) -> None:
        for label, value in (
            ("baseline", self.baseline),
            ("candidate", self.candidate),
            ("observed", self.observed),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{label} must be finite and non-negative")


@dataclass(frozen=True)
class BootstrapResult:
    metric_name: str
    point_estimate: float
    lower: float
    upper: float
    confidence: float
    resamples: int
    seed: int
    sample_size: int


@dataclass(frozen=True)
class PromotionDecision:
    baseline: BootstrapResult
    candidate: BootstrapResult
    paired_improvement: BootstrapResult
    minimum_sample_size: int
    promoted: bool
    reason_codes: tuple[str, ...]
    # How many independently-seeded bootstraps were run, and how many of them
    # promoted. A split vote means the evidence is too marginal to act on, not
    # that the majority is right.
    seed_replicates: int = 1
    seeds_promoting: int = 0


def evaluate_promotion(
    triplets: Sequence[TripletPrediction],
    *,
    metric_name: str,
    metric: Metric,
    metric_direction: MetricDirection,
    resamples: int,
    seed: int,
    confidence: float,
    minimum_sample_size: int,
    seed_replicates: int = 1,
) -> PromotionDecision:
    _validate_parameters(
        triplets,
        metric_name=metric_name,
        metric_direction=metric_direction,
        resamples=resamples,
        seed=seed,
        confidence=confidence,
        minimum_sample_size=minimum_sample_size,
        seed_replicates=seed_replicates,
    )
    baseline_values = tuple(row.baseline for row in triplets)
    candidate_values = tuple(row.candidate for row in triplets)
    observed_values = tuple(row.observed for row in triplets)
    baseline_point = metric(baseline_values, observed_values)
    candidate_point = metric(candidate_values, observed_values)
    improvement_point = _improvement(baseline_point, candidate_point, metric_direction)
    sample_size = len(triplets)

    if sample_size < minimum_sample_size:
        return PromotionDecision(
            baseline=_degenerate_result(metric_name, baseline_point, confidence, seed, sample_size),
            candidate=_degenerate_result(
                metric_name, candidate_point, confidence, seed, sample_size
            ),
            paired_improvement=_degenerate_result(
                f"paired_{metric_name}_improvement",
                improvement_point,
                confidence,
                seed,
                sample_size,
            ),
            minimum_sample_size=minimum_sample_size,
            promoted=False,
            reason_codes=("insufficient_sample",),
        )

    rng = random.Random(seed)
    baseline_samples: list[float] = []
    candidate_samples: list[float] = []
    improvement_samples: list[float] = []
    for _ in range(resamples):
        indices = tuple(rng.randrange(sample_size) for _ in range(sample_size))
        sampled_observed = tuple(observed_values[index] for index in indices)
        sampled_baseline = tuple(baseline_values[index] for index in indices)
        sampled_candidate = tuple(candidate_values[index] for index in indices)
        baseline_metric = metric(sampled_baseline, sampled_observed)
        candidate_metric = metric(sampled_candidate, sampled_observed)
        baseline_samples.append(baseline_metric)
        candidate_samples.append(candidate_metric)
        improvement_samples.append(
            _improvement(baseline_metric, candidate_metric, metric_direction)
        )

    baseline_result = _bootstrap_result(
        metric_name,
        baseline_point,
        baseline_samples,
        confidence,
        resamples,
        seed,
        sample_size,
    )
    candidate_result = _bootstrap_result(
        metric_name,
        candidate_point,
        candidate_samples,
        confidence,
        resamples,
        seed,
        sample_size,
    )
    improvement_result = _bootstrap_result(
        f"paired_{metric_name}_improvement",
        improvement_point,
        improvement_samples,
        confidence,
        resamples,
        seed,
        sample_size,
    )
    promoted = improvement_result.lower > 0
    if promoted:
        reasons = ("beat_baseline",)
    elif improvement_point <= 0:
        reasons = ("no_improvement",)
    else:
        reasons = ("ci_includes_zero",)

    # Replicate the bootstrap under further seeds and require unanimity. A
    # 2,000-resample interval carries enough Monte Carlo error that a marginal
    # candidate promotes on some seeds and not others: measured at 3 of 40 for a
    # 60-row sample with a small true edge. Promoting on the strength of which
    # seed was passed in is not a decision about the model.
    promoting = 1 if promoted else 0
    for offset in range(1, seed_replicates):
        replicate = _improvement_interval(
            triplets,
            metric=metric,
            metric_direction=metric_direction,
            resamples=resamples,
            seed=seed + offset,
            confidence=confidence,
        )
        if replicate > 0:
            promoting += 1
    if promoting != seed_replicates and promoted:
        promoted = False
        reasons = ("seed_disagreement",)

    return PromotionDecision(
        baseline=baseline_result,
        candidate=candidate_result,
        paired_improvement=improvement_result,
        minimum_sample_size=minimum_sample_size,
        promoted=promoted,
        reason_codes=reasons,
        seed_replicates=seed_replicates,
        seeds_promoting=promoting,
    )


def _improvement_interval(
    triplets: Sequence[TripletPrediction],
    *,
    metric: Metric,
    metric_direction: MetricDirection,
    resamples: int,
    seed: int,
    confidence: float,
) -> float:
    """Lower bound of the paired improvement interval under one seed."""
    baseline_values = tuple(row.baseline for row in triplets)
    candidate_values = tuple(row.candidate for row in triplets)
    observed_values = tuple(row.observed for row in triplets)
    sample_size = len(triplets)
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(resamples):
        indices = tuple(rng.randrange(sample_size) for _ in range(sample_size))
        sampled_observed = tuple(observed_values[index] for index in indices)
        samples.append(
            _improvement(
                metric(tuple(baseline_values[i] for i in indices), sampled_observed),
                metric(tuple(candidate_values[i] for i in indices), sampled_observed),
                metric_direction,
            )
        )
    return _quantile(sorted(samples), (1.0 - confidence) / 2.0)


def _validate_parameters(
    triplets: Sequence[TripletPrediction],
    *,
    metric_name: str,
    metric_direction: MetricDirection,
    resamples: int,
    seed: int,
    confidence: float,
    minimum_sample_size: int,
    seed_replicates: int = 1,
) -> None:
    if not triplets:
        raise ValueError("promotion evaluation requires at least one prediction")
    if not metric_name:
        raise ValueError("metric_name must be non-empty")
    if metric_direction not in ("lower_is_better", "higher_is_better"):
        raise ValueError("metric_direction must be 'lower_is_better' or 'higher_is_better'")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 1:
        raise ValueError("resamples must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    if (
        isinstance(minimum_sample_size, bool)
        or not isinstance(minimum_sample_size, int)
        or minimum_sample_size < 1
    ):
        raise ValueError("minimum_sample_size must be a positive integer")
    if (
        isinstance(seed_replicates, bool)
        or not isinstance(seed_replicates, int)
        or seed_replicates < 1
    ):
        raise ValueError("seed_replicates must be a positive integer")


def _improvement(baseline: float, candidate: float, direction: MetricDirection) -> float:
    return baseline - candidate if direction == "lower_is_better" else candidate - baseline


def _bootstrap_result(
    metric_name: str,
    point_estimate: float,
    samples: list[float],
    confidence: float,
    resamples: int,
    seed: int,
    sample_size: int,
) -> BootstrapResult:
    ordered = sorted(samples)
    tail = (1 - confidence) / 2
    return BootstrapResult(
        metric_name=metric_name,
        point_estimate=point_estimate,
        lower=_quantile(ordered, tail),
        upper=_quantile(ordered, 1 - tail),
        confidence=confidence,
        resamples=resamples,
        seed=seed,
        sample_size=sample_size,
    )


def _quantile(ordered: list[float], fraction: float) -> float:
    """Linear interpolation between order statistics.

    The previous `ceil(f * n) - 1` indexing snapped to a whole resample, which
    biases the bound inward and does so hardest when there are fewest resamples
    - exactly the runs where the interval is doing the most work. At 200
    resamples the 97.5th percentile landed on sample 194 rather than between
    195 and 196.
    """
    if not ordered:
        raise ValueError("a quantile needs at least one sample")
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _degenerate_result(
    metric_name: str,
    point_estimate: float,
    confidence: float,
    seed: int,
    sample_size: int,
) -> BootstrapResult:
    return BootstrapResult(
        metric_name=metric_name,
        point_estimate=point_estimate,
        lower=point_estimate,
        upper=point_estimate,
        confidence=confidence,
        resamples=0,
        seed=seed,
        sample_size=sample_size,
    )


__all__ = [
    "BootstrapResult",
    "MetricDirection",
    "PromotionDecision",
    "TripletPrediction",
    "evaluate_promotion",
]
