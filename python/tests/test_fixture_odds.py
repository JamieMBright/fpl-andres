"""The join from a priced fixture to the quantity the projector asks for."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_andres.models.fixture_odds import (
    OddsArtifactError,
    club_views,
    load_fixture_odds,
)

# Arsenal expected to score 2.14 at home, Bournemouth 0.73.
FIXTURE = {
    "kickoff": "2026-08-15T19:00:00+00:00",
    "home": "ARS",
    "away": "BOU",
    "homeExpectedGoals": 2.142,
    "awayExpectedGoals": 0.731,
    "homeCleanSheet": 0.4814,
    "awayCleanSheet": 0.1174,
    "drawResidual": 0.0019,
    "priceSource": "average",
}


class TestClubViews:
    def test_a_clean_sheet_belongs_to_the_side_keeping_it(self) -> None:
        # The easiest mistake here is crediting a clean sheet to the side that
        # scored, so this is pinned rather than left to review.
        views = club_views([dict(FIXTURE)])

        arsenal = views["ARS"][0]
        assert arsenal.opponent == "BOU"
        assert arsenal.home is True
        assert arsenal.expected_goals == pytest.approx(2.142)
        assert arsenal.opponent_expected_goals == pytest.approx(0.731)
        assert arsenal.clean_sheet == pytest.approx(0.4814)

    def test_the_weaker_side_is_less_likely_to_keep_one(self) -> None:
        views = club_views([dict(FIXTURE)])
        assert views["BOU"][0].clean_sheet < views["ARS"][0].clean_sheet

    def test_one_fixture_becomes_two_club_views(self) -> None:
        views = club_views([dict(FIXTURE)])
        assert sorted(views) == ["ARS", "BOU"]
        assert views["BOU"][0].home is False

    def test_a_club_with_no_priced_fixture_is_absent_not_averaged(self) -> None:
        # A fixture with no market is a fixture with no evidence, which is not
        # the same as a fixture priced level.
        views = club_views([dict(FIXTURE)])
        assert "LIV" not in views

    def test_matches_come_back_in_kickoff_order(self) -> None:
        later = dict(FIXTURE)
        later["kickoff"] = "2026-08-22T14:00:00+00:00"
        later["away"] = "LIV"
        views = club_views([later, dict(FIXTURE)])
        kickoffs = [match.kickoff for match in views["ARS"]]
        assert kickoffs == sorted(kickoffs)

    def test_refuses_a_row_with_no_club_code(self) -> None:
        broken = dict(FIXTURE)
        del broken["home"]
        with pytest.raises(OddsArtifactError, match="club code"):
            club_views([broken])

    def test_refuses_a_row_with_a_non_numeric_expectation(self) -> None:
        broken = dict(FIXTURE)
        broken["homeExpectedGoals"] = "lots"
        with pytest.raises(OddsArtifactError, match="numeric"):
            club_views([broken])


class TestLoad:
    def test_reads_the_published_shape(self, tmp_path: Path) -> None:
        path = tmp_path / "fixture-odds.json"
        path.write_text(json.dumps({"schemaVersion": 1, "fixtures": [FIXTURE]}), encoding="utf-8")
        assert len(load_fixture_odds(path)) == 1

    def test_names_the_workflow_when_the_artifact_is_missing(self, tmp_path: Path) -> None:
        with pytest.raises(OddsArtifactError, match="Ingest Bookmaker Odds"):
            load_fixture_odds(tmp_path / "absent.json")

    def test_refuses_an_artifact_with_no_fixtures_list(self, tmp_path: Path) -> None:
        path = tmp_path / "fixture-odds.json"
        path.write_text(json.dumps({"schemaVersion": 1}), encoding="utf-8")
        with pytest.raises(OddsArtifactError, match="no fixtures"):
            load_fixture_odds(path)

    def test_a_naive_kickoff_is_read_as_utc(self, tmp_path: Path) -> None:
        naive = dict(FIXTURE)
        naive["kickoff"] = "2026-08-15T19:00:00"
        views = club_views([naive])
        assert views["ARS"][0].kickoff == datetime(2026, 8, 15, 19, 0, tzinfo=UTC)
