"""Parsing the football-data.co.uk odds feed.

The network this repository is developed on refuses the host, so the parser is
deliberately separate from the fetch and is tested against fixed text. That is
the only way to have tests for a source that cannot be reached from the desk.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fpl_andres.adapters.football_data import (
    OddsContractError,
    fixtures_url,
    parse_odds_csv,
    season_url,
)

FETCHED = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)

HEADER = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,"
    "AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5,"
    "B365H,B365D,B365A,B365>2.5,B365<2.5,"
    "AvgCH,AvgCD,AvgCA"
)


def csv_of(*rows: str) -> str:
    return "\n".join((HEADER, *rows)) + "\n"


class TestUrls:
    def test_a_season_maps_onto_the_feeds_own_naming(self) -> None:
        assert season_url("2026-27").endswith("/mmz4281/2627/E0.csv")

    def test_refuses_a_season_that_is_not_the_archive_format(self) -> None:
        with pytest.raises(OddsContractError):
            season_url("2026")

    def test_unplayed_matches_come_from_a_separate_file(self) -> None:
        assert fixtures_url().endswith("/fixtures.csv")


class TestParse:
    def test_reads_a_complete_row(self) -> None:
        batch = parse_odds_csv(
            csv_of(
                "E0,15/08/2026,20:00,Arsenal,Bournemouth,0,0,"
                "1.40,5.00,8.00,1.75,2.10,"
                "1.42,5.20,8.50,1.78,2.05,"
                "1.30,5.50,9.00"
            ),
            upstream_reference="test",
            fetched_at=FETCHED,
        )

        assert len(batch.rows) == 1
        row = batch.rows[0]
        assert row.home_team == "Arsenal"
        assert row.home_odds == 1.40
        assert row.over_odds == 1.75
        assert row.price_source == "average"

    def test_prefers_the_market_average_over_a_single_book(self) -> None:
        # One book carries its own bias into every fixture it prices.
        batch = parse_odds_csv(
            csv_of(
                "E0,15/08/2026,20:00,Arsenal,Bournemouth,0,0,"
                "1.40,5.00,8.00,1.75,2.10,"
                "1.42,5.20,8.50,1.78,2.05,"
                "1.30,5.50,9.00"
            ),
            upstream_reference="test",
            fetched_at=FETCHED,
        )
        assert batch.rows[0].draw_odds == 5.00

    def test_falls_back_to_bet365_when_the_average_is_absent(self) -> None:
        batch = parse_odds_csv(
            csv_of(
                "E0,15/08/2026,20:00,Arsenal,Bournemouth,0,0,"
                ",,,1.75,2.10,"
                "1.42,5.20,8.50,1.78,2.05,"
                "1.30,5.50,9.00"
            ),
            upstream_reference="test",
            fetched_at=FETCHED,
        )
        assert batch.rows[0].price_source == "bet365"
        assert batch.rows[0].home_odds == 1.42

    def test_never_reads_a_closing_price(self) -> None:
        # Closing prices carry team news that lands after the FPL deadline, so
        # fitting on them would score information no manager could have had.
        batch = parse_odds_csv(
            csv_of(
                "E0,15/08/2026,20:00,Arsenal,Bournemouth,0,0,"
                "1.40,5.00,8.00,1.75,2.10,"
                "1.42,5.20,8.50,1.78,2.05,"
                "1.30,5.50,9.00"
            ),
            upstream_reference="test",
            fetched_at=FETCHED,
        )
        assert batch.rows[0].home_odds != 1.30

    def test_a_row_with_half_a_book_is_reported_not_filled_in(self) -> None:
        batch = parse_odds_csv(
            csv_of(
                "E0,15/08/2026,20:00,Arsenal,Bournemouth,0,0,1.40,5.00,8.00,,,,,,,,1.30,5.50,9.00"
            ),
            upstream_reference="test",
            fetched_at=FETCHED,
        )
        assert batch.rows == ()
        assert batch.skipped == (("Arsenal v Bournemouth", "no complete over/under 2.5 market"),)

    def test_ignores_other_divisions(self) -> None:
        batch = parse_odds_csv(
            csv_of(
                "E1,15/08/2026,20:00,Watford,Millwall,0,0,"
                "1.40,5.00,8.00,1.75,2.10,"
                "1.42,5.20,8.50,1.78,2.05,"
                "1.30,5.50,9.00"
            ),
            upstream_reference="test",
            fetched_at=FETCHED,
        )
        assert batch.rows == ()
        assert batch.skipped == ()

    def test_refuses_a_feed_that_changed_shape(self) -> None:
        with pytest.raises(OddsContractError, match="feed shape changed"):
            parse_odds_csv(
                "Div,Something,Else\nE0,1,2\n",
                upstream_reference="test",
                fetched_at=FETCHED,
            )

    def test_hashes_what_it_read_so_a_republish_is_detectable(self) -> None:
        batch = parse_odds_csv(
            csv_of(
                "E0,15/08/2026,20:00,Arsenal,Bournemouth,0,0,"
                "1.40,5.00,8.00,1.75,2.10,"
                "1.42,5.20,8.50,1.78,2.05,"
                "1.30,5.50,9.00"
            ),
            upstream_reference="test",
            fetched_at=FETCHED,
        )
        assert batch.content_hash.startswith("sha256:")

    def test_refuses_a_naive_timestamp(self) -> None:
        with pytest.raises(OddsContractError):
            parse_odds_csv(csv_of(""), upstream_reference="test", fetched_at=datetime(2026, 8, 7))
