"""Argparse types that refuse a value before the work starts.

Every numeric CLI argument was `type=int` or `type=float`, so
`--rate 0` reached the throttle and divided by zero, `--concurrency 0` produced a
semaphore nobody could acquire, and `--gameweek 99` ran a whole ingest before
failing on a database check constraint.

Argparse reports these as usage errors with exit status 2, which is what a wrong
flag deserves: a message naming the flag, not a traceback from four layers down.
"""

from __future__ import annotations

import argparse
import math
import re

__all__ = [
    "MAX_EVENT",
    "event_id",
    "positive_float",
    "positive_int",
    "season",
]

# 2019/20 ran to gameweek 47 after the pandemic restart. Most seasons run to 38.
MAX_EVENT = 47

_SEASON = re.compile(r"^20[0-9]{2}-[0-9]{2}$")


def positive_int(raw: str) -> int:
    value = _as_int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def positive_float(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a number") from error
    # Before the sign check: nan fails `> 0` and would otherwise be reported as
    # not positive, which is true but not the useful thing to say about it.
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"must be finite, got {value}")
    if not value > 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0, got {value}")
    return value


def event_id(raw: str) -> int:
    value = _as_int(raw)
    if not 1 <= value <= MAX_EVENT:
        raise argparse.ArgumentTypeError(f"must be a gameweek 1..{MAX_EVENT}, got {value}")
    return value


def season(raw: str) -> str:
    if not _SEASON.match(raw):
        raise argparse.ArgumentTypeError(f"must look like 2025-26, got {raw!r}")
    start, end = raw.split("-")
    if int(end) != (int(start) + 1) % 100:
        raise argparse.ArgumentTypeError(f"{raw!r} does not name consecutive years")
    return raw


def _as_int(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a whole number") from error
