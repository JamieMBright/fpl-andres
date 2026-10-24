"""Every crowd capture establishes its references, including newly listed players."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fpl_andres.cli.capture_crowd import _capture
from fpl_andres.contracts import FetchedPayload, SourceSnapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("season_exists", [False, True])
async def test_capture_establishes_new_player_references_without_overwriting_existing_ones(
    season_exists: bool,
) -> None:
    captured_at = datetime(2026, 10, 24, tzinfo=UTC)
    fetched = FetchedPayload(
        payload={
            "teams": [{"id": 1, "code": 3, "name": "Arsenal", "short_name": "ARS"}],
            "elements": [
                {
                    "id": element_id,
                    "code": element_id,
                    "team": 1,
                    "element_type": 3,
                    "now_cost": 50,
                    "web_name": f"Player {element_id}",
                    "selected_by_percent": "1.0",
                }
                for element_id in (1, 669)
            ],
            "total_players": 11_000_000,
        },
        snapshot=SourceSnapshot(
            source="fpl",
            fetched_at=captured_at,
            data_available_at=captured_at,
            content_hash=f"sha256:{'a' * 64}",
            upstream_reference="https://fantasy.premierleague.com/api/bootstrap-static/",
        ),
        compressed_bytes=123,
    )
    database = MagicMock()
    database.__enter__.return_value = database
    database.select.return_value = [{"season": "2026-27"}] if season_exists else []
    database.insert.return_value = [{"id": "00000000-0000-0000-0000-000000000001"}]
    fpl = MagicMock()
    fpl.fetch_bootstrap = AsyncMock(return_value=fetched)

    with (
        patch("fpl_andres.cli.capture_crowd.FplClient", return_value=fpl),
        patch("fpl_andres.cli.capture_crowd.SupabaseCredentials.from_env"),
        patch("fpl_andres.cli.capture_crowd.SupabaseRestClient", return_value=database),
    ):
        result = await _capture(argparse.Namespace(season="2026-27", event=8, dry_run=False))

    assert result == 0
    writes = database.insert_ignoring_duplicates.call_args_list
    assert [write.args[0] for write in writes] == [
        "seasons",
        "teams",
        "elements",
        "crowd_snapshots",
    ]
    assert [row["element_id"] for row in writes[2].args[1]] == [1, 669]
    assert [row["element_id"] for row in writes[3].args[1]] == [1, 669]
    assert writes[2].kwargs["on_conflict"] == "season,element_id"
    database.upsert.assert_not_called()
