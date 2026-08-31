"""Which gameweeks can still be planned, and how many the season is into.

FPL publishes `finished` on an event only once the bonus for every match in it
is confirmed, which is hours after the last whistle and days after the deadline
that locked the squad. Anchoring the site on that flag meant a gameweek already
played was still being presented as the one to plan for: transfers could not be
made for it, its matches were over, and every page still pointed at it.

The deadline is the honest boundary. Once it passes, a manager can do nothing
about that gameweek, so the next one he can act on is the first whose deadline
is still ahead. That is what the publishers now solve for.

`finished` keeps its job elsewhere and is not replaced here: a settled round is
what the projection corpus is built from, and that must wait for confirmed
bonus. This module is about what to plan, not what to learn from.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

__all__ = ["plannable_events"]


def _deadline(event: Mapping[str, Any]) -> datetime | None:
    raw = event.get("deadline_time")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def plannable_events(
    events: Sequence[Mapping[str, Any]],
    now: datetime,
) -> dict[int, Mapping[str, Any]]:
    """The gameweeks a manager can still act on, keyed by event id.

    An event without a readable deadline is dropped rather than guessed at: a
    plan built on an invented deadline is a plan for a gameweek that may already
    be locked.
    """
    if now.tzinfo is None:
        raise ValueError("the current time must carry a timezone")
    plannable: dict[int, Mapping[str, Any]] = {}
    for event in events:
        identifier = event.get("id")
        deadline = _deadline(event)
        if not isinstance(identifier, int) or deadline is None:
            continue
        if deadline > now:
            plannable[identifier] = event
    return plannable
