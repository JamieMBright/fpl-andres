"""The crowd capture has never once succeeded, and never said why.

Three scheduled runs since the job was written, three failures, each in about
twenty-five seconds. `crowd_snapshots.season` is a foreign key into `seasons`
and `(season, element_id)` is one into `elements`. Both are filled by the
historical ingest, which reads a published archive -- and an archive of a
season only exists once that season has been played.

So a job whose entire purpose is capturing *live* pre-deadline ownership
depends on a corpus that cannot yet contain the season it is capturing. The
read half works: `--dry-run` returns 570 elements for 2026-27 GW1. The write
half hits the foreign key.

The failure surfaced as an opaque PostgREST status because the check happened
inside the database. It now happens here, before anything is written, and says
what is wrong.
"""

from __future__ import annotations

from typing import Any

from fpl_andres.cli.capture_crowd import _unseeded


class _Client:
    """Records the read it was asked for and returns what it was told to."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def select(
        self, table: str, *, columns: str = "*", filters: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append((table, {"columns": columns, "filters": filters}))
        return self._rows


class TestTheSeasonPreflight:
    def test_a_seeded_season_passes_silently(self) -> None:
        client = _Client([{"season": "2025-26"}])

        assert _unseeded(client, "2025-26") is None  # type: ignore[arg-type]

    def test_an_unseeded_season_is_refused_before_anything_is_written(self) -> None:
        client = _Client([])

        message = _unseeded(client, "2026-27")  # type: ignore[arg-type]

        assert message is not None
        assert "2026-27" in message

    def test_the_message_names_the_constraint_rather_than_a_status_code(self) -> None:
        # The whole point: "returned 409" sent somebody to the wrong place for
        # three runs. The message has to name the foreign key and the fix.
        message = _unseeded(_Client([]), "2026-27")  # type: ignore[arg-type]

        assert message is not None
        assert "foreign key" in message
        assert "seasons" in message
        assert "elements" in message
        assert "Ingest the season first" in message

    def test_it_asks_the_database_only_about_the_season_in_hand(self) -> None:
        # A bare select on `seasons` would pull every row of a table this job
        # has no business reading in bulk.
        client = _Client([])
        _unseeded(client, "2026-27")  # type: ignore[arg-type]

        table, kwargs = client.calls[0]
        assert table == "seasons"
        assert kwargs["filters"] == {"season": "eq.2026-27"}
        assert kwargs["columns"] == "season"
