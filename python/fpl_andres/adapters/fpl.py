from __future__ import annotations

import asyncio
import hashlib
import json
import random as random_module
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any, cast
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError

from fpl_andres import timeouts
from fpl_andres.contracts import FetchedPayload, FplEntry, SourceSnapshot
from fpl_andres.timeguard import is_utc
from fpl_andres.timeouts import client_timeout

FPL_API_BASE = "https://fantasy.premierleague.com/api/"
FPL_USER_AGENT = "FPLAndres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
BOOTSTRAP_LIMIT_BYTES = 8 * 1024 * 1024
DEFAULT_LIMIT_BYTES = 5 * 1024 * 1024
MAX_PUBLIC_ID = 4_294_967_295
MAX_ELEMENT_ID = 2_000
MAX_EVENT_ID = 38
MAX_PAGE = 9_999
MAX_PHASE = 99
MAX_ATTEMPTS = 3
MAX_RETRY_AFTER_SECONDS = 30.0
# Caps the exponential itself, not just the number of attempts, so raising
# MAX_ATTEMPTS later cannot silently turn a retry into a minutes-long stall
# inside an unattended workflow.
MAX_BACKOFF_SECONDS = 8.0
# Consecutive upstream failures before the adapter stops asking. A sweeping job
# should not spend an hour hammering an endpoint that is plainly down.
CIRCUIT_BREAKER_THRESHOLD = 12
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

Sleep = Callable[[float], Awaitable[None]]


class FplContractError(ValueError):
    """Raised when FPL responds with a shape unsafe for downstream use."""


class FplUpstreamDown(RuntimeError):
    """Raised when the adapter has given up on an endpoint that keeps failing."""


class FplPicksUnavailable(LookupError):
    """Raised when an entry's picks for an event are not public.

    Expected, not exceptional: picks stay private until the deadline passes, and
    a manager who did not play a gameweek never has any. Callers degrade rather
    than refuse.
    """

    def __init__(self, entry_id: int, event: int) -> None:
        super().__init__(f"picks are unavailable for entry {entry_id}, event {event}")
        self.entry_id = entry_id
        self.event = event


def normalize_entry(payload: Mapping[str, Any]) -> FplEntry:
    normalized = {
        "id": _required_raw_field(payload, "id"),
        "name": _required_raw_field(payload, "name"),
        "startedEvent": _required_raw_field(payload, "started_event"),
        "currentEvent": _required_raw_field(payload, "current_event"),
        "lastDeadlineBank": _required_raw_field(payload, "last_deadline_bank"),
        "lastDeadlineValue": _required_raw_field(payload, "last_deadline_value"),
        "lastDeadlineTotalTransfers": _required_raw_field(
            payload,
            "last_deadline_total_transfers",
        ),
    }
    try:
        return FplEntry.model_validate(normalized)
    except ValidationError as error:
        raise FplContractError(f"invalid FPL entry payload: {error}") from error


