from __future__ import annotations

from fpl_andres.cohorts.points_to_rank import rank_band


def catalogue() -> list[dict[str, object]]:
    return [
        {"seasons": [{"season": "2025/26", "points": 1900, "rank": 5_000_000}]},
        {"seasons": [{"season": "2025/26", "points": 1950, "rank": 4_000_000}]},
        {"seasons": [{"season": "2025/26", "points": 1950, "rank": 4_100_000}]},
        {"seasons": [{"season": "2025/26", "points": 2000, "rank": 3_000_000}]},
        {"seasons": [{"season": "2024/25", "points": 1950, "rank": 900_000}]},
    ]


def test_brackets_the_nearest_measured_finishes() -> None:
    band = rank_band(catalogue(), season="2025/26", points=1975, minimum_sample=3)

    assert band is not None
    assert (band.lower_points, band.upper_points) == (1950, 2000)
    assert (band.rank_from, band.rank_to) == (3_000_000, 4_100_000)
    assert band.sample_size == 3


def test_an_exact_score_uses_every_observation_at_that_score() -> None:
    band = rank_band(catalogue(), season="2025/26", points=1950, minimum_sample=2)

    assert band is not None
    assert (band.rank_from, band.rank_to) == (4_000_000, 4_100_000)
    assert band.sample_size == 2


def test_better_points_never_produce_a_worse_bracket() -> None:
    lower = rank_band(catalogue(), season="2025/26", points=1925, minimum_sample=2)
    higher = rank_band(catalogue(), season="2025/26", points=1975, minimum_sample=2)

    assert lower is not None and higher is not None
    assert higher.rank_from < lower.rank_from
    assert higher.rank_to < lower.rank_to


def test_refuses_to_extrapolate_beyond_the_catalogue() -> None:
    assert rank_band(catalogue(), season="2025/26", points=1800, minimum_sample=2) is None
    assert rank_band(catalogue(), season="2025/26", points=2100, minimum_sample=2) is None


def test_seasons_never_leak_into_each_other() -> None:
    band = rank_band(catalogue(), season="2025/26", points=1950, minimum_sample=2)

    assert band is not None
    assert band.rank_from != 900_000


def test_refuses_a_catalogue_below_the_sample_floor() -> None:
    assert rank_band(catalogue(), season="2025/26", points=1950) is None


def test_refuses_an_invalid_sample_floor() -> None:
    import pytest

    with pytest.raises(ValueError, match="at least two"):
        rank_band(catalogue(), season="2025/26", points=1950, minimum_sample=1)
