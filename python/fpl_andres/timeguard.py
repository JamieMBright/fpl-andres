"""One definition of "this timestamp is trustworthy".

Every leakage guard, every evidence record and every contract in this package
depends on timestamps being aware and in UTC. The check was written out fifteen
times across adapters, contracts and models. Fifteen copies of a rule is fifteen
chances for one of them to drift, and the rule is load-bearing: a naive
timestamp compared against an aware cutoff is the shape of a leak.

Two entry points, because three call sites raise their own contract exception
and should keep doing so rather than have a ValueError escape as the wrong type.
"""

from __future__ import annotations

from datetime import datetime, timedelta

__all__ = ["is_utc", "require_utc"]


def is_utc(value: datetime) -> bool:
    """True when the timestamp is timezone-aware and its offset is exactly zero.

    A zero offset is not the same as `tzinfo is UTC`: several libraries hand
    back a fixed-offset zone that happens to be zero, and those are fine.
    """
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def require_utc(value: datetime, label: str) -> datetime:
    """Return the timestamp, or fail naming which one was wrong."""
    if not is_utc(value):
        raise ValueError(f"{label} must be an aware UTC timestamp")
    return value