class FplClient:
    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        clock: Callable[[], datetime],
        sleep: Sleep = asyncio.sleep,
        random: Callable[[], float] = random_module.random,
    ) -> None:
        self._http = http
        self._clock = clock
        self._sleep = sleep
        self._random = random
        self._consecutive_failures = 0

    async def fetch_bootstrap(self) -> FetchedPayload[dict[str, Any]]:
        return await self._fetch_json_object(
            "bootstrap-static/",
            size_limit=BOOTSTRAP_LIMIT_BYTES,
        )

    async def fetch_fixtures(
        self,
        *,
        event: int | None = None,
    ) -> FetchedPayload[list[dict[str, Any]]]:
        path = "fixtures/"
        if event is not None:
            _require_id("event ID", event, MAX_EVENT_ID)
            path = f"{path}?{urlencode({'event': event})}"
        return await self._fetch_json_array(path, size_limit=DEFAULT_LIMIT_BYTES)

    async def fetch_entry(self, entry_id: int) -> FetchedPayload[dict[str, Any]]:
        _require_id("entry ID", entry_id, MAX_PUBLIC_ID)
        return await self._fetch_json_object(
            f"entry/{entry_id}/",
            size_limit=DEFAULT_LIMIT_BYTES,
        )

    async def fetch_entry_history(self, entry_id: int) -> FetchedPayload[dict[str, Any]]:
        _require_id("entry ID", entry_id, MAX_PUBLIC_ID)
        return await self._fetch_json_object(
            f"entry/{entry_id}/history/",
            size_limit=DEFAULT_LIMIT_BYTES,
        )

    async def fetch_entry_picks(
        self,
        entry_id: int,
        *,
        event: int,
    ) -> FetchedPayload[dict[str, Any]]:
        _require_id("entry ID", entry_id, MAX_PUBLIC_ID)
        _require_id("event ID", event, MAX_EVENT_ID)
        try:
            return await self._fetch_json_object(
                f"entry/{entry_id}/event/{event}/picks/",
                size_limit=DEFAULT_LIMIT_BYTES,
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                raise FplPicksUnavailable(entry_id, event) from error
            raise

    async def fetch_element_summary(
        self,
        element_id: int,
    ) -> FetchedPayload[dict[str, Any]]:
        _require_id("element ID", element_id, MAX_ELEMENT_ID)
        return await self._fetch_json_object(
            f"element-summary/{element_id}/",
            size_limit=DEFAULT_LIMIT_BYTES,
        )

    async def fetch_standings(
        self,
        league_id: int,
        *,
        page_standings: int = 1,
        page_new_entries: int | None = None,
        phase: int | None = None,
    ) -> FetchedPayload[dict[str, Any]]:
        _require_id("league ID", league_id, MAX_PUBLIC_ID)
        _require_id("standings page", page_standings, MAX_PAGE)
        query: list[tuple[str, int]] = [("page_standings", page_standings)]
        if page_new_entries is not None:
            _require_id("new entries page", page_new_entries, MAX_PAGE)
            query.append(("page_new_entries", page_new_entries))
        if phase is not None:
            _require_id("phase", phase, MAX_PHASE)
            query.append(("phase", phase))
        return await self._fetch_json_object(
            f"leagues-classic/{league_id}/standings/?{urlencode(query)}",
            size_limit=DEFAULT_LIMIT_BYTES,
        )

    async def _fetch_json_object(
        self,
        path: str,
        *,
        size_limit: int,
    ) -> FetchedPayload[dict[str, Any]]:
        payload, snapshot = await self._fetch_json(path, size_limit=size_limit)
        if not isinstance(payload, Mapping) or not all(isinstance(key, str) for key in payload):
            raise FplContractError("FPL response must be a JSON object")
        return FetchedPayload(
            payload=cast(dict[str, Any], dict(payload)),
            snapshot=snapshot,
        )

    async def _fetch_json_array(
        self,
        path: str,
        *,
        size_limit: int,
    ) -> FetchedPayload[list[dict[str, Any]]]:
        payload, snapshot = await self._fetch_json(path, size_limit=size_limit)
        if not isinstance(payload, list) or not all(
            isinstance(item, Mapping) and all(isinstance(key, str) for key in item)
            for item in payload
        ):
            raise FplContractError("FPL response must be an array of JSON objects")
        return FetchedPayload(
            payload=[cast(dict[str, Any], dict(item)) for item in payload],
            snapshot=snapshot,
        )

    async def _fetch_json(
        self,
        path: str,
        *,
        size_limit: int,
    ) -> tuple[object, SourceSnapshot]:
        upstream_reference = f"{FPL_API_BASE}{path}"
        response = await self._request_with_retries(upstream_reference)
        try:
            response.raise_for_status()

            declared_length = _parse_content_length(response.headers.get("Content-Length"))
            if declared_length is not None and declared_length > size_limit:
                raise FplContractError("FPL response exceeded the allowed size")
            content_type = response.headers.get("Content-Type", "")
            if "application/json" not in content_type.lower():
                raise FplContractError("FPL response was not JSON")
            content = await _read_bounded_content(response, size_limit)
            payload = cast(object, json.loads(content))
        finally:
            await response.aclose()

        fetched_at = self._clock()
        if not is_utc(fetched_at):
            raise FplContractError("adapter clock must return an aware UTC timestamp")

        snapshot = SourceSnapshot(
            source="fpl",
            fetched_at=fetched_at,
            data_available_at=fetched_at,
            content_hash=f"sha256:{hashlib.sha256(content).hexdigest()}",
            upstream_reference=upstream_reference,
        )
        return payload, snapshot

    async def _request_with_retries(self, upstream_reference: str) -> httpx.Response:
        if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            raise FplUpstreamDown(
                f"stopped asking after {self._consecutive_failures} consecutive "
                "upstream failures; the endpoint is down, not slow"
            )
        transport_errors: list[httpx.TransportError] = []
        for attempt in range(MAX_ATTEMPTS):
            try:
                request = self._http.build_request(
                    "GET",
                    upstream_reference,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "User-Agent": FPL_USER_AGENT,
                    },
                    timeout=client_timeout(timeouts.FPL_API),
                )
                response = await self._http.send(request, stream=True)
            except httpx.TransportError as error:
                transport_errors.append(error)
                if attempt == MAX_ATTEMPTS - 1:
                    self._consecutive_failures += 1
                    raise _joined_transport_error(transport_errors) from error
                await self._sleep(_retry_delay(None, attempt, self._random))
                continue

            if response.status_code not in RETRYABLE_STATUSES or attempt == MAX_ATTEMPTS - 1:
                if response.status_code in RETRYABLE_STATUSES:
                    self._consecutive_failures += 1
                else:
                    self._consecutive_failures = 0
                return response
            await response.aclose()
            await self._sleep(
                _retry_delay(response.headers.get("Retry-After"), attempt, self._random)
            )

        self._consecutive_failures += 1
        if transport_errors:
            raise _joined_transport_error(transport_errors)
        raise RuntimeError("FPL retry loop ended without a response")


