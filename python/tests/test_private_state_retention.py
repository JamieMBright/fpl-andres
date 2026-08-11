from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_andres.cli.prune_private_state import prune_private_state


class RecordingDeleteClient:
    def __init__(self, counts: list[int] | None = None) -> None:
        self.deletes: list[tuple[str, dict[str, str]]] = []
        self._counts = list(counts or [])

    def count(self, table: str, *, filters: dict[str, str]) -> int:
        del table, filters
        return self._counts.pop(0) if self._counts else 0

    def delete(self, table: str, *, filters: dict[str, str]) -> None:
        self.deletes.append((table, filters))


def plan(*deadlines: str) -> dict[str, Any]:
    return {
        "season": "2026-27",
        "gameweeks": [
            {"event": index, "deadline": deadline}
            for index, deadline in enumerate(deadlines, start=1)
        ],
    }


def test_diagnostics_expire_after_thirty_days() -> None:
    client = RecordingDeleteClient()

    prune_private_state(
        client,
        plan("2026-08-21T17:30:00Z"),
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )

    assert (
        "analysis_requests",
        {"requested_at": "lt.2026-08-01T00:00:00Z"},
    ) in client.deletes


def test_transfers_expire_seven_days_after_their_deadline() -> None:
    client = RecordingDeleteClient()

    prune_private_state(
        client,
        plan("2026-08-21T17:30:00Z", "2026-08-28T17:30:00Z"),
        now=datetime(2026, 8, 29, tzinfo=UTC),
    )

    assert (
        "declared_transfers",
        {"season": "eq.2026-27", "event": "in.(1)"},
    ) in client.deletes


def test_transfer_retention_has_a_thirty_day_absolute_cap() -> None:
    client = RecordingDeleteClient()

    prune_private_state(
        client,
        plan("2027-05-30T13:30:00Z"),
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )

    assert (
        "declared_transfers",
        {"declared_at": "lt.2026-08-01T00:00:00Z"},
    ) in client.deletes


def test_no_event_delete_runs_before_deadline_plus_seven_days() -> None:
    client = RecordingDeleteClient()

    prune_private_state(
        client,
        plan("2026-08-21T17:30:00Z"),
        now=datetime(2026, 8, 28, 17, 29, tzinfo=UTC),
    )

    assert all("event" not in filters for _, filters in client.deletes)


def test_every_delete_is_counted_before_any_row_is_removed() -> None:
    client = RecordingDeleteClient([1, 2, 1_001])

    try:
        prune_private_state(
            client,
            plan("2026-08-21T17:30:00Z"),
            now=datetime(2026, 8, 29, tzinfo=UTC),
            max_delete_rows=1_000,
        )
    except RuntimeError as error:
        assert "refusing retention run" in str(error)
    else:
        raise AssertionError("an oversized delete was not refused")

    assert client.deletes == []


def test_the_scheduled_workflow_runs_in_the_production_environment() -> None:
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "prune-private-state.yml"
    ).read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "environment: production" in workflow
    assert "SUPABASE_SECRET_KEY: ${{ secrets.SUPABASE_SECRET_KEY }}" in workflow
    assert "python -m fpl_andres.cli.prune_private_state" in workflow
