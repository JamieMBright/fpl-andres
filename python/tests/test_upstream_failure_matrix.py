"""Every upstream failure, driven through the real adapter.

Retry and backoff were covered by handlers written inline in
each test, so each exercised the shape its author thought of. Driving the whole
catalogue through one code path is what turns "we handle failures" into a list of
the failures actually handled.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from tests.upstream_failures import UPSTREAM_FAILURES, UpstreamFailure, responder

from fpl_andres.adapters.fpl import (
    CIRCUIT_BREAKER_THRESHOLD,
    FplClient,
    FplContractError,
    FplUpstreamDown,
)

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _client(handler, *, sleeps: list[float] | None = None) -> FplClient:
    async def sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return FplClient(
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        clock=lambda: NOW,
        sleep=sleep,
    )


def _named(*names: str) -> list[UpstreamFailure]:
    chosen = [failure for failure in UPSTREAM_FAILURES if failure.name in names]
    assert len(chosen) == len(names), "a failure name in this test no longer exists"
    return chosen


def test_the_catalogue_covers_both_outcomes() -> None:
    """A catalogue of only-retryable failures would prove half the behaviour."""
    assert any(failure.retryable for failure in UPSTREAM_FAILURES)
    assert any(not failure.retryable for failure in UPSTREAM_FAILURES)
    assert len({failure.name for failure in UPSTREAM_FAILURES}) == len(UPSTREAM_FAILURES)


@pytest.mark.parametrize("failure", UPSTREAM_FAILURES, ids=lambda failure: failure.name)
async def test_no_failure_ever_returns_a_payload(failure: UpstreamFailure) -> None:
    """The property that matters more than which exception comes out: a failed
    fetch must never look like a successful one."""
    client = _client(responder(failure), sleeps=[])

    with pytest.raises(Exception) as caught:
        await client.fetch_bootstrap()

    assert not isinstance(caught.value, AssertionError)


@pytest.mark.parametrize(
    "failure",
    [f for f in UPSTREAM_FAILURES if f.retryable and f.status is not None],
    ids=lambda failure: failure.name,
)
async def test_a_retryable_failure_is_retried(failure: UpstreamFailure) -> None:
    handler = responder(failure, succeed_after=1)
    client = _client(handler, sleeps=[])

    await client.fetch_bootstrap()

    assert handler.calls["calls"] == 2, "the first failure should have been retried"


@pytest.mark.parametrize(
    "failure",
    [f for f in UPSTREAM_FAILURES if not f.retryable and f.status == 200],
    ids=lambda failure: failure.name,
)
async def test_an_unparseable_two_hundred_is_not_retried(
    failure: UpstreamFailure,
) -> None:
    """Retrying gets the same bytes. A 200 the parser cannot read is a contract
    break, and the circuit breaker exists for outages rather than for those."""
    handler = responder(failure, succeed_after=1)
    client = _client(handler, sleeps=[])

    with pytest.raises(FplContractError):
        await client.fetch_bootstrap()

    assert handler.calls["calls"] == 1


async def test_a_rate_limit_with_a_delay_waits_at_least_that_long() -> None:
    """#47's rule, exercised through the adapter rather than asserted on a
    helper."""
    sleeps: list[float] = []
    failure = _named("rate_limited_with_delay")[0]
    client = _client(responder(failure, succeed_after=1), sleeps=sleeps)

    await client.fetch_bootstrap()

    assert sleeps, "no backoff happened"
    assert max(sleeps) >= 30.0


async def test_a_rate_limit_without_a_delay_still_backs_off() -> None:
    sleeps: list[float] = []
    failure = _named("rate_limited_without_delay")[0]
    client = _client(responder(failure, succeed_after=1), sleeps=sleeps)

    await client.fetch_bootstrap()

    assert sleeps and all(delay > 0 for delay in sleeps)


async def test_an_http_date_retry_after_falls_back_rather_than_crashing() -> None:
    """The other legal form. Unparsed, so it must take the fallback path — and
    must not take zero."""
    sleeps: list[float] = []
    failure = _named("rate_limited_with_http_date")[0]
    client = _client(responder(failure, succeed_after=1), sleeps=sleeps)

    await client.fetch_bootstrap()

    assert sleeps and all(delay > 0 for delay in sleeps)


async def test_a_persistent_outage_trips_the_circuit_breaker() -> None:
    """Past the threshold the adapter stops asking. An endpoint that has failed
    a dozen times consecutively is down, not slow."""
    failure = _named("server_error_json")[0]
    handler = responder(failure)
    client = _client(handler, sleeps=[])

    for _ in range(CIRCUIT_BREAKER_THRESHOLD):
        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch_bootstrap()
    calls_before = handler.calls["calls"]

    with pytest.raises(FplUpstreamDown):
        await client.fetch_bootstrap()

    # The point of the breaker: it stops asking, rather than failing faster.
    assert handler.calls["calls"] == calls_before


async def test_a_gateway_html_error_is_not_reported_as_bad_json() -> None:
    """A CDN answering instead of the API is a different diagnosis, and the
    content type is what distinguishes them."""
    failure = _named("gateway_html")[0]
    client = _client(responder(failure), sleeps=[])

    with pytest.raises(Exception) as caught:
        await client.fetch_bootstrap()

    assert "503" in str(caught.value) or "not JSON" in str(caught.value)


@pytest.mark.parametrize("failure", UPSTREAM_FAILURES, ids=lambda failure: failure.name)
async def test_no_failure_message_carries_the_response_body(
    failure: UpstreamFailure,
) -> None:
    """An upstream body can contain anything, including a quoted request header.
    That is how a key reached the logs in #73.

    Asserts on markup and on body-only phrases. "Bad Gateway" is excluded
    deliberately: it is also HTTP's own reason phrase for 502, so httpx puts it
    in a status error message without ever reading the body.
    """
    client = _client(responder(failure), sleeps=[])

    with pytest.raises(Exception) as caught:
        await client.fetch_bootstrap()

    message = str(caught.value)
    for fragment in ("<html>", "<head>", "<body>", "Access denied", "throttled"):
        assert fragment not in message
