"""The requests this client actually puts on the wire.

The persistence tests asserted that a mocked client was called
and what rows it was given. None of them checked the request PostgREST would
receive — the `Prefer` header, the `on_conflict` parameter, the batching, the
content type — so a change to any of those would pass every test and fail
against a real database.

These assert the HTTP request. They still do not need a database, which is the
point: the dialect is a property of the request, and the request is
inspectable.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx
import pytest

from fpl_andres.persistence.supabase import (
    _MAX_ROWS_PER_REQUEST,
    SupabaseCredentials,
    SupabaseRestClient,
    SupabaseWriteError,
)

SECRET = "sb_secret_" + "0" * 32


class Recorder:
    """Captures every request and answers with a canned response."""

    def __init__(
        self,
        status: int = 201,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self._status = status
        self._body = body if body is not None else []
        self._headers = headers

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            self._status,
            json=self._body,
            headers=self._headers,
            request=request,
        )

    @property
    def only(self) -> httpx.Request:
        assert len(self.requests) == 1, f"expected one request, got {len(self.requests)}"
        return self.requests[0]

    def prefer(self, index: int = 0) -> set[str]:
        return set(self.requests[index].headers["Prefer"].split(","))

    def body(self, index: int = 0) -> Any:
        return json.loads(self.requests[index].content)


def _client(recorder: Recorder) -> SupabaseRestClient:
    return SupabaseRestClient(
        credentials=SupabaseCredentials(url="https://p.supabase.invalid", secret_key=SECRET),
        transport=httpx.MockTransport(recorder),
    )


def _rows(count: int) -> list[dict[str, Any]]:
    return [{"season": "2025-26", "element_id": index} for index in range(count)]


def test_an_insert_asks_for_nothing_back_by_default() -> None:
    """`return=minimal` matters: PostgREST otherwise serialises every written
    row into the response, which on a 500-row batch is the whole payload again."""
    recorder = Recorder()

    _client(recorder).insert("elements", _rows(1))

    assert recorder.prefer() == {"return=minimal"}
    assert "on_conflict" not in recorder.only.url.params


def test_asking_for_the_written_rows_changes_the_prefer_header() -> None:
    recorder = Recorder(body=[{"id": "x"}])

    written = _client(recorder).insert("elements", _rows(1), returning=True)

    assert recorder.prefer() == {"return=representation"}
    assert written == [{"id": "x"}]


def test_an_upsert_sends_both_the_resolution_and_the_conflict_target() -> None:
    """PostgREST needs both. `resolution=merge-duplicates` without
    `on_conflict` resolves against the primary key, which for the corpus is not
    the key the caller means."""
    recorder = Recorder()

    _client(recorder).upsert("elements", _rows(1), on_conflict="season,element_id")

    assert recorder.prefer() == {"return=minimal", "resolution=merge-duplicates"}
    assert recorder.only.url.params["on_conflict"] == "season,element_id"


def test_ignoring_duplicates_uses_the_other_resolution() -> None:
    recorder = Recorder()

    _client(recorder).insert_ignoring_duplicates(
        "seasons", [{"season": "2025-26"}], on_conflict="season"
    )

    assert recorder.prefer() == {"return=minimal", "resolution=ignore-duplicates"}


def test_a_conflict_target_naming_a_column_the_rows_lack_is_refused() -> None:
    """Silently, PostgREST would insert rather than merge. That is audit #58."""
    recorder = Recorder()

    with pytest.raises(SupabaseWriteError, match="on_conflict column"):
        _client(recorder).upsert("elements", _rows(1), on_conflict="season,code")

    assert recorder.requests == [], "a refused upsert must not reach the network"


def test_a_large_write_is_split_into_batches() -> None:
    """PostgREST and the gateway in front of it both cap a request body. A
    38-gameweek season is tens of thousands of rows."""
    recorder = Recorder()
    count = _MAX_ROWS_PER_REQUEST * 2 + 1

    _client(recorder).insert("element_gameweek_stats", _rows(count))

    assert len(recorder.requests) == 3
    assert [len(recorder.body(i)) for i in range(3)] == [
        _MAX_ROWS_PER_REQUEST,
        _MAX_ROWS_PER_REQUEST,
        1,
    ]


def test_every_batch_carries_the_same_conflict_target() -> None:
    """A batch that lost it would insert duplicates for its share of the rows."""
    recorder = Recorder()

    _client(recorder).upsert(
        "element_gameweek_stats",
        _rows(_MAX_ROWS_PER_REQUEST + 1),
        on_conflict="season,element_id",
    )

    assert len(recorder.requests) == 2
    for index in range(2):
        assert recorder.requests[index].url.params["on_conflict"] == "season,element_id"
        assert "resolution=merge-duplicates" in recorder.prefer(index)


