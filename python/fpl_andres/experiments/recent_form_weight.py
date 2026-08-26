"""Held-out recent-form blend experiment outside the production model path."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fpl_andres.backtesting.captain_significance import _family_confidence
from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.backtesting.projector import (
    ProjectionSettings,
    baseline_ownership,
    baseline_recent_mean,
    project_gameweek,
)
from fpl_andres.models.metrics import rank_correlation
from fpl_andres.models.promotion import (
    PromotionDecision,
    TripletPrediction,
    evaluate_promotion,
)

CANDIDATE_WEIGHTS = (0.10, 0.15, 0.20, 0.25, 0.30)
INCUMBENT_WEIGHT = 0.20
SPEARMAN_REGRESSION_LIMIT = 0.005
FAMILY_SIZE = len(CANDIDATE_WEIGHTS) - 1
CONFIDENCE = 0.95
MINIMUM_WEEKS = 32
RESAMPLES = 2_000
SEED = 17
SEED_REPLICATES = 3


@dataclass(frozen=True)
class WeightScore:
    weekly_mae: tuple[float, ...]
    mean_spearman: float | None

    @property
    def mean_mae(self) -> float:
        if not self.weekly_mae:
            raise ValueError("recent-form weight has no scored gameweeks")
        return sum(self.weekly_mae) / len(self.weekly_mae)


@dataclass(frozen=True)
class SeasonWeightScore:
    season: str
    by_weight: dict[float, WeightScore]


@dataclass(frozen=True)
class WeightEvaluation:
    candidate_weight: float
    decision: PromotionDecision
    family_size: int
    confidence: float
    spearman_regressions: dict[str, float]
    promoted: bool
    reason_codes: tuple[str, ...]


def _mean(values: Sequence[float], _observed: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean metric requires at least one value")
    return sum(values) / len(values)


def _settings(weight: float) -> ProjectionSettings:
    return ProjectionSettings(recent_form_weight=weight)


def score_recent_form_weights(
    corpus: SeasonCorpus,
    *,
    weights: Sequence[float] = CANDIDATE_WEIGHTS,
    minimum_history: int = 6,
    minimum_players: int = 20,
) -> SeasonWeightScore:
    """Score all weights on one shared player population per gameweek."""
    ordered_weights = tuple(weights)
    if set(ordered_weights) != set(CANDIDATE_WEIGHTS):
        raise ValueError("recent-form experiment requires the predeclared candidate grid")
    weekly_mae: dict[float, list[float]] = {weight: [] for weight in ordered_weights}
    weekly_spearman: dict[float, list[float]] = {weight: [] for weight in ordered_weights}

    for gameweek in corpus.gameweeks:
        if gameweek <= minimum_history:
            continue
        actual = corpus.actual_points(gameweek)
        if not actual:
            continue
        projections = {
            weight: {
                row.element_id: row.expected_points
                for row in project_gameweek(corpus, gameweek, settings=_settings(weight))
            }
            for weight in ordered_weights
        }
        recent = baseline_recent_mean(corpus, gameweek)
        ownership = baseline_ownership(corpus, gameweek)
        shared = set(actual) & set(recent) & set(ownership)
        for ranking in projections.values():
            shared &= set(ranking)
        population = sorted(shared)
        if len(population) < minimum_players:
            continue
        realised = [float(actual[element]) for element in population]
        for weight in ordered_weights:
            predicted = [projections[weight][element] for element in population]
            weekly_mae[weight].append(
                sum(
                    abs(forecast - outcome)
                    for forecast, outcome in zip(predicted, realised, strict=True)
                )
                / len(population)
            )
            correlation = rank_correlation(predicted, realised)
            if correlation is not None:
                weekly_spearman[weight].append(correlation)

    return SeasonWeightScore(
        season=corpus.season,
        by_weight={
            weight: WeightScore(
                weekly_mae=tuple(weekly_mae[weight]),
                mean_spearman=(
                    sum(weekly_spearman[weight]) / len(weekly_spearman[weight])
                    if weekly_spearman[weight]
                    else None
                ),
            )
            for weight in ordered_weights
        },
    )


def select_weight(scores: Sequence[SeasonWeightScore]) -> float:
    """Select on training MAE, preferring the incumbent when tied."""
    if not scores:
        raise ValueError("recent-form selection requires training seasons")

    def pooled_mean(weight: float) -> float:
        values = [value for score in scores for value in score.by_weight[weight].weekly_mae]
        if not values:
            raise ValueError(f"recent-form weight {weight} has no training weeks")
        return sum(values) / len(values)

    return min(
        CANDIDATE_WEIGHTS,
        key=lambda weight: (
            pooled_mean(weight),
            abs(weight - INCUMBENT_WEIGHT),
            weight,
        ),
    )


def evaluate_weight(
    scores: Sequence[SeasonWeightScore],
    *,
    candidate_weight: float,
    resamples: int = RESAMPLES,
) -> WeightEvaluation:
    """Apply family-corrected paired MAE and the per-season rank veto."""
    if candidate_weight not in CANDIDATE_WEIGHTS:
        raise ValueError("candidate weight is outside the predeclared grid")
    triplets = tuple(
        TripletPrediction(baseline=baseline, candidate=candidate, observed=0.0)
        for score in scores
        for baseline, candidate in zip(
            score.by_weight[INCUMBENT_WEIGHT].weekly_mae,
            score.by_weight[candidate_weight].weekly_mae,
            strict=True,
        )
    )
    confidence = _family_confidence(FAMILY_SIZE, CONFIDENCE)
    decision = evaluate_promotion(
        triplets,
        metric_name="weekly_mae",
        metric=_mean,
        metric_direction="lower_is_better",
        resamples=resamples,
        seed=SEED,
        confidence=confidence,
        minimum_sample_size=MINIMUM_WEEKS,
        seed_replicates=SEED_REPLICATES,
    )
    regressions: dict[str, float] = {}
    missing_spearman = False
    for score in scores:
        baseline = score.by_weight[INCUMBENT_WEIGHT].mean_spearman
        candidate = score.by_weight[candidate_weight].mean_spearman
        if baseline is None or candidate is None:
            missing_spearman = True
            continue
        regressions[score.season] = baseline - candidate
    reasons: tuple[str, ...]
    if missing_spearman:
        promoted = False
        reasons = ("spearman_unavailable",)
    elif any(regression > SPEARMAN_REGRESSION_LIMIT for regression in regressions.values()):
        promoted = False
        reasons = ("spearman_regression",)
    else:
        promoted = decision.promoted
        reasons = decision.reason_codes
    return WeightEvaluation(
        candidate_weight=candidate_weight,
        decision=decision,
        family_size=FAMILY_SIZE,
        confidence=confidence,
        spearman_regressions=regressions,
        promoted=promoted,
        reason_codes=reasons,
    )


__all__ = [
    "CANDIDATE_WEIGHTS",
    "INCUMBENT_WEIGHT",
    "SeasonWeightScore",
    "WeightEvaluation",
    "WeightScore",
    "evaluate_weight",
    "score_recent_form_weights",
    "select_weight",
]
