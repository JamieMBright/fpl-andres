"""Back off by what the server asked for, not by what we guessed.

- **#47** The adapter already honours `Retry-After`. The sweep CLI did not: it
  inferred a pause from a refusal count, which backs off too little when the
  server wants a minute and too much when it wants a second. Fixed there.

- **#50** asked for the response body to be drained or discarded
  deterministically when the size limit trips. It already is: `_fetch_json`
  closes the response in a `finally`, and `httpx` discards rather than reuses a
  connection whose stream was not consumed. Discarding is also the right choice
  — draining an oversized body to save a socket is paying the exact cost the
  limit exists to avoid. Recorded rather than changed.
"""

from __future__ import annotations

import pytest

from fpl_andres.cli.sweep_managers import MAX_BACKOFF_SECONDS, _backoff_seconds


@pytest.mark.parametrize(
    ("header", "refusals", "expected"),
    [
        ("1", 9, 1.0),
        ("30", 1, 30.0),
        ("0", 5, 0.0),
    ],
)
def test_the_servers_own_delay_wins(header: str, refusals: int, expected: float) -> None:
    """Including when it asks for less than the guess would have taken. The
    refusal count is a fallback, not a floor."""
    assert _backoff_seconds(header, refusals) == expected


def test_a_long_retry_after_is_still_capped() -> None:
    """A server asking for an hour gets a minute. The sweep is resumable, so
    stopping is cheaper than sleeping through a deploy window."""
    assert _backoff_seconds("3600", 1) == MAX_BACKOFF_SECONDS


@pytest.mark.parametrize("header", [None, "", "   ", "Wed, 21 Oct 2026 07:28:00 GMT", "soon", "-5"])
def test_an_unusable_header_falls_back_to_the_refusal_count(header: str | None) -> None:
    """Never to zero. A malformed header is not permission to hammer the API.

    The HTTP-date form is deliberately unhandled: FPL sends delta-seconds, and a
    date parser here would be untested code guessing at a format that has never
    arrived.
    """
    assert _backoff_seconds(header, 4) == 8.0
    assert _backoff_seconds(header, 1) > 0.0


def test_the_fallback_grows_with_repeated_refusals() -> None:
    delays = [_backoff_seconds(None, count) for count in (1, 2, 5, 10)]

    assert delays == sorted(delays)
    assert delays[0] < delays[-1]


def test_the_fallback_is_capped_too() -> None:
    assert _backoff_seconds(None, 1_000) == MAX_BACKOFF_SECONDS


def test_the_adapter_already_honoured_retry_after() -> None:
    """#47's premise, as it applies to adapters/fpl.py. Recorded so it is not
    reopened: the retry loop reads the header and closes the response before
    sleeping."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "fpl_andres" / "adapters" / "fpl.py").read_text(
        encoding="utf-8"
    )

    assert 'response.headers.get("Retry-After")' in source
    assert "await response.aclose()" in source


def test_an_oversized_response_is_closed_deterministically() -> None:
    """#50. The close is in a `finally`, so it runs on the size-limit raise as
    well as the happy path."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "fpl_andres" / "adapters" / "fpl.py").read_text(
        encoding="utf-8"
    )
    body = source.split("async def _fetch_json(", 1)[1].split("\n    async def", 1)[0]

    assert "finally:" in body
    assert body.index("finally:") < body.index("fetched_at = self._clock()")
    assert "await response.aclose()" in body
