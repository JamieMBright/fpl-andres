"""Upstream failures as data, not as one-off mocks.

Retry and backoff were covered by handlers written inline in
each test, so each one exercised the shape its author thought of. A 429 with a
`Retry-After`, a 503 with an HTML body, a truncated response and a connection
reset are all "the upstream failed", and the code paths differ.

These are the responses, in one place, so a new retry test starts from the full
set rather than from whichever one was copied last.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

__all__ = ["UPSTREAM_FAILURES", "UpstreamFailure", "responder"]


@dataclass(frozen=True)
class UpstreamFailure:
    """One way a request can fail, and what a caller should do about it."""

    name: str
    status: int | None
    body: bytes
    headers: dict[str, str]
    retryable: bool
    # What the failure looks like from the outside. A gateway returning HTML on a
    # 503 is not the same problem as an API returning JSON on a 503, and only one
    # of them means the API is up.
    note: str

    def response(self, request: httpx.Request) -> httpx.Response:
        if self.status is None:
            raise httpx.ConnectError(self.note, request=request)
        return httpx.Response(self.status, content=self.body, headers=self.headers, request=request)


_JSON = {"Content-Type": "application/json"}
_HTML = {"Content-Type": "text/html"}


UPSTREAM_FAILURES: tuple[UpstreamFailure, ...] = (
    UpstreamFailure(
        name="rate_limited_with_delay",
        status=429,
        body=b'{"detail":"Request was throttled."}',
        headers={**_JSON, "Retry-After": "30"},
        retryable=True,
        note="the server said how long to wait; guessing instead is the bug in #47",
    ),
    UpstreamFailure(
        name="rate_limited_without_delay",
        status=429,
        body=b"",
        headers=dict(_JSON),
        retryable=True,
        note="no Retry-After, so the caller must fall back to its own backoff",
    ),
    UpstreamFailure(
        name="rate_limited_with_http_date",
        status=429,
        body=b"",
        headers={**_JSON, "Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
        retryable=True,
        note="the other legal Retry-After form; unparsed here, so it must fall back",
    ),
    UpstreamFailure(
        name="server_error_json",
        status=500,
        body=b'{"detail":"Internal server error."}',
        headers=dict(_JSON),
        retryable=True,
        note="the API is up and something inside it broke",
    ),
    UpstreamFailure(
        name="gateway_html",
        status=503,
        body=b"<html><head><title>503 Service Unavailable</title></head></html>",
        headers=dict(_HTML),
        retryable=True,
        note="a CDN answered, not the API; the body is not JSON and never will be",
    ),
    UpstreamFailure(
        name="bad_gateway",
        status=502,
        body=b"<html>502 Bad Gateway</html>",
        headers=dict(_HTML),
        retryable=True,
        note="upstream of the upstream",
    ),
    UpstreamFailure(
        name="truncated_json",
        status=200,
        body=b'{"elements":[{"id":1,"web_name":"Sa',
        headers=dict(_JSON),
        retryable=False,
        note="a 200 that cannot be parsed; retrying gets the same bytes",
    ),
    UpstreamFailure(
        name="html_on_success",
        status=200,
        body=b"<html><body>Access denied</body></html>",
        headers=dict(_HTML),
        retryable=False,
        note="a 200 carrying an error page; the status line lies",
    ),
    UpstreamFailure(
        name="empty_body",
        status=200,
        body=b"",
        headers=dict(_JSON),
        retryable=False,
        note="nothing at all, with a content type promising JSON",
    ),
    UpstreamFailure(
        name="not_found",
        status=404,
        body=b'{"detail":"Not found."}',
        headers=dict(_JSON),
        retryable=False,
        note="the entry does not exist; retrying is asking the same question again",
    ),
    UpstreamFailure(
        name="connection_reset",
        status=None,
        body=b"",
        headers={},
        retryable=True,
        note="no response at all",
    ),
)


def responder(failure: UpstreamFailure, *, succeed_after: int = 0):
    """An httpx handler that fails, then succeeds once it has failed enough.

    `succeed_after=0` never succeeds, which is what a circuit-breaker test wants.
    """
    state = {"calls": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if succeed_after and state["calls"] > succeed_after:
            return httpx.Response(200, json={"elements": []}, headers=dict(_JSON), request=request)
        return failure.response(request)

    handle.calls = state  # type: ignore[attr-defined]
    return handle
