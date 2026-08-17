"""The odds ingest CLI: what it fetches, where it writes, and what it refuses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpl_andres.adapters.football_data import FixtureOdds, fixtures_url, season_url
from fpl_andres.adapters.the_odds_api import read_fixture_odds
from fpl_andres.cli.ingest_odds import (
    BACKTEST_SEASONS,
    TEAM_CODES,
    OddsIngestError,
    UnknownClubError,
    _entry,
    _fetch,
    _merge_fixture_entries,
    _parser,
    _priced,
    _uncovered_team_events,
)


class _StubResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = ""


class _StubClient:
    """Just enough httpx.Client to exercise the status handling."""

    def __init__(self, statuses: dict[str, int]) -> None:
        self._statuses = statuses

    def get(self, url: str, timeout: float) -> _StubResponse:
        return _StubResponse(self._statuses.get(url, 200))


PRICED = FixtureOdds(
    division="E0",
    kickoff=None,
    home_team="Arsenal",
    away_team="Bournemouth",
    home_odds=1.40,
    draw_odds=5.00,
    away_odds=8.00,
    over_odds=1.75,
    under_odds=2.10,
    price_source="average",
    markets={"AvgH": 1.40, "AvgD": 5.00, "AvgA": 8.00},
)


class TestCrosswalk:
    def test_maps_onto_fpl_short_codes_not_display_names(self) -> None:
        # Every other artifact here joins on the short code. Mapping to "Man
        # Utd" produced a file that looked right and matched nothing.
        assert TEAM_CODES["Man United"] == "MUN"
        assert TEAM_CODES["Tottenham"] == "TOT"
        assert TEAM_CODES["Nott'm Forest"] == "NFO"

    def test_covers_the_whole_of_the_current_division(self) -> None:
        current = {
            "ARS",
            "AVL",
            "BHA",
            "BOU",
            "BRE",
            "CHE",
            "COV",
            "CRY",
            "EVE",
            "FUL",
            "HUL",
            "IPS",
            "LEE",
            "LIV",
            "MCI",
            "MUN",
            "NEW",
            "NFO",
            "SUN",
            "TOT",
        }
        assert current <= set(TEAM_CODES.values())

    def test_covers_every_club_of_the_backtest_seasons(self) -> None:
        # 2023-24 published 342 of 380 fixtures because Luton was missing here.
        # 38 fixtures is exactly one club's season, and it read as a rounding
        # shortfall rather than a hole.
        for club in ["Luton", "Sheffield United", "Burnley", "Ipswich", "Leicester"]:
            assert club in TEAM_CODES, club

    def test_an_unmapped_club_refuses_the_fixture(self) -> None:
        # A silently dropped fixture is a fixture priced as if it had no
        # market, which is the one failure mode invisible downstream.
        unknown = FixtureOdds(**{**PRICED.__dict__, "home_team": "Real Madrid"})
        with pytest.raises(UnknownClubError, match="Real Madrid"):
            _entry(unknown, _priced(unknown), keep_markets=False)

    def test_history_keeps_every_price_and_the_site_keeps_none(self) -> None:
        # The corpus needs the raw markets to train on later; the site needs
        # only the derived numbers, not a hundred prices per fixture.
        corpus = _entry(PRICED, _priced(PRICED), keep_markets=True)
        site = _entry(PRICED, _priced(PRICED), keep_markets=False)
        assert "markets" in corpus
        assert "markets" not in site
        assert site["homeCleanSheet"] == corpus["homeCleanSheet"]


class TestPreSeason:
    def test_a_missing_season_file_is_not_an_error(self) -> None:
        # football-data creates a season's played-match file only once matches
        # have been played, so between seasons it 404s while the fixture list
        # is already priced. Treating that as failure stopped the job in
        # exactly the weeks a manager is choosing an opening squad.
        client = _StubClient({season_url("2026-27"): 404})
        assert _fetch(season_url("2026-27"), client, required=False) is None

    def test_a_missing_required_file_still_fails(self) -> None:
        client = _StubClient({fixtures_url(): 404})
        with pytest.raises(OddsIngestError, match="404"):
            _fetch(fixtures_url(), client, required=True)

    def test_a_server_error_fails_even_when_optional(self) -> None:
        # 404 means "not published yet". 500 means the host is broken, and
        # carrying on would publish a partial artifact as if it were complete.
        client = _StubClient({season_url("2026-27"): 500})
        with pytest.raises(OddsIngestError, match="500"):
            _fetch(season_url("2026-27"), client, required=False)

    def test_the_backtest_seasons_are_the_ones_validate_runs_on(self) -> None:
        # Odds have to cover the same ground as the backtest or the comparison
        # against the history model has nothing to stand on.
        validation = json.loads(
            Path("apps/web/src/data/validation.json").read_text(encoding="utf-8")
        )
        assert set(BACKTEST_SEASONS) == {season["season"] for season in validation["seasons"]}

    def test_every_backtest_season_has_a_reachable_url_shape(self) -> None:
        assert season_url("2022-23").endswith("/mmz4281/2223/E0.csv")
        for season in BACKTEST_SEASONS:
            assert season_url(season).endswith("/E0.csv")

    def test_history_defaults_outside_the_site_bundle(self) -> None:
        # Four seasons is about fifteen hundred fixtures. It belongs in the
        # corpus, not in every visitor's download.
        args = _parser().parse_args(["--season", "2026-27"])
        assert "apps/web" not in args.backfill_dir
        assert args.backfill_seasons == []

    def test_backfill_seasons_are_accepted_as_a_list(self) -> None:
        args = _parser().parse_args(
            ["--season", "2026-27", "--backfill-seasons", "2022-23", "2023-24"]
        )
        assert args.backfill_seasons == ["2022-23", "2023-24"]


class TestTheOddsApiFallback:
    def test_reads_the_median_one_x_two_and_total_markets(self) -> None:
        row = read_fixture_odds(
            {
                "home_team": "Arsenal",
                "away_team": "Bournemouth",
                "commence_time": "2026-08-21T19:00:00Z",
                "bookmakers": [
                    {
                        "key": "a",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Arsenal", "price": 1.4},
                                    {"name": "Draw", "price": 5.0},
                                    {"name": "Bournemouth", "price": 8.0},
                                ],
                            },
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over", "point": 2.5, "price": 1.75},
                                    {"name": "Under", "point": 2.5, "price": 2.1},
                                ],
                            },
                        ],
                    },
                    {
                        "key": "b",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Arsenal", "price": 1.5},
                                    {"name": "Draw", "price": 4.8},
                                    {"name": "Bournemouth", "price": 7.5},
                                ],
                            },
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over", "point": 2.5, "price": 1.85},
                                    {"name": "Under", "point": 2.5, "price": 2.0},
                                ],
                            },
                        ],
                    },
                ],
            }
        )

        assert row is not None
        assert row.home_team == "Arsenal"
        assert row.away_team == "Bournemouth"
        assert row.home_odds == pytest.approx(1.45)
        assert row.draw_odds == pytest.approx(4.9)
        assert row.away_odds == pytest.approx(7.75)
        assert row.over_odds == pytest.approx(1.8)
        assert row.under_odds == pytest.approx(2.05)
        assert row.price_source == "the-odds-api-median"

    def test_refuses_a_fixture_without_both_required_markets(self) -> None:
        assert (
            read_fixture_odds(
                {
                    "home_team": "Arsenal",
                    "away_team": "Bournemouth",
                    "bookmakers": [],
                }
            )
            is None
        )

    def test_only_the_current_rounds_uncovered_fixtures_are_selected(self) -> None:
        events = [
            {
                "id": "covered",
                "home_team": "Arsenal",
                "away_team": "Coventry City",
                "commence_time": "2026-08-21T19:00:00Z",
            },
            {
                "id": "current",
                "home_team": "Nottingham Forest",
                "away_team": "Leeds United",
                "commence_time": "2026-08-22T14:00:00Z",
            },
            {
                "id": "next-week",
                "home_team": "Arsenal",
                "away_team": "Everton",
                "commence_time": "2026-08-28T19:00:00Z",
            },
        ]
        existing = [
            {
                "home": "ARS",
                "away": "COV",
                "kickoff": "2026-08-21T19:00:00+00:00",
            }
        ]

        selected = _uncovered_team_events(events, existing)

        assert [event["id"] for event in selected] == ["current"]

    def test_fresh_rows_replace_the_same_fixture_and_retain_the_rest(self) -> None:
        previous = [
            {"home": "ARS", "away": "COV", "kickoff": "2026-08-21T19:00:00+00:00"},
            {"home": "NFO", "away": "LEE", "kickoff": "2026-08-22T14:00:00+00:00"},
        ]
        fresh = [
            {
                "home": "ARS",
                "away": "COV",
                "kickoff": "2026-08-21T19:00:00+00:00",
                "homeExpectedGoals": 2.0,
            }
        ]

        merged = _merge_fixture_entries(previous, fresh)

        assert len(merged) == 2
        arsenal = next(row for row in merged if row["home"] == "ARS")
        assert arsenal["homeExpectedGoals"] == 2.0
