from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from fpl_andres.adapters.vaastav import VaastavRevision
from fpl_andres.cli.ingest_historical import SUPPORTED_SEASONS, parse_gameweeks, parse_seasons
from fpl_andres.ingest.historical import ArchiveFetcher, ArchiveFetchError, HistoricalIngest
from fpl_andres.ingest.normalise import (
    ColumnMappingError,
    normalise_fixtures,
    normalise_gameweek_stats,
    normalise_players,
    normalise_teams,
)
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient

COMMIT = "a" * 40
SEASON = "2024-25"
BASE_URL = "https://project.supabase.co"
ARCHIVE_ROOT = (
    f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{COMMIT}/data/{SEASON}"
)

TEAMS_CSV = (
    b"id,code,name,short_name,strength,strength_overall_home,strength_overall_away,"
    b"strength_attack_home,strength_attack_away,strength_defence_home,strength_defence_away\n"
    b"1,3,Arsenal,ARS,4,1300,1310,1280,1290,1270,1260\n"
    b"2,7,Aston Villa,AVL,3,1150,1140,1130,1120,1110,1100\n"
)

PLAYERS_CSV = (
    b"id,code,first_name,second_name,web_name,element_type,team,now_cost\n"
    b"11,118748,Bukayo,Saka,Saka,3,1,100\n"
    b"12,154043,Ollie,Watkins,Watkins,4,2,90\n"
)

FIXTURES_CSV = (
    b"id,event,kickoff_time,team_h,team_a,team_h_score,team_a_score,"
    b"team_h_difficulty,team_a_difficulty,finished\n"
    b"1,1,2024-08-16T19:00:00Z,1,2,2,1,2,4,True\n"
    b"2,,,2,1,,,3,3,False\n"
)

GW1_CSV = (
    b"element,round,minutes,total_points,goals_scored,assists,clean_sheets,goals_conceded,"
    b"own_goals,penalties_saved,penalties_missed,yellow_cards,red_cards,saves,bonus,bps,"
    b"value,was_home,fixture,opponent_team,kickoff_time,starts,selected,transfers_in,"
    b"transfers_out,influence,creativity,threat,ict_index,expected_goals,expected_assists,"
    b"expected_goal_involvements,expected_goals_conceded,xP\n"
    b"11,1,90,13,1,1,1,0,0,0,0,0,0,0,3,45,100,True,1,2,2024-08-16T19:00:00Z,1,3500000,"
    b"120000,4000,55.2,31.4,48.0,13.5,0.62,0.31,0.93,0.74,6.1\n"
    b"12,1,72,2,0,0,0,2,0,0,0,1,0,0,0,12,90,False,1,1,2024-08-16T19:00:00Z,1,2200000,"
    b"9000,50000,12.4,8.1,22.0,4.3,0.28,0.05,0.33,1.85,4.2\n"
)


def _credentials() -> SupabaseCredentials:
    return SupabaseCredentials(url=BASE_URL, secret_key="secret")


def test_revision_builds_every_pinned_archive_url() -> None:
    revision = VaastavRevision(commit_sha=COMMIT, season=SEASON)

    assert revision.teams_url() == f"{ARCHIVE_ROOT}/teams.csv"
    assert revision.players_url() == f"{ARCHIVE_ROOT}/players_raw.csv"
    assert revision.fixtures_url() == f"{ARCHIVE_ROOT}/fixtures.csv"
    assert revision.gameweek_url(7) == f"{ARCHIVE_ROOT}/gws/gw7.csv"


def test_gameweek_rows_normalise_with_cross_season_codes() -> None:
    rows = normalise_gameweek_stats(
        GW1_CSV,
        season=SEASON,
        gameweek=1,
        element_codes={11: 118748, 12: 154043},
        source_snapshot_id="snap-1",
    )

    assert len(rows) == 2
    saka = rows[0]
    assert saka["element_id"] == 11
    assert saka["element_code"] == 118748
    assert saka["minutes"] == 90
    assert saka["total_points"] == 13
    assert saka["was_home"] is True
    assert saka["expected_goals"] == pytest.approx(0.62)
    assert saka["source_snapshot_id"] == "snap-1"

    watkins = rows[1]
    assert watkins["was_home"] is False
    assert watkins["yellow_cards"] == 1