def test_no_batch_is_sent_for_an_empty_write() -> None:
    recorder = Recorder()

    assert _client(recorder).insert("elements", []) == []
    assert recorder.requests == []


def test_the_body_is_compact_json() -> None:
    """Whitespace in a 500-row batch is bandwidth spent on nothing."""
    recorder = Recorder()

    _client(recorder).insert("elements", _rows(2))

    assert b", " not in recorder.only.content
    assert b'": ' not in recorder.only.content


def test_credentials_travel_in_both_headers_postgrest_expects() -> None:
    recorder = Recorder()

    _client(recorder).insert("elements", _rows(1))

    assert recorder.only.headers["apikey"] == SECRET
    assert recorder.only.headers["Authorization"] == f"Bearer {SECRET}"


def test_an_update_filters_rather_than_rewriting_the_table() -> None:
    """A PATCH with no filter updates every row. PostgREST allows it."""
    recorder = Recorder(status=204)

    _client(recorder).update("workflow_runs", {"status": "succeeded"}, filters={"id": "eq.7"})

    assert recorder.only.method == "PATCH"
    assert recorder.only.url.params["id"] == "eq.7"
    assert "return=minimal" in recorder.prefer()


def test_a_delete_filters_rather_than_clearing_the_table() -> None:
    recorder = Recorder(status=204)

    _client(recorder).delete(
        "analysis_requests",
        filters={"requested_at": "lt.2026-07-01T00:00:00Z"},
    )

    assert recorder.only.method == "DELETE"
    assert recorder.only.url.params["requested_at"] == "lt.2026-07-01T00:00:00Z"
    assert "return=minimal" in recorder.prefer()


def test_a_delete_without_a_filter_is_refused_before_the_network() -> None:
    recorder = Recorder(status=204)

    with pytest.raises(ValueError, match="at least one filter"):
        _client(recorder).delete("analysis_requests", filters={})

    assert recorder.requests == []


def test_an_exact_count_uses_head_and_reads_content_range() -> None:
    recorder = Recorder(status=200, headers={"Content-Range": "0-24/357"})

    count = _client(recorder).count(
        "analysis_requests",
        filters={"requested_at": "lt.2026-07-01T00:00:00Z"},
    )

    assert recorder.only.method == "HEAD"
    assert recorder.only.headers["Prefer"] == "count=exact"
    assert count == 357


def test_a_select_sends_its_filters_and_ordering() -> None:
    recorder = Recorder(status=200, body=[{"season": "2025-26"}])

    rows = _client(recorder).select(
        "elements",
        columns="season,element_id",
        filters={"season": "eq.2025-26"},
        order="element_id",
        limit=10,
    )

    params = recorder.only.url.params
    assert params["select"] == "season,element_id"
    assert params["season"] == "eq.2025-26"
    assert params["order"] == "element_id"
    assert params["limit"] == "10"
    assert rows == [{"season": "2025-26"}]


def test_a_postgrest_error_names_the_table_and_the_status() -> None:
    """The failure an operator reads first."""
    recorder = Recorder(status=409, body={"message": "duplicate key"})

    with pytest.raises(SupabaseWriteError, match="elements write failed with 409"):
        _client(recorder).insert("elements", _rows(1))


def test_a_postgrest_error_never_carries_the_key_back() -> None:
    """A gateway quoting the apikey header back on a 401 is how the service-role
    key reached the logs in #73."""
    recorder = Recorder(status=401, body={"message": f"invalid apikey {SECRET}"})

    with pytest.raises(SupabaseWriteError) as caught:
        _client(recorder).insert("elements", _rows(1))

    assert SECRET not in str(caught.value)


@pytest.mark.slow
def test_a_server_error_is_retried_and_a_client_error_is_not() -> None:
    """Retrying a 409 asks the same question again; retrying a 503 does not.

    Sleeps for real, because the backoff is the behaviour under test.
    """
    server = Recorder(status=503, body={})
    with pytest.raises(SupabaseWriteError):
        _client(server).insert("elements", _rows(1))
    assert len(server.requests) > 1

    client = Recorder(status=400, body={})
    with pytest.raises(SupabaseWriteError):
        _client(client).insert("elements", _rows(1))
    assert len(client.requests) == 1
