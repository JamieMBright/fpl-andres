import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from fpl_andres.adapters.fpl import (
    FplClient,
    FplContractError,
    FplPicksUnavailable,
    normalize_entry,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fpl" / "bootstrap_rules_2026_27.json"
ENTRY_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fpl" / "entry_preseason.json"
FETCHED_AT = datetime(2026, 7, 29, 17, 6, 32, tzinfo=UTC)


class OversizedAsyncStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = False
        self.read_beyond_limit = False

    async def __aiter__(self):
        yield b"{" + b" " * (4 * 1024 * 1024 - 1)
        yield b" " * (2 * 1024 * 1024)
        self.read_beyond_limit = True
        raise AssertionError("adapter read beyond the configured body limit")

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_bootstrap_fetch_attaches_exact_source_provenance() -> None:
    document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    raw_payload = json.dumps(
        document["payload"],
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://fantasy.premierleague.com/api/bootstrap-static/").mock(
            return_value=httpx.Response(
                200,
                content=raw_payload,
                headers={"Content-Type": "application/json"},
            )
        )

        async with httpx.AsyncClient() as http:
            client = FplClient(http=http, clock=lambda: FETCHED_AT)
            fetched = await client.fetch_bootstrap()

    assert fetched.payload == document["payload"]
    assert fetched.snapshot.source == "fpl"
    assert fetched.snapshot.fetched_at == FETCHED_AT
    assert fetched.snapshot.data_available_at == FETCHED_AT
    assert fetched.snapshot.upstream_reference.endswith("/api/bootstrap-static/")
    assert fetched.snapshot.content_hash == f"sha256:{hashlib.sha256(raw_payload).hexdigest()}"
    assert route.called
    request = route.calls.last.request
    assert request.headers["Accept"] == "application/json"
    assert "FPLAndres/0.4" in request.headers["User-Agent"]


@pytest.mark.asyncio
async def test_bootstrap_fetch_retries_transient_status_with_bounded_backoff() -> None:
    document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    responses = [
        httpx.Response(
            503,
            json={"detail": "temporarily unavailable"},
            headers={"Content-Type": "application/json"},
        ),
        httpx.Response(
            200,
            json=document["payload"],
            headers={"Content-Type": "application/json"},
        ),
    ]
    sleep = AsyncMock()

    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://fantasy.premierleague.com/api/bootstrap-static/").mock(
            side_effect=responses
        )
        async with httpx.AsyncClient() as http:
            client = FplClient(
                http=http,
                clock=lambda: FETCHED_AT,
                sleep=sleep,
                random=lambda: 0.5,
            )
            fetched = await client.fetch_bootstrap()

    assert fetched.payload == document["payload"]
    assert route.call_count == 2
    sleep.assert_awaited_once_with(0.5)


@pytest.mark.asyncio
async def test_bootstrap_fetch_does_not_retry_not_found() -> None:
    sleep = AsyncMock()

    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://fantasy.premierleague.com/api/bootstrap-static/").mock(
            return_value=httpx.Response(
                404,
                json={"detail": "not found"},
                headers={"Content-Type": "application/json"},
            )
        )
        async with httpx.AsyncClient() as http:
            client = FplClient(http=http, clock=lambda: FETCHED_AT, sleep=sleep)
            with pytest.raises(httpx.HTTPStatusError):
                await client.fetch_bootstrap()

    assert route.call_count == 1
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_bootstrap_fetch_rejects_declared_oversized_response() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://fantasy.premierleague.com/api/bootstrap-static/").mock(
            return_value=httpx.Response(
                200,
                content=b"{}",
                headers={
                    "Content-Length": str(8 * 1024 * 1024 + 1),
                    "Content-Type": "application/json",
                },
            )
        )
        async with httpx.AsyncClient() as http:
            client = FplClient(http=http, clock=lambda: FETCHED_AT)
            with pytest.raises(FplContractError, match="allowed size"):
                await client.fetch_bootstrap()