def test_defensive_contribution_is_null_before_2025_26_rather_than_zero() -> None:
    rows = normalise_gameweek_stats(
        GW1_CSV,
        season=SEASON,
        gameweek=1,
        element_codes={11: 118748, 12: 154043},
        source_snapshot_id="snap-1",
    )

    # A zero here would be indistinguishable from an observed zero.
    assert all(row["defensive_contribution"] is None for row in rows)


def test_defensive_contribution_is_read_when_the_season_publishes_it() -> None:
    csv_2025 = (
        GW1_CSV.replace(b",xP\n", b",xP,defensive_contribution\n")
        .replace(b",6.1\n", b",6.1,11\n")
        .replace(b",4.2\n", b",4.2,3\n")
    )

    rows = normalise_gameweek_stats(
        csv_2025,
        season="2025-26",
        gameweek=1,
        element_codes={11: 118748, 12: 154043},
        source_snapshot_id="snap-1",
    )

    assert [row["defensive_contribution"] for row in rows] == [11, 3]


def test_defensive_contribution_components_are_captured_when_published() -> None:
    csv_2025 = (
        GW1_CSV.replace(
            b",xP\n",
            b",xP,defensive_contribution,clearances_blocks_interceptions,tackles,recoveries\n",
        )
        .replace(b",6.1\n", b",6.1,21,20,1,4\n")
        .replace(b",4.2\n", b",4.2,20,7,3,10\n")
    )

    rows = normalise_gameweek_stats(
        csv_2025,
        season="2025-26",
        gameweek=1,
        element_codes={11: 118748, 12: 154043},
        source_snapshot_id="snap-1",
    )

    # Defenders qualify on CBIT, midfielders and forwards on CBIRT, so the
    # label alone cannot be modelled per position.
    assert rows[0]["clearances_blocks_interceptions"] == 20
    assert rows[0]["tackles"] == 1
    assert rows[0]["recoveries"] == 4
    assert rows[1]["recoveries"] == 10


def test_defensive_components_are_null_in_seasons_that_omit_them() -> None:
    rows = normalise_gameweek_stats(
        GW1_CSV,
        season=SEASON,
        gameweek=1,
        element_codes={11: 118748, 12: 154043},
        source_snapshot_id="snap-1",
    )

    for row in rows:
        assert row["clearances_blocks_interceptions"] is None
        assert row["tackles"] is None
        assert row["recoveries"] is None


def test_a_missing_required_column_fails_loudly_rather_than_defaulting() -> None:
    broken = GW1_CSV.replace(b"minutes,", b"", 1)

    with pytest.raises(ColumnMappingError) as error:
        normalise_gameweek_stats(
            broken,
            season=SEASON,
            gameweek=1,
            element_codes={11: 118748, 12: 154043},
            source_snapshot_id="snap-1",
        )

    assert "minutes" in str(error.value)


def test_an_unknown_element_is_rejected_rather_than_silently_dropped() -> None:
    with pytest.raises(ColumnMappingError) as error:
        normalise_gameweek_stats(
            GW1_CSV,
            season=SEASON,
            gameweek=1,
            element_codes={11: 118748},
            source_snapshot_id="snap-1",
        )

    assert "12" in str(error.value)


def test_a_gameweek_file_holding_another_round_is_rejected() -> None:
    with pytest.raises(ColumnMappingError) as error:
        normalise_gameweek_stats(
            GW1_CSV,
            season=SEASON,
            gameweek=2,
            element_codes={11: 118748, 12: 154043},
            source_snapshot_id="snap-1",
        )

    assert "round 1" in str(error.value)


def test_pre_2019_seasons_decode_as_cp1252_rather_than_crashing() -> None:
    """Archive seasons before 2019/20 are cp1252, not UTF-8.

    A player name carrying an accent (0xe9 here) raises UnicodeDecodeError
    under a strict UTF-8 read, which would abort the whole season.
    """
    latin_players = (
        b"id,code,first_name,second_name,web_name,element_type,team,now_cost\n"
        b"11,118748,Bukayo,Saka,Saka,3,1,100\n"
        b"12,154043,Rub\xe9n,Neves,Neves,3,2,90\n"
    )

    rows = normalise_players(latin_players, season="2016-17", source_snapshot_id="snap-p")

    assert rows[1]["first_name"] == "Rubén"


