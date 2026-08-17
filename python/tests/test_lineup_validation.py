"""A dated external XI prior, scored against model probabilities and reality."""

from __future__ import annotations

import pytest

from fpl_andres.models.lineup_validation import (
    LineupCandidate,
    LineupPrior,
    evaluate_lineup_prior,
)


def test_the_model_is_scored_against_the_supplied_eleven() -> None:
    prior = LineupPrior(
        club="LEE",
        fixture_id=6,
        cutoff="2026-08-17T22:30:00Z",
        source="owner-declared-validation",
        expected_names=("Trafford", "Bogle", "Rodon"),
        least_confident=("Trafford",),
    )
    candidates = [
        LineupCandidate(1, "Trafford", 0.1),
        LineupCandidate(2, "Bogle", 0.8),
        LineupCandidate(3, "Rodon", 0.7),
        LineupCandidate(4, "Perri", 0.6),
    ]

    report = evaluate_lineup_prior(prior, candidates, lineup_size=3)

    assert report.overlap == 2
    assert report.model_names == ("Bogle", "Rodon", "Perri")
    assert report.actual_overlap is None


def test_actual_starters_fill_the_post_match_score() -> None:
    prior = LineupPrior(
        club="LEE",
        fixture_id=6,
        cutoff="2026-08-17T22:30:00Z",
        source="owner-declared-validation",
        expected_names=("Trafford", "Bogle", "Rodon"),
    )
    candidates = [
        LineupCandidate(1, "Trafford", 0.1),
        LineupCandidate(2, "Bogle", 0.8),
        LineupCandidate(3, "Rodon", 0.7),
        LineupCandidate(4, "Perri", 0.6),
    ]

    report = evaluate_lineup_prior(
        prior,
        candidates,
        lineup_size=3,
        actual_element_ids={1, 2, 3},
    )

    assert report.actual_overlap == 3
    assert report.model_actual_overlap == 2
    assert report.brier_score == pytest.approx((0.9**2 + 0.2**2 + 0.3**2 + 0.6**2) / 4)


def test_accents_do_not_create_a_false_lineup_miss() -> None:
    prior = LineupPrior(
        club="LEE",
        fixture_id=6,
        cutoff="2026-08-17T22:30:00Z",
        source="owner-declared-validation",
        expected_names=("Muharemovic",),
    )
    report = evaluate_lineup_prior(
        prior,
        [LineupCandidate(1, "Muharemović", 0.8)],
        lineup_size=1,
    )

    assert report.overlap == 1
