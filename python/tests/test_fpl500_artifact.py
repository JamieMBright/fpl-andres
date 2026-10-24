"""The published FPL500 artifact says what it claims to say.

The ranking is derived offline from a 1.8 MB catalogue, so nothing at runtime
would notice it going wrong. These assert the properties the cohort portfolio
depends on, against the file that actually ships.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpl_andres.cohorts.elite import EliteSettings, ManagerSeason, SweptManager, rank_elite
from fpl_andres.jsonio import read_json_file

ARTIFACT = Path(__file__).resolve().parents[2] / "data" / "cohort" / "fpl500.json"

pytestmark = pytest.mark.skipif(
    not ARTIFACT.exists(),
    reason="FPL500 has not been published in this checkout",
)


@pytest.fixture(scope="module")
def fpl500() -> dict[str, object]:
    return read_json_file(ARTIFACT)


def test_it_holds_the_requested_five_hundred(fpl500: dict[str, object]) -> None:
    managers = fpl500["managers"]
    assert isinstance(managers, list)
    assert len(managers) == fpl500["size"] == 500
    assert len({row["entryId"] for row in managers}) == 500


def test_it_is_ordered_by_score(fpl500: dict[str, object]) -> None:
    scores = [row["score"] for row in fpl500["managers"]]
    assert scores == sorted(scores, reverse=True)


def test_every_member_is_a_long_term_performer(fpl500: dict[str, object]) -> None:
    for row in fpl500["managers"]:
        assert row["seasons"] >= fpl500["settings"]["minimumSeasons"]


def test_every_member_is_elite_at_their_best(fpl500: dict[str, object]) -> None:
    # The catalogue admits two top-10k finishes since 2021; ranking on sustained
    # percentile should leave nobody below the top 1% at their peak.
    for row in fpl500["managers"]:
        assert row["bestPercentile"] >= 0.99, row


def test_the_field_size_estimate_is_published_for_every_season_used(
    fpl500: dict[str, object],
) -> None:
    # Percentiles are only as good as this, and it is the largest rank observed
    # rather than a true entry count, so it has to be inspectable.
    field = fpl500["estimatedEntriesBySeason"]
    assert field
    seasons = {row["latestSeason"] for row in fpl500["managers"]}
    for season in seasons:
        assert season in field
        assert field[season] > 0


def test_published_percentiles_and_scores_stay_in_their_population_bounds(
    fpl500: dict[str, object],
) -> None:
    for manager in fpl500["managers"]:
        assert 0 <= manager["score"] <= 1, manager
        assert 0 <= manager["latestPercentile"] <= manager["bestPercentile"] <= 1, manager


def test_equal_relative_finishes_score_equally_in_different_sized_fields() -> None:
    managers = [
        SweptManager(1, (ManagerSeason("2024/25", points=2000, rank=101),)),
        SweptManager(2, (ManagerSeason("2025/26", points=2000, rank=1001),)),
    ]
    scores = rank_elite(
        managers,
        entries={"2024/25": 1001, "2025/26": 10001},
        settings=EliteSettings(
            decay_per_season=1,
            pre_rules_change_weight=1,
            shrinkage_weight=0,
            minimum_seasons=1,
        ),
    )

    assert len(scores) == 2
    assert [row.score for row in scores] == pytest.approx([0.9, 0.9])


def test_the_settings_that_produced_it_travel_with_it(
    fpl500: dict[str, object],
) -> None:
    settings = fpl500["settings"]
    for key in (
        "decayPerSeason",
        "preRulesChangeWeight",
        "rulesChangedIn",
        "shrinkageWeight",
        "priorPercentile",
        "minimumSeasons",
    ):
        assert key in settings, key
    # Shrinking toward the catalogue's own mean would condition on the selection.
    assert settings["priorPercentile"] == 0.5
