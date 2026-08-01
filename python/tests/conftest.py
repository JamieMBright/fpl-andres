"""Shared test configuration.

Audit items #161, #162 and #165.

**#161** Nothing pinned `PYTHONHASHSEED`, so set iteration order varied between
runs. Most code here sorts before it depends on order, but "most" is the problem:
a test that passes on one hash seed and fails on another is a test that fails in
CI once a fortnight and cannot be reproduced locally.

**#165** The `slow` marker existed and nothing used it. A test that quietly
grows to several seconds is how a suite becomes something people skip, so this
reports the ones that have crossed the line rather than waiting for someone to
notice the total.
"""

from __future__ import annotations

import random
import sys
from collections.abc import Iterator

import pytest

# Every test that needs randomness gets this. Changing it is a deliberate act
# with a diff, not an accident of import order.
SESSION_SEED = 20260801

# A test slower than this must say so with @pytest.mark.slow.
SLOW_THRESHOLD_SECONDS = 1.0


def pytest_report_header() -> list[str]:
    """State the seeds in the run header, so a failure log carries them."""
    return [
        f"session seed: {SESSION_SEED}",
        f"PYTHONHASHSEED: {(sys.flags.hash_randomization and 'randomised') or 'fixed'}",
    ]


@pytest.fixture(autouse=True)
def _deterministic_random() -> Iterator[None]:
    """Reseed the global RNG before every test.

    Autouse and per-test rather than per-session: a session-level seed makes
    each test depend on how many random numbers the tests before it consumed,
    so running one test alone gives a different result from running the suite.
    """
    state = random.getstate()
    random.seed(SESSION_SEED)
    yield
    random.setstate(state)


@pytest.fixture
def seed() -> int:
    """The seed to pass to anything that takes one explicitly."""
    return SESSION_SEED


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
) -> None:
    """Name unmarked slow tests. #165."""
    unmarked: list[tuple[float, str]] = []
    for reports in terminalreporter.stats.values():
        for report in reports:
            if getattr(report, "when", None) != "call":
                continue
            if report.duration <= SLOW_THRESHOLD_SECONDS:
                continue
            if any(marker == "slow" for marker in getattr(report, "keywords", ())):
                continue
            unmarked.append((report.duration, report.nodeid))

    if not unmarked:
        return
    terminalreporter.write_sep("-", "slow tests without @pytest.mark.slow")
    for duration, nodeid in sorted(unmarked, reverse=True):
        terminalreporter.write_line(f"  {duration:6.2f}s  {nodeid}")