def test_players_and_teams_normalise_into_schema_rows() -> None:
    teams = normalise_teams(TEAMS_CSV, season=SEASON, source_snapshot_id="snap-t")
    elements = normalise_players(PLAYERS_CSV, season=SEASON, source_snapshot_id="snap-p")

    assert teams[0]["short_name"] == "ARS"
    assert teams[0]["strength_overall_home"] == 1300
    assert elements[0]["code"] == 118748
    assert elements[0]["web_name"] == "Saka"
    assert elements[1]["element_type"] == 4


def test_fixtures_normalise_and_keep_score_pairing_consistent() -> None:
    fixtures = normalise_fixtures(FIXTURES_CSV, season=SEASON, source_snapshot_id="snap-f")

    played, unplayed = fixtures
    assert played["team_h_score"] == 2
    assert played["finished"] is True
    assert unplayed["event"] is None
    assert unplayed["team_h_score"] is None
    assert unplayed["team_a_score"] is None
    assert unplayed["finished"] is False


def test_season_selection_defaults_to_every_supported_season() -> None:
    assert parse_seasons("all") == SUPPORTED_SEASONS
    assert SUPPORTED_SEASONS[0] == "2019-20"
    assert SUPPORTED_SEASONS[-1] == "2025-26"
    assert len(SUPPORTED_SEASONS) == 7


def test_season_selection_accepts_an_explicit_list() -> None:
    assert parse_seasons("2024-25,2025-26") == ("2024-25", "2025-26")
    assert parse_seasons(" 2023-24 , 2024-25 ") == ("2023-24", "2024-25")


def test_seasons_the_archive_cannot_serve_are_refused() -> None:
    # 2016-17 to 2018-19 publish no teams.csv, so the schema's foreign keys
    # cannot be satisfied. Refusing beats a partial ingest.
    with pytest.raises(ValueError, match="unsupported seasons"):
        parse_seasons("2016-17")

    with pytest.raises(ValueError, match="no seasons selected"):
        parse_seasons("")


def test_gameweek_selection_parses_ranges_and_lists() -> None:
    assert parse_gameweeks("1-3") == (1, 2, 3)
    assert parse_gameweeks("5,1,5") == (1, 5)
    assert parse_gameweeks("1-2,7") == (1, 2, 7)

    with pytest.raises(ValueError):
        parse_gameweeks("0-3")
    with pytest.raises(ValueError):
        parse_gameweeks("9-4")
    with pytest.raises(ValueError):
        parse_gameweeks("")


def _archive_root(season: str) -> str:
    return (
        f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{COMMIT}/data/{season}"
    )


def _mock_archive(season: str = SEASON, gw1_csv: bytes = GW1_CSV) -> None:
    root = _archive_root(season)
    respx.get(f"{root}/teams.csv").mock(return_value=httpx.Response(200, content=TEAMS_CSV))
    respx.get(f"{root}/players_raw.csv").mock(return_value=httpx.Response(200, content=PLAYERS_CSV))
    respx.get(f"{root}/fixtures.csv").mock(return_value=httpx.Response(200, content=FIXTURES_CSV))
    respx.get(f"{root}/gws/gw1.csv").mock(return_value=httpx.Response(200, content=gw1_csv))


def _mock_supabase() -> dict[str, respx.Route]:
    return {
        "seasons": respx.post(f"{BASE_URL}/rest/v1/seasons").mock(
            return_value=httpx.Response(201, json=[])
        ),
        "snapshots": respx.post(f"{BASE_URL}/rest/v1/source_snapshots").mock(
            return_value=httpx.Response(201, json=[{"id": "00000000-0000-4000-8000-000000000001"}])
        ),
        "teams": respx.post(f"{BASE_URL}/rest/v1/teams").mock(
            return_value=httpx.Response(201, json=[])
        ),
        "elements": respx.post(f"{BASE_URL}/rest/v1/elements").mock(
            return_value=httpx.Response(201, json=[])
        ),
        "fixtures": respx.post(f"{BASE_URL}/rest/v1/fixtures").mock(
            return_value=httpx.Response(201, json=[])
        ),
        "stats": respx.post(f"{BASE_URL}/rest/v1/element_gameweek_stats").mock(
            return_value=httpx.Response(201, json=[])
        ),
    }


