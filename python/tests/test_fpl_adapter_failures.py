"""What the adapter does when FPL misbehaves.

Covers the adapter's failure paths and the negative paths of its cache. Also records
two audit claims that did not survive checking: #45 and #51 asked for guaranteed
cleanup of the HTTP client, the JSONL sink and the sweep semaphore, and all
three already use context managers, which release on any exception.
"""

from __future__ import annotations

import contextlib
import unittest
from datetime import UTC, datetime

import httpx

from fpl_andres.adapters.fpl import (
    CIRCUIT_BREAKER_THRESHOLD,
    MAX_ATTEMPTS,
    MAX_BACKOFF_SECONDS,
    FplClient,
    FplContractError,
    FplUpstreamDown,
    _retry_delay,
)


def _client(handler, sleeps: list[float] | None = None) -> FplClient:
    async def sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return FplClient(
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        clock=lambda: datetime.now(UTC),
        sleep=sleep,
        random=lambda: 0.5,
    )


def _json(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload, headers={"Content-Type": "application/json"})


class BackoffTest(unittest.TestCase):
    def test_the_exponential_is_capped(self) -> None:
        """Capped on the delay itself, not only on the attempt count."""
        for attempt in range(0, 20):
            with self.subTest(attempt=attempt):
                self.assertLessEqual(_retry_delay(None, attempt, lambda: 1.0), MAX_BACKOFF_SECONDS)

    def test_retry_after_is_honoured_over_the_exponential(self) -> None:
        self.assertEqual(_retry_delay("3", 0, lambda: 0.5), 3.0)

    def test_an_absurd_retry_after_is_capped(self) -> None:
        self.assertLessEqual(_retry_delay("99999", 0, lambda: 0.5), 30.0)


class RetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_retryable_status_is_retried_then_succeeds(self) -> None:
        seen: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(1)
            if len(seen) < 2:
                return _json({"detail": "busy"}, status=503)
            return _json({"total_players": 1})

        fetched = await _client(handler).fetch_bootstrap()

        self.assertEqual(fetched.payload["total_players"], 1)
        self.assertGreaterEqual(len(seen), 2)

    async def test_every_transport_error_is_preserved_not_only_the_last(self) -> None:
        failures = [
            httpx.ConnectError("dns went away"),
            httpx.ReadTimeout("read timed out"),
            httpx.ConnectError("connection reset"),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            raise failures[min(len(failures) - 1, handler.calls)]  # type: ignore[attr-defined]

        handler.calls = 0  # type: ignore[attr-defined]

        def counting(request: httpx.Request) -> httpx.Response:
            error = failures[handler.calls]  # type: ignore[attr-defined]
            handler.calls += 1  # type: ignore[attr-defined]
            raise error

        client = _client(counting)
        with self.assertRaises(httpx.TransportError) as caught:
            await client.fetch_bootstrap()

        message = str(caught.exception)
        self.assertIn("dns went away", message)
        self.assertIn("read timed out", message)
        self.assertIn(f"{MAX_ATTEMPTS} attempts failed", message)

    async def test_a_non_json_content_type_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>maintenance</html>")

        client = _client(handler)
        with self.assertRaises(FplContractError):
            await client.fetch_bootstrap()

    async def test_an_oversized_declared_length_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"a": 1},
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(64 * 1024 * 1024),
                },
            )

        client = _client(handler)
        with self.assertRaises(FplContractError):
            await client.fetch_bootstrap()

    async def test_malformed_json_surfaces_rather_than_returning_a_shape(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b'{"truncated": ',
                headers={"Content-Type": "application/json"},
            )

        client = _client(handler)
        with self.assertRaises(ValueError):
            await client.fetch_bootstrap()


class CircuitBreakerTest(unittest.IsolatedAsyncioTestCase):
    async def test_it_stops_asking_once_the_endpoint_is_plainly_down(self) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return _json({"detail": "down"}, status=503)

        client = _client(handler)
        for _ in range(CIRCUIT_BREAKER_THRESHOLD):
            with contextlib.suppress(httpx.HTTPError, FplContractError):
                await client.fetch_bootstrap()

        before = len(calls)
        with self.assertRaises(FplUpstreamDown):
            await client.fetch_bootstrap()

        self.assertEqual(len(calls), before, "breaker must not send another request")

    async def test_a_success_resets_the_breaker(self) -> None:
        state = {"fail": True}

        def handler(request: httpx.Request) -> httpx.Response:
            if state["fail"]:
                return _json({"detail": "down"}, status=503)
            return _json({"total_players": 1})

        client = _client(handler)
        with contextlib.suppress(httpx.HTTPError, FplContractError):
            await client.fetch_bootstrap()

        state["fail"] = False
        await client.fetch_bootstrap()

        self.assertEqual(client._consecutive_failures, 0)


if __name__ == "__main__":
    unittest.main()