@pytest.mark.asyncio
async def test_entry_fetch_stops_chunked_body_at_size_limit() -> None:
    stream = OversizedAsyncStream()
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://fantasy.premierleague.com/api/entry/123/").mock(
            return_value=httpx.Response(
                200,
                stream=stream,
                headers={"Content-Type": "application/json"},
            )
        )
        async with httpx.AsyncClient() as http:
            client = FplClient(http=http, clock=lambda: FETCHED_AT)
            with pytest.raises(FplContractError, match="allowed size"):
                await client.fetch_entry(123)

    assert stream.closed
    assert not stream.read_beyond_limit


@pytest.mark.asyncio
async def test_adapter_methods_use_exact_allowlisted_endpoint_paths() -> None:
    object_response = httpx.Response(
        200,
        json={"ok": True},
        headers={"Content-Type": "application/json"},
    )
    fixtures_response = httpx.Response(
        200,
        json=[{"id": 1, "event": 5}],
        headers={"Content-Type": "application/json"},
    )

    with respx.mock(assert_all_called=True) as mock:
        routes = [
            mock.get("https://fantasy.premierleague.com/api/fixtures/?event=5").mock(
                return_value=fixtures_response
            ),
            mock.get("https://fantasy.premierleague.com/api/entry/123/").mock(
                return_value=object_response
            ),
            mock.get("https://fantasy.premierleague.com/api/entry/123/history/").mock(
                return_value=object_response
            ),
            mock.get("https://fantasy.premierleague.com/api/entry/123/event/5/picks/").mock(
                return_value=object_response
            ),
            mock.get("https://fantasy.premierleague.com/api/element-summary/456/").mock(
                return_value=object_response
            ),
            mock.get(
                "https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
                params={"page_standings": 3, "phase": 2},
            ).mock(return_value=object_response),
        ]

        async with httpx.AsyncClient() as http:
            client = FplClient(http=http, clock=lambda: FETCHED_AT)
            fixtures = await client.fetch_fixtures(event=5)
            await client.fetch_entry(123)
            await client.fetch_entry_history(123)
            await client.fetch_entry_picks(123, event=5)
            await client.fetch_element_summary(456)
            await client.fetch_standings(314, page_standings=3, phase=2)

    assert fixtures.payload == [{"id": 1, "event": 5}]
    assert fixtures.snapshot.upstream_reference.endswith("/api/fixtures/?event=5")
    assert all(route.called for route in routes)


@pytest.mark.asyncio
async def test_adapter_rejects_out_of_range_ids_before_network() -> None:
    async with httpx.AsyncClient() as http:
        client = FplClient(http=http, clock=lambda: FETCHED_AT)
        with pytest.raises(FplContractError, match="event ID"):
            await client.fetch_fixtures(event=39)
        with pytest.raises(FplContractError, match="element ID"):
            await client.fetch_element_summary(2_001)


@pytest.mark.asyncio
async def test_picks_not_found_is_typed_without_guessing_why() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://fantasy.premierleague.com/api/entry/123/event/38/picks/").mock(
            return_value=httpx.Response(
                404,
                json={"detail": "Not found."},
                headers={"Content-Type": "application/json"},
            )
        )
        async with httpx.AsyncClient() as http:
            client = FplClient(http=http, clock=lambda: FETCHED_AT)
            with pytest.raises(FplPicksUnavailable) as caught:
                await client.fetch_entry_picks(123, event=38)

    assert caught.value.entry_id == 123
    assert caught.value.event == 38


def test_entry_normalization_preserves_explicit_unknowns_and_drops_identity() -> None:
    raw_entry = json.loads(ENTRY_FIXTURE_PATH.read_text(encoding="utf-8"))

    entry = normalize_entry(raw_entry)

    assert entry.id == 1
    assert entry.current_event is None
    assert entry.last_deadline_bank is None
    assert "playerFirstName" not in entry.model_dump(by_alias=True)


def test_entry_normalization_rejects_missing_bank_instead_of_treating_it_as_null() -> None:
    raw_entry = json.loads(ENTRY_FIXTURE_PATH.read_text(encoding="utf-8"))
    missing_bank = deepcopy(raw_entry)
    del missing_bank["last_deadline_bank"]

    with pytest.raises(FplContractError, match="last_deadline_bank"):
        normalize_entry(missing_bank)