@respx.mock
def test_season_ingest_records_provenance_before_writing_rows() -> None:
    _mock_archive()
    routes = _mock_supabase()

    with (
        SupabaseRestClient(_credentials()) as client,
        httpx.Client() as http,
    ):
        ingest = HistoricalIngest(client=client, fetcher=ArchiveFetcher(http))
        result = ingest.ingest_season(
            VaastavRevision(commit_sha=COMMIT, season=SEASON),
            gameweeks=(1,),
            data_available_at=datetime(2025, 6, 1, tzinfo=UTC),
        )

    assert result.teams == 2
    assert result.elements == 2
    assert result.fixtures == 2
    assert result.gameweeks == {1: 2}
    assert result.total_stat_rows == 2

    # One snapshot per fetched archive file.
    assert routes["snapshots"].call_count == 4
    assert routes["stats"].call_count == 1


@respx.mock
def test_ingest_reuses_an_existing_snapshot_when_the_hash_already_exists() -> None:
    _mock_archive()
    _mock_supabase()
    respx.post(f"{BASE_URL}/rest/v1/source_snapshots").mock(
        return_value=httpx.Response(201, json=[])
    )
    lookup = respx.get(f"{BASE_URL}/rest/v1/source_snapshots").mock(
        return_value=httpx.Response(200, json=[{"id": "00000000-0000-4000-8000-000000000009"}])
    )

    with (
        SupabaseRestClient(_credentials()) as client,
        httpx.Client() as http,
    ):
        ingest = HistoricalIngest(client=client, fetcher=ArchiveFetcher(http))
        ingest.ingest_season(
            VaastavRevision(commit_sha=COMMIT, season=SEASON),
            gameweeks=(1,),
            data_available_at=datetime(2025, 6, 1, tzinfo=UTC),
        )

    assert lookup.call_count == 4


@respx.mock
def test_a_missing_archive_file_raises_rather_than_writing_partial_state() -> None:
    respx.get(f"{ARCHIVE_ROOT}/teams.csv").mock(return_value=httpx.Response(404))
    respx.post(f"{BASE_URL}/rest/v1/seasons").mock(return_value=httpx.Response(201, json=[]))

    with (
        SupabaseRestClient(_credentials()) as client,
        httpx.Client() as http,
        pytest.raises(ArchiveFetchError),
    ):
        HistoricalIngest(client=client, fetcher=ArchiveFetcher(http)).ingest_season(
            VaastavRevision(commit_sha=COMMIT, season=SEASON),
            gameweeks=(1,),
            data_available_at=datetime(2025, 6, 1, tzinfo=UTC),
        )


@respx.mock
def test_a_gameweek_the_archive_never_published_is_skipped_not_fatal() -> None:
    """Seasons differ in length: 2019/20 ran to 47, most run to 38."""
    _mock_archive()
    routes = _mock_supabase()
    respx.get(f"{ARCHIVE_ROOT}/gws/gw39.csv").mock(return_value=httpx.Response(404))

    with SupabaseRestClient(_credentials()) as client, httpx.Client() as http:
        result = HistoricalIngest(client=client, fetcher=ArchiveFetcher(http)).ingest_season(
            VaastavRevision(commit_sha=COMMIT, season=SEASON),
            gameweeks=(1, 39),
            data_available_at=datetime(2025, 6, 1, tzinfo=UTC),
        )

    assert result.gameweeks == {1: 2}
    assert routes["stats"].call_count == 1


