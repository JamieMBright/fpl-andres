from __future__ import annotations

import pytest

from fpl_andres.experiments.recent_form_weight import (
    CANDIDATE_WEIGHTS,
    INCUMBENT_WEIGHT,
    SeasonWeightScore,
    WeightScore,
    evaluate_weight,
    select_weight,
)


def _score(
    season: str,
    maes: dict[float, tuple[float, ...]],
    spearman: dict[float, float],
) -> SeasonWeightScore:
    return SeasonWeightScore(
        season=season,
        by_weight={
            weight: WeightScore(weekly_mae=values, mean_spearman=spearman[weight])
            for weight, values in maes.items()
        },
    )


def test_equal_training_mae_keeps_the_incumbent() -> None:
    tied = {weight: (1.0, 1.0) for weight in CANDIDATE_WEIGHTS}
    spearman = {weight: 0.5 for weight in CANDIDATE_WEIGHTS}

    assert select_weight([_score("2022-23", tied, spearman)]) == INCUMBENT_WEIGHT


def test_training_selection_uses_mae_only_before_holdout() -> None:
    maes = {weight: (1.0, 1.0) for weight in CANDIDATE_WEIGHTS}
    maes[0.15] = (0.8, 0.9)
    spearman = {weight: 0.5 for weight in CANDIDATE_WEIGHTS}

    assert select_weight([_score("2022-23", maes, spearman)]) == 0.15


def test_paired_mae_uses_a_family_of_four_challengers() -> None:
    baseline = (1.0,) * 40
    candidate = (0.5,) * 40
    maes = {weight: baseline for weight in CANDIDATE_WEIGHTS}
    maes[0.15] = candidate
    spearman = {weight: 0.5 for weight in CANDIDATE_WEIGHTS}

    result = evaluate_weight(
        [_score("2024-25", maes, spearman)],
        candidate_weight=0.15,
        resamples=200,
    )

    assert result.family_size == 4
    assert result.confidence == pytest.approx(0.9875)
    assert result.decision.promoted
    assert result.promoted


def test_spearman_regression_vetoes_an_mae_winner() -> None:
    baseline = (1.0,) * 40
    candidate = (0.5,) * 40
    maes = {weight: baseline for weight in CANDIDATE_WEIGHTS}
    maes[0.15] = candidate
    spearman = {weight: 0.6 for weight in CANDIDATE_WEIGHTS}
    spearman[0.15] = 0.594

    result = evaluate_weight(
        [_score("2024-25", maes, spearman)],
        candidate_weight=0.15,
        resamples=200,
    )

    assert result.decision.promoted
    assert not result.promoted
    assert result.reason_codes == ("spearman_regression",)
    assert result.spearman_regressions == {"2024-25": pytest.approx(0.006)}


def test_incumbent_never_promotes_against_itself() -> None:
    maes = {weight: (1.0,) * 40 for weight in CANDIDATE_WEIGHTS}
    spearman = {weight: 0.5 for weight in CANDIDATE_WEIGHTS}

    result = evaluate_weight(
        [_score("2024-25", maes, spearman)],
        candidate_weight=INCUMBENT_WEIGHT,
        resamples=200,
    )

    assert not result.promoted
    assert result.reason_codes == ("no_improvement",)