def _parse_content_length(raw_value: str | None) -> int | None:
    if raw_value is None or not raw_value.isdigit():
        return None
    return int(raw_value)


async def _read_bounded_content(response: httpx.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise FplContractError("FPL response exceeded the allowed size")
        chunks.append(chunk)
    return b"".join(chunks)


def _joined_transport_error(errors: list[httpx.TransportError]) -> httpx.TransportError:
    """Keep every attempt's failure, not only the last.

    Three different failures - a DNS miss, a reset, a timeout - say something a
    single reset does not, and the first two used to be discarded.
    """
    if len(errors) == 1:
        return errors[0]
    summary = "; ".join(f"{type(error).__name__}: {error}" for error in errors)
    joined = httpx.TransportError(f"{len(errors)} attempts failed: {summary}")
    joined.__cause__ = errors[-1]
    return joined


def _retry_delay(
    retry_after: str | None,
    attempt: int,
    random: Callable[[], float],
) -> float:
    if retry_after is not None and retry_after.isdigit():
        return min(float(retry_after), MAX_RETRY_AFTER_SECONDS)
    exponential: float = 0.5 * float(2**attempt)
    jitter: float = 0.8 + float(random()) * 0.4
    return min(exponential * jitter, MAX_BACKOFF_SECONDS)


def _require_id(label: str, value: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise FplContractError(f"{label} is outside the supported range")


def _required_raw_field(payload: Mapping[str, Any], key: str) -> Any:
    if key not in payload:
        raise FplContractError(f"FPL entry is missing required field: {key}")
    return payload[key]


__all__ = [
    "FplClient",
    "FplContractError",
    "FplPicksUnavailable",
    "FplUpstreamDown",
    "normalize_entry",
]
