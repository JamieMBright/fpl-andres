from __future__ import annotations

import pytest

from fpl_andres.cohorts.veterans import (
    CohortCriteria,
    CohortError,
    ManagerRecord,
    SeasonFinish,
    extract_entry_ids,
    parse_history,
    qualifies,
    rank_cohort,
)

CRITERIA = CohortCriteria(
    elite_rank_threshold=10_000,
    minimum_elite_seasons=2,
    minimum_seasons_played=3,
)


def _history(*seasons: tuple[str, int, int]) -> dict[str, object]:
    return {
        "past": [
            {"season_name": name, "total_points": points, "rank": rank}
            for name, points, rank in seasons
        ]
    }


def test_a_record_is_derived_from_the_official_history() -> None:
    record = parse_history(
        1,
        _history(("2022/23", 2543, 69), ("2023/24", 2283, 1204), ("2024/25", 2308, 19)),
    )

    assert record.entry_id == 1
    assert record.seasons_played == 3
    assert record.best_rank == 19


def test_an_incomplete_season_is_skipped_rather_than_placed() -> None:
    payload = _history(("2023/24", 2283, 1204))
    payload["past"].append({"season_name": "2024/25", "total_points": 900, "rank": None})  # type: ignore[union-attr]

    record = parse_history(7, payload)

    # A null rank means the season was never completed.
    assert record.seasons_played == 1


def test_a_payload_without_past_seasons_is_rejected() -> None:
    with pytest.raises(CohortError, match="no past seasons"):
        parse_history(7, {"current": []})


def test_a_malformed_season_name_is_rejected() -> None:
    with pytest.raises(CohortError, match="season name"):
        parse_history(7, {"past": [{"season_name": "last year", "total_points": 1, "rank": 1}]})


def test_sustained_elite_finishes_qualify() -> None:
    record = parse_history(
        1,
        _history(("2022/23", 2543, 69), ("2023/24", 2283, 4_100), ("2024/25", 2308, 900)),
    )

    assert qualifies(record, CRITERIA) is True


def test_a_single_spike_does_not_qualify() -> None:
    # One top finish out of eleven million carries real luck.
    record = parse_history(
        2,
        _history(("2022/23", 2543, 42), ("2023/24", 2100, 900_000), ("2024/25", 2050, 1_200_000)),
    )

    assert qualifies(record, CRITERIA) is False


def test_too_few_seasons_does_not_qualify() -> None:
    record = parse_history(3, _history(("2023/24", 2543, 12), ("2024/25", 2500, 40)))

    assert qualifies(record, CRITERIA) is False


def test_criteria_reject_an_incoherent_configuration() -> None:
    with pytest.raises(ValueError, match="seasons played"):
        CohortCriteria(
            elite_rank_threshold=10_000,
            minimum_elite_seasons=5,
            minimum_seasons_played=2,
        )


def test_the_cohort_is_ordered_by_consistency_then_peak() -> None:
    consistent = ManagerRecord(
        entry_id=10,
        finishes=tuple(
            SeasonFinish(season_name=f"20{year}/2{year - 19}", total_points=2400, rank=5_000)
            for year in (20, 21, 22, 23)
        ),
    )
    peaky = ManagerRecord(
        entry_id=11,
        finishes=(
            SeasonFinish(season_name="2022/23", total_points=2600, rank=3),
            SeasonFinish(season_name="2023/24", total_points=2400, rank=9_000),
            SeasonFinish(season_name="2024/25", total_points=2100, rank=800_000),
        ),
    )

    ordered = rank_cohort([peaky, consistent], CRITERIA)

    assert [record.entry_id for record in ordered] == [10, 11]


def test_candidate_ids_are_read_from_pasted_urls_and_bare_numbers() -> None:
    pasted = """
    https://fantasy.premierleague.com/entry/1/history
    Some name — https://fantasy.premierleague.com/entry/2/event/38
    212279
    1
    not-an-id
    """

    assert extract_entry_ids(pasted) == (1, 2, 212279)


def test_candidate_extraction_is_capped() -> None:
    pasted = "\n".join(str(index) for index in range(1, 50))

    assert len(extract_entry_ids(pasted, limit=10)) == 10
