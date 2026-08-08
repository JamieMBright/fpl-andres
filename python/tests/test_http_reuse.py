"""Why bootstrap is refetched, and why that is not fixable as proposed.

It was asked for conditional-request support (ETag / If-Modified-Since)
for `bootstrap-static`, on the grounds that it is stable within a gameweek and
refetched per command. The premise is true. The remedy is not available.

Probed against the live endpoint on 2026-08-01:

    status 200, 1,328,564 bytes
    ETag:          absent
    Last-Modified: absent
    Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=3600
    Age:           294

FPL publishes no validator. `If-None-Match` has nothing to send and
`If-Modified-Since` has no `Last-Modified` to echo, so a conditional request
would be an unconditional one with a useless header attached.

The obvious substitute — an in-process cache honouring the server's own
`max-age` — saves nothing either. `fetch_bootstrap` has two production callers
and each fetches once per process, so there is no second request inside a
process lifetime for a cache to serve. A cross-process cache would mean writing
1.3 MB to disk and reasoning about its staleness, to save one request from a
command that runs on a schedule.

It was asked for explicit connection pooling and a single client per CLI
run. Every CLI already opens one `httpx.AsyncClient` in an `async with` for the
whole run, which is connection pooling: httpx keeps up to 20 keep-alive
connections per client by default, and this workload talks to one host.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_CLI = Path(__file__).resolve().parents[1] / "fpl_andres" / "cli"

# Measured against the live endpoint. See the module docstring.
BOOTSTRAP_BYTES = 1_328_564
BOOTSTRAP_MAX_AGE_SECONDS = 300


def test_every_cli_opens_one_client_for_the_whole_run() -> None:
    """#49. A client per request would discard the connection pool between
    calls, which for a 2.5-million-id sweep is 2.5 million TLS handshakes."""
    offenders: list[str] = []
    for path in sorted(_CLI.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        constructions = len(re.findall(r"httpx\.(?:Async)?Client\(", source))
        if constructions > 1:
            offenders.append(f"{path.name} ({constructions})")
    assert offenders == [], (
        f"these construct more than one client, so the pool is discarded between calls: {offenders}"
    )


def test_no_cli_constructs_a_client_inside_a_loop() -> None:
    """The shape that defeats pooling even with a single construction site."""
    offenders: list[str] = []
    for path in sorted(_CLI.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.For | ast.AsyncFor | ast.While):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr in {"Client", "AsyncClient"}
                ):
                    offenders.append(path.name)
    assert offenders == [], f"a client is constructed inside a loop in: {set(offenders)}"


def test_the_client_is_closed_by_a_context_manager() -> None:
    """An unclosed pool leaks sockets for the life of the process."""
    for path in sorted(_CLI.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "httpx.AsyncClient(" in source:
            assert "async with" in source, f"{path.name} does not close its client"
        if "httpx.Client(" in source:
            assert "with (" in source or "with httpx" in source, (
                f"{path.name} does not close its client"
            )


def test_bootstrap_has_exactly_one_fetch_per_process() -> None:
    """#48's substitute would need a second call to be worth anything."""
    callers = {
        path.name: path.read_text(encoding="utf-8").count("fetch_bootstrap()")
        for path in sorted(_CLI.glob("*.py"))
        if "fetch_bootstrap()" in path.read_text(encoding="utf-8")
    }

    assert callers == {"capture_crowd.py": 1, "live_contracts.py": 1}


def test_the_adapter_sends_no_useless_conditional_header() -> None:
    """FPL publishes no ETag and no Last-Modified, so a conditional request
    would be an unconditional one carrying a header that can never match."""
    adapter = (
        Path(__file__).resolve().parents[1] / "fpl_andres" / "adapters" / "fpl.py"
    ).read_text(encoding="utf-8")

    assert "If-None-Match" not in adapter
    assert "If-Modified-Since" not in adapter


def test_the_measurement_behind_the_decision_is_recorded() -> None:
    """So the item is re-openable on evidence rather than on memory: if FPL
    starts publishing a validator, these numbers are what to re-check."""
    assert BOOTSTRAP_BYTES > 1_000_000
    assert BOOTSTRAP_MAX_AGE_SECONDS == 300