@respx.mock
def test_a_double_gameweek_keeps_one_row_per_fixture() -> None:
    """A shared key would collapse the second fixture and break the upsert."""
    double = GW1_CSV + (
        b"11,1,62,7,1,0,0,1,0,0,0,0,0,0,1,28,100,False,9,4,2024-08-19T19:00:00Z,1,"
        b"3500000,120000,4000,30.1,12.0,24.0,6.6,0.41,0.10,0.51,0.90,5.0\n"
    )
    _mock_archive(gw1_csv=double)
    routes = _mock_supabase()

    with SupabaseRestClient(_credentials()) as client, httpx.Client() as http:
        result = HistoricalIngest(client=client, fetcher=ArchiveFetcher(http)).ingest_season(
            VaastavRevision(commit_sha=COMMIT, season=SEASON),
            gameweeks=(1,),
            data_available_at=datetime(2025, 6, 1, tzinfo=UTC),
        )

    assert result.gameweeks == {1: 3}
    written = json.loads(routes["stats"].calls[0].request.content)
    element_11 = [row for row in written if row["element_id"] == 11]
    assert len(element_11) == 2
    assert {row["fixture_id"] for row in element_11} == {1, 9}

    # The conflict target must include the fixture or the upsert fails 21000.
    assert (
        routes["stats"].calls[0].request.url.params["on_conflict"]
        == "season,gameweek,element_id,fixture_id"
    )


@respx.mock
def test_a_gameweek_row_without_a_fixture_is_rejected() -> None:
    missing = GW1_CSV.replace(b",fixture,", b",", 1).replace(b",True,1,2,", b",True,2,", 1)

    with pytest.raises(ColumnMappingError, match="fixture"):
        normalise_gameweek_stats(
            missing,
            season=SEASON,
            gameweek=1,
            element_codes={11: 118748, 12: 154043},
            source_snapshot_id="snap-1",
        )


def test_a_verbatim_duplicate_row_is_collapsed() -> None:
    """The archive repeats some elements with byte-identical stats."""
    saka_row = GW1_CSV.split(b"\n")[1]
    doubled = GW1_CSV + saka_row + b"\n"

    rows = normalise_gameweek_stats(
        doubled,
        season=SEASON,
        gameweek=1,
        element_codes={11: 118748, 12: 154043},
        source_snapshot_id="snap-1",
    )

    assert len(rows) == 2


def test_a_duplicate_key_with_different_values_is_rejected() -> None:
    """Picking a winner would be an invented fact, so this must fail loudly."""
    saka_row = GW1_CSV.split(b"\n")[1]
    conflicting = saka_row.replace(b",90,13,", b",90,99,", 1)
    doubled = GW1_CSV + conflicting + b"\n"

    with pytest.raises(ColumnMappingError, match="conflicting values"):
        normalise_gameweek_stats(
            doubled,
            season=SEASON,
            gameweek=1,
            element_codes={11: 118748, 12: 154043},
            source_snapshot_id="snap-1",
        )


@respx.mock
def test_defcon_columns_survive_all_the_way_into_the_write_payload() -> None:
    """Guards the whole path, not just the normaliser.

    DefCon is the reason 2025/26 is ingested at all, so a regression that
    dropped these columns between normalisation and the POST would be silent
    and would cost a full re-ingest to discover.
    """
    defcon_csv = (
        GW1_CSV.replace(
            b",xP\n",
            b",xP,defensive_contribution,clearances_blocks_interceptions,tackles,recoveries\n",
        )
        .replace(b",6.1\n", b",6.1,21,20,1,4\n")
        .replace(b",4.2\n", b",4.2,12,5,3,4\n")
    )
    _mock_archive(season="2025-26", gw1_csv=defcon_csv)
    routes = _mock_supabase()

    with SupabaseRestClient(_credentials()) as client, httpx.Client() as http:
        HistoricalIngest(client=client, fetcher=ArchiveFetcher(http)).ingest_season(
            VaastavRevision(commit_sha=COMMIT, season="2025-26"),
            gameweeks=(1,),
            data_available_at=datetime(2026, 6, 1, tzinfo=UTC),
        )

    written = json.loads(routes["stats"].calls[0].request.content)
    assert [row["defensive_contribution"] for row in written] == [21, 12]
    assert [row["clearances_blocks_interceptions"] for row in written] == [20, 5]
    assert [row["tackles"] for row in written] == [1, 3]
    assert [row["recoveries"] for row in written] == [4, 4]
