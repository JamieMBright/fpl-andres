"""A gameweek stops being plannable at its deadline, not when FPL settles it."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fpl_andres.season_position import plannable_events

NOW = datetime(2026, 8, 31, 21, 0, tzinfo=UTC)

EVENTS = [
    {"id": 1, "deadline_time": "2026-08-21T17:30:00Z", "finished": True},
    # Played out over the four days before NOW, but FPL still confirms bonus.
    {"id": 2, "deadline_time": "2026-08-28T17:30:00Z", "finished": False},
    {"id": 3, "deadline_time": "2026-09-04T17:30:00Z", "finished": False},
    {"id": 4, "deadline_time": "2026-09-12T12:30:00Z", "finished": False},
]


def test_a_gameweek_whose_deadline_has_passed_cannot_be_planned() -> None:
    """Nothing a manager does now reaches gameweek 2, whatever `finished` says."""
    assert sorted(plannable_events(EVENTS, NOW)) == [3, 4]


def test_the_deadline_itself_closes_the_gameweek() -> None:
    at_the_deadline = datetime(2026, 9, 4, 17, 30, tzinfo=UTC)

    assert sorted(plannable_events(EVENTS, at_the_deadline)) == [4]


def test_an_event_without_a_readable_deadline_is_dropped() -> None:
    events = [*EVENTS, {"id": 5}, {"id": 6, "deadline_time": "not a time"}]

    assert sorted(plannable_events(events, NOW)) == [3, 4]


def test_a_naive_now_is_refused() -> None:
    with pytest.raises(ValueError):
        plannable_events(EVENTS, datetime(2026, 8, 31, 21, 0))
