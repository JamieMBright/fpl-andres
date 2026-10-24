"""Capturing the published crowd signal, and refusing to mislabel a capture."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from fpl_andres.cli.capture_crowd import _current_event, _record_snapshot, _rows, season_from

SNAPSHOT_ID = "00000000-0000-0000-0000-000000000001"


def test_snapshot_storage_path_matches_its_source_and_content_hash() -> None:
    client = Mock()
    client.insert.return_value = [{"id": SNAPSHOT_ID}]
    captured = datetime(2026, 10, 24, tzinfo=UTC)
    snapshot = SimpleNamespace(
        source="fpl",
        fetched_at=captured,
        data_available_at=captured,
        content_hash=f"sha256:{'a' * 64}",
        upstream_reference="https://fantasy.premierleague.com/api/bootstrap-static/",
    )

    assert _record_snapshot(client, snapshot) == SNAPSHOT_ID
    table, rows = client.insert.call_args.args
    assert table == "source_snapshots"
    assert rows[0]["storage_path"] == f"fpl/{'a' * 64}"
    assert rows[0]["content_hash"] == snapshot.content_hash
    assert rows[0]["data_available_at"] == captured.isoformat()


def bootstrap(
    events: list[dict[str, Any]] | None = None,
    elements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "events": events if events is not None else [],
        "elements": elements if elements is not None else [],
        "total_players": 11_000_000,
    }


def test_the_season_is_derived_from_the_opening_deadline() -> None:
    payload = bootstrap(
        events=[
            {"id": 1, "deadline_time": "2026-08-14T17:30:00Z"},
            {"id": 20, "deadline_time": "2027-01-02T11:30:00Z"},
        ]
    )

    assert season_from(payload) == "2026-27"


def test_a_january_only_calendar_still_lands_in_the_right_season() -> None:
    payload = bootstrap(events=[{"id": 20, "deadline_time": "2027-01-02T11:30:00Z"}])

    # A January deadline belongs to the season that began the previous August.
    assert season_from(payload) == "2026-27"


def test_no_deadlines_means_no_season_rather_than_a_guess() -> None:
    assert season_from(bootstrap()) is None


def test_the_current_event_is_preferred_over_the_next_one() -> None:
    payload = bootstrap(
        events=[
            {"id": 7, "is_current": True},
            {"id": 8, "is_next": True},
        ]
    )

    assert _current_event(payload) == 7


def test_before_the_season_starts_the_next_event_is_used() -> None:
    payload = bootstrap(events=[{"id": 1, "is_next": True}])

    assert _current_event(payload) == 1


def test_an_unstarted_calendar_yields_no_event_rather_than_zero() -> None:
    assert _current_event(bootstrap(events=[{"id": 1}])) is None


def test_ownership_rows_carry_the_denominator_behind_any_share() -> None:
    from datetime import UTC, datetime

    payload = bootstrap(
        elements=[
            {
                "id": 5,
                "selected_by_percent": "42.7",
                "transfers_in_event": 1000,
                "transfers_out_event": 250,
            }
        ]
    )

    rows = _rows(
        payload,
        season="2026-27",
        event=3,
        captured_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
        snapshot_id=SNAPSHOT_ID,
    )

    assert rows[0]["selected_by_percent"] == 42.7
    assert rows[0]["total_managers"] == 11_000_000
    assert rows[0]["source_snapshot_id"] == SNAPSHOT_ID
    assert rows[0]["event"] == 3
