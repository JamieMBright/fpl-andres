"""Ingest failures must be diagnosable and must not half-write a season.

- **#44** Numeric conversions raised whatever `float()` raised, deep in the
  pipeline, with no column name. Worse, `_bool` returned `False` for anything it
  did not recognise — so the day the archive switched `was_home` from
  `True`/`False` to `H`/`A`, every fixture would silently have become an away
  fixture. That is the shape of bug this project exists to refuse.

- **#59** Teams, elements, fixtures and thirty-eight gameweeks were fetched and
  written interleaved, so a dropped connection at gameweek 20 left a season with
  teams and elements and no stats. PostgREST has no transaction spanning
  requests, so the fix is ordering: every fetch happens before every write.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from fpl_andres.adapters.vaastav import VaastavRevision
from fpl_andres.ingest.historical import ArchiveFetcher, HistoricalIngest
from fpl_andres.ingest.normalise import ColumnMappingError, normalise_gameweek_stats

SNAPSHOT = "00000000-0000-4000-8000-000000000000"
AVAILABLE = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

_HEADER = (
    "element,fixture,round,minutes,total_points,goals_scored,assists,clean_sheets,"
    "goals_conceded,own_goals,penalties_saved,penalties_missed,yellow_cards,"
    "red_cards,saves,bonus,bps,value,was_home"
)
_ROW = "1,10,1,90,8,1,0,1,0,0,0,0,0,0,0,2,30,75,True"


def _stats(row: str = _ROW) -> bytes:
    return f"{_HEADER}\n{row}\n".encode()


def _normalise(row: str) -> list[dict[str, Any]]:
    return normalise_gameweek_stats(
        _stats(row),
        season="2025-26",
        gameweek=1,
        source_snapshot_id=SNAPSHOT,
        element_codes={1: 100_001},
    )


def test_a_well_formed_row_still_parses() -> None:
    assert _normalise(_ROW)[0]["total_points"] == 8


def test_a_non_numeric_value_names_its_column() -> None:
    """`float()` raised "could not convert string to float: 'n/a'" from four
    frames down, naming neither the column nor the season."""
    broken = _ROW.replace(",8,", ",n/a,", 1)

    with pytest.raises(ColumnMappingError, match="total_points") as caught:
        _normalise(broken)

    assert "'n/a'" in str(caught.value)


def test_a_non_numeric_optional_column_names_itself_too() -> None:
    header = f"{_HEADER},expected_goals"
    row = f"{_ROW},not-a-number"

    with pytest.raises(ColumnMappingError, match="expected_goals"):
        normalise_gameweek_stats(
            f"{header}\n{row}\n".encode(),
            season="2025-26",
            gameweek=1,
            source_snapshot_id=SNAPSHOT,
            element_codes={1: 100_001},
        )


@pytest.mark.parametrize("value", ["True", "true", "TRUE", "1", "t", "yes"])
def test_every_truthy_form_the_archive_uses_is_accepted(value: str) -> None:
    assert _normalise(_ROW.replace(",True", f",{value}"))[0]["was_home"] is True


@pytest.mark.parametrize("value", ["False", "false", "FALSE", "0", "f", "no"])
def test_every_falsy_form_the_archive_uses_is_accepted(value: str) -> None:
    assert _normalise(_ROW.replace(",True", f",{value}"))[0]["was_home"] is False


@pytest.mark.parametrize("value", ["H", "A", "home", "away", "2", "maybe"])
def test_an_unrecognised_boolean_is_refused_rather_than_read_as_false(
    value: str,
) -> None:
    """The bug #44 describes as "coerces silently", and the most damaging one
    available: a format change to `was_home` would have turned every fixture in
    the corpus into an away fixture, and nothing would have raised."""
    with pytest.raises(ColumnMappingError, match="was_home"):
        _normalise(_ROW.replace(",True", f",{value}"))


def test_an_empty_value_is_still_absent_rather_than_false() -> None:
    """Absent and false are different facts, and the archive uses both."""
    assert _normalise(_ROW.replace(",True", ","))[0]["was_home"] is None


class _Fetcher(ArchiveFetcher):
    """Serves canned files and fails on the nth request."""

    def __init__(self, fail_on: int | None = None) -> None:
        self.requests: list[str] = []
        self._fail_on = fail_on

    def fetch(self, url: str, *, season: str | None = None, gameweek: int | None = None) -> Any:
        self.requests.append(url)
        if self._fail_on is not None and len(self.requests) == self._fail_on:
            raise httpx.ConnectError("connection dropped", request=httpx.Request("GET", url))
        from fpl_andres.ingest.historical import FetchedFile

        if "teams" in url:
            content = b"id,code,name,short_name\n1,3,Arsenal,ARS\n"
        elif "players_raw" in url or "players" in url:
            content = b"id,code,first_name,second_name,element_type,team\n1,100001,A,B,3,1\n"
        elif "fixtures" in url:
            content = b"id,team_h,team_a,event,kickoff_time\n10,1,2,1,\n"
        else:
            # The round column must match the gameweek asked for; normalise
            # refuses a file whose rows disagree with its name.
            content = _stats(_ROW.replace(",1,90,", f",{gameweek},90,", 1))
        return FetchedFile(url=url, content=content, fetched_at=AVAILABLE)


class _Client:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def insert_ignoring_duplicates(self, table: str, rows: Any, **_: Any) -> list[Any]:
        self.writes.append(table)
        return []

    def upsert(self, table: str, rows: Any, **_: Any) -> list[Any]:
        self.writes.append(table)
        return []

    def insert(self, table: str, rows: Any, *, returning: bool = False, **_: Any) -> list[Any]:
        self.writes.append(table)
        return [{"id": SNAPSHOT}] if returning else []

    def select(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


def _ingest(fetcher: _Fetcher, client: _Client) -> Any:
    return HistoricalIngest(client=client, fetcher=fetcher).ingest_season(  # type: ignore[arg-type]
        VaastavRevision(season="2025-26", commit_sha="a" * 40),
        gameweeks=[1, 2, 3],
        data_available_at=AVAILABLE,
    )


def test_a_dropped_connection_partway_through_writes_nothing() -> None:
    """#59. Failing on the fourth request — the first gameweek file — used to
    leave seasons, teams, elements and fixtures written."""
    fetcher, client = _Fetcher(fail_on=4), _Client()

    with pytest.raises(httpx.ConnectError):
        _ingest(fetcher, client)

    assert client.writes == [], f"a failed ingest wrote: {client.writes}"


def test_every_fetch_happens_before_every_write() -> None:
    """The property, rather than one instance of it."""
    for failure_point in range(1, 7):
        fetcher, client = _Fetcher(fail_on=failure_point), _Client()

        with pytest.raises(httpx.ConnectError):
            _ingest(fetcher, client)

        assert client.writes == [], f"failing at request {failure_point} wrote rows"


def test_a_complete_ingest_still_writes_in_dependency_order() -> None:
    """Seasons before teams, teams before elements, elements before stats. A
    foreign key would refuse anything else."""
    fetcher, client = _Fetcher(), _Client()

    _ingest(fetcher, client)

    tables = [table for table in client.writes if table != "source_snapshots"]
    assert tables.index("seasons") < tables.index("teams")
    assert tables.index("teams") < tables.index("elements")
    assert tables.index("elements") < tables.index("element_gameweek_stats")
