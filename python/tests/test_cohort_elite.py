"""Ranking the catalogue down to FPL500.

The property that matters is that the ranking answers the question asked:
sustained elite finishing, judged relative to the field of the day, weighted
toward the game as it is currently scored.
"""

from __future__ import annotations

import pytest

from fpl_andres.cohorts.elite import (
    EliteSettings,
    ManagerSeason,
    SweptManager,
    entries_by_season,
    rank_elite,
    season_start_year,
)


def manager(entry_id: int, finishes: dict[str, int]) -> SweptManager:
    return SweptManager(
        entry_id=entry_id,
        seasons=tuple(
            ManagerSeason(season=season, points=2000, rank=rank)
            for season, rank in finishes.items()
        ),
    )


FIELD = {
    "2021/22": 9_000_000,
    "2022/23": 11_000_000,
    "2023/24": 10_600_000,
    "2024/25": 8_600_000,
    "2025/26": 13_000_000,
}


def test_season_labels_are_parsed_not_guessed() -> None:
    assert season_start_year("2025/26") == 2025
    assert season_start_year("2006/07") == 2006
    with pytest.raises(ValueError, match="not an FPL season"):
        season_start_year("last year")


def test_the_field_size_is_taken_from_the_worst_rank_observed() -> None:
    managers = [
        manager(1, {"2025/26": 500}),
        manager(2, {"2025/26": 4_000_000}),
        manager(3, {"2024/25": 12}),
    ]

    assert entries_by_season(managers) == {"2025/26": 4_000_000, "2024/25": 12}


def test_relative_position_beats_absolute_rank_across_eras() -> None:
    """The whole point. 10,000th in a 1.1M field is worse than 10,000th in 13M."""
    field = {"2006/07": 1_100_000, "2025/26": 13_000_000}
    early = manager(1, {"2006/07": 10_000, "2025/26": 200_000})
    late = manager(2, {"2006/07": 200_000, "2025/26": 10_000})

    ranked = rank_elite(
        [early, late],
        entries=field,
        settings=EliteSettings(minimum_seasons=1),
        top=2,
    )
    by_id = {row.entry_id: row for row in ranked}

    # Both have one strong and one weak season; the modern 10,000th is a far
    # better relative finish, and recency compounds it.
    assert by_id[2].score > by_id[1].score


def test_recent_seasons_outweigh_old_ones() -> None:
    recent = manager(1, {"2024/25": 5_000, "2025/26": 5_000, "2021/22": 500_000})
    old = manager(2, {"2021/22": 5_000, "2022/23": 5_000, "2025/26": 500_000})

    ranked = rank_elite([recent, old], entries=FIELD, top=2)
    by_id = {row.entry_id: row for row in ranked}

    assert by_id[1].score > by_id[2].score


def test_the_new_scoring_rules_widen_the_gap_beyond_age_alone() -> None:
    """Defensive contributions arrived in 2025/26, so seasons before it are
    evidence about a different game — a discount on top of being older."""
    modern = manager(1, {"2025/26": 2_000, "2024/25": 2_000, "2021/22": 4_000_000})
    dated = manager(2, {"2021/22": 2_000, "2022/23": 2_000, "2025/26": 4_000_000})

    def gap(pre_rules_change_weight: float) -> float:
        settings = EliteSettings(pre_rules_change_weight=pre_rules_change_weight)
        ranked = rank_elite([modern, dated], entries=FIELD, settings=settings, top=2)
        by_id = {row.entry_id: row for row in ranked}
        return by_id[1].score - by_id[2].score

    # Recency alone already favours the modern manager; the rules step must
    # favour him further, or it is not doing anything the decay was not.
    assert gap(1.0) > 0
    assert gap(0.5) > gap(1.0)


def test_a_short_record_is_shrunk_toward_the_middle() -> None:
    settings = EliteSettings(minimum_seasons=1, shrinkage_weight=3.0)
    brief = manager(1, {"2025/26": 100})
    sustained = manager(
        2,
        {season: 100 for season in FIELD},
    )

    ranked = rank_elite([brief, sustained], entries=FIELD, settings=settings, top=2)
    by_id = {row.entry_id: row for row in ranked}

    # Identical quality, different amounts of evidence. Long term wins.
    assert by_id[2].score > by_id[1].score
    assert by_id[2].total_weight > by_id[1].total_weight


def test_managers_without_enough_history_are_left_out_entirely() -> None:
    settings = EliteSettings(minimum_seasons=3)
    thin = manager(1, {"2025/26": 10, "2024/25": 10})
    thick = manager(2, {"2025/26": 10, "2024/25": 10, "2023/24": 10})

    ranked = rank_elite([thin, thick], entries=FIELD, settings=settings, top=10)

    assert [row.entry_id for row in ranked] == [2]


def test_the_ranking_is_capped_and_ordered() -> None:
    managers = [manager(i, {season: (i + 1) * 1_000 for season in FIELD}) for i in range(50)]

    ranked = rank_elite(managers, entries=FIELD, top=10)

    assert len(ranked) == 10
    assert [row.entry_id for row in ranked] == list(range(10))
    scores = [row.score for row in ranked]
    assert scores == sorted(scores, reverse=True)


def test_a_season_with_no_field_size_fails_rather_than_scoring_as_zero() -> None:
    managers = [manager(1, {"2019/20": 5_000, "2025/26": 5_000})]

    with pytest.raises(ValueError, match="2019/20"):
        rank_elite(managers, entries={"2025/26": 13_000_000}, top=1)


def test_percentile_is_bounded_and_first_place_is_the_top() -> None:
    settings = EliteSettings(minimum_seasons=1)
    winner = manager(1, {"2025/26": 1})

    ranked = rank_elite([winner], entries=FIELD, settings=settings, top=1)

    assert ranked[0].best_percentile == pytest.approx(1.0)
    assert 0.0 <= ranked[0].score <= 1.0


def test_the_latest_season_is_reported_so_a_dormant_manager_is_visible() -> None:
    settings = EliteSettings(minimum_seasons=1)
    dormant = manager(1, {"2021/22": 500, "2022/23": 600})

    ranked = rank_elite(dormant and [dormant], entries=FIELD, settings=settings, top=1)

    assert ranked[0].latest_season == "2022/23"


def test_an_empty_catalogue_ranks_nothing_rather_than_failing() -> None:
    assert rank_elite([], top=500) == ()


def test_a_ranking_of_no_size_is_refused() -> None:
    with pytest.raises(ValueError, match="positive size"):
        rank_elite([manager(1, {"2025/26": 1})], entries=FIELD, top=0)
