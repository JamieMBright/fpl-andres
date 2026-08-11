from __future__ import annotations

from fpl_andres.cohorts.points_to_rank import (
    RANK_CUTOFFS,
    classify_points,
    rank_boundaries,
)


def catalogue() -> list[dict[str, object]]:
    return [
        {"seasons": [{"season": "2025/26", "points": 2500, "rank": 900}]},
        {"seasons": [{"season": "2025/26", "points": 2499, "rank": 1100}]},
        {"seasons": [{"season": "2025/26", "points": 2400, "rank": 9_900}]},
        {"seasons": [{"season": "2025/26", "points": 2399, "rank": 10_100}]},
        {"seasons": [{"season": "2025/26", "points": 2200, "rank": 499_000}]},
        {"seasons": [{"season": "2025/26", "points": 2200, "rank": 501_000}]},
        {"seasons": [{"season": "2025/26", "points": 2100, "rank": 990_000}]},
        {"seasons": [{"season": "2025/26", "points": 2099, "rank": 1_010_000}]},
        {"seasons": [{"season": "2025/26", "points": 2000, "rank": 1_990_000}]},
        {"seasons": [{"season": "2025/26", "points": 1999, "rank": 2_010_000}]},
        {"seasons": [{"season": "2025/26", "points": 1900, "rank": 2_990_000}]},
        {"seasons": [{"season": "2025/26", "points": 1899, "rank": 3_010_000}]},
        {"seasons": [{"season": "2024/25", "points": 2500, "rank": 8_000_000}]},
    ]


def test_the_requested_rank_cutoffs_are_fixed() -> None:
    assert RANK_CUTOFFS == (
        1_000,
        10_000,
        50_000,
        100_000,
        250_000,
        500_000,
        1_000_000,
        2_000_000,
        3_000_000,
    )


def test_boundaries_use_the_nearest_finish_on_each_side() -> None:
    boundaries = rank_boundaries(catalogue(), season="2025/26")
    top_10k = next(boundary for boundary in boundaries if boundary.rank_cutoff == 10_000)

    assert top_10k.inside.rank == 9_900
    assert top_10k.inside.points == 2400
    assert top_10k.outside.rank == 10_100
    assert top_10k.outside.points == 2399
    assert top_10k.rank_gap == 200
    assert top_10k.status == "bracketed"


def test_equal_points_on_both_sides_are_a_tie_not_an_exact_threshold() -> None:
    boundaries = rank_boundaries(catalogue(), season="2025/26")
    top_500k = next(boundary for boundary in boundaries if boundary.rank_cutoff == 500_000)

    assert top_500k.inside.points == top_500k.outside.points == 2200
    assert top_500k.status == "tie_at_cutoff"
    estimate = classify_points(boundaries, points=2200)
    assert estimate is not None
    assert estimate.status == "around"
    assert estimate.rank_cutoff == 500_000


def test_score_is_classified_into_the_first_cutoff_it_clearly_beats() -> None:
    boundaries = rank_boundaries(catalogue(), season="2025/26")

    top_1k = classify_points(boundaries, points=2501)
    top_10k = classify_points(boundaries, points=2400)
    top_1m = classify_points(boundaries, points=2100)
    outside = classify_points(boundaries, points=1800)
    assert top_1k is not None and top_1k.rank_cutoff == 1_000
    assert top_10k is not None and top_10k.rank_cutoff == 10_000
    assert top_1m is not None and top_1m.rank_cutoff == 1_000_000
    assert outside is not None and outside.status == "outside"


def test_a_score_between_observed_point_levels_is_around_the_cutoff() -> None:
    rows = [
        {"seasons": [{"season": "2025/26", "points": 2302, "rank": 99_000}]},
        {"seasons": [{"season": "2025/26", "points": 2298, "rank": 101_000}]},
    ]
    estimate = classify_points(
        rank_boundaries(rows, season="2025/26", cutoffs=(100_000,)),
        points=2300,
    )

    assert estimate is not None
    assert estimate.status == "around"
    assert estimate.rank_cutoff == 100_000


def test_seasons_never_leak_into_each_other() -> None:
    boundaries = rank_boundaries(catalogue(), season="2025/26", cutoffs=(1_000,))

    assert boundaries[0].inside.rank == 900
    assert boundaries[0].outside.rank == 1_100


def test_an_unbracketed_cutoff_is_unavailable() -> None:
    boundaries = rank_boundaries(catalogue()[:1], season="2025/26", cutoffs=(1_000,))

    assert boundaries == ()
    assert classify_points(boundaries, points=2500) is None
