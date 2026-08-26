from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres.cli import capture_live_gameweek


def _raw_live() -> bytes:
    return json.dumps(
        {
            "elements": [
                {
                    "id": 1,
                    "stats": {
                        "starts": 1,
                        "minutes": 90,
                        "goals_scored": 0,
                        "assists": 0,
                        "clean_sheets": 1,
                        "goals_conceded": 0,
                        "own_goals": 0,
                        "penalties_saved": 0,
                        "penalties_missed": 0,
                        "yellow_cards": 0,
                        "red_cards": 0,
                        "saves": 3,
                        "bonus": 3,
                        "defensive_contribution": 4,
                        "total_points": 6,
                    },
                    "explain": [],
                }
            ]
        },
        separators=(",", ":"),
    ).encode()


def test_snapshot_preserves_the_complete_fpl_payload_and_hash() -> None:
    raw = _raw_live()

    snapshot = capture_live_gameweek.build_snapshot(
        raw,
        season="2026-27",
        event=1,
        captured_at=datetime(2026, 8, 26, 12, tzinfo=UTC),
    )

    assert snapshot["schemaVersion"] == capture_live_gameweek.SCHEMA_VERSION
    assert snapshot["sourceHash"] == f"sha256:{hashlib.sha256(raw).hexdigest()}"
    assert snapshot["roundComplete"] is True
    assert snapshot["elements"][0]["stats"]["starts"] == 1
    assert snapshot["elements"][0]["stats"]["saves"] == 3
    assert snapshot["elements"][0]["stats"]["total_points"] == 6


def test_capture_refuses_an_unfinished_round_or_existing_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "gw01.json"
    monkeypatch.setattr(
        capture_live_gameweek,
        "_fetch_fixtures",
        lambda _event: [{"finished": False}],
    )
    monkeypatch.setattr(capture_live_gameweek, "_get_bytes", lambda _url: _raw_live())

    assert capture_live_gameweek.capture(1, "2026-27", output) is False
    assert not output.exists()

    output.write_text("immutable bytes", encoding="utf-8")
    monkeypatch.setattr(
        capture_live_gameweek,
        "_fetch_fixtures",
        lambda _event: [{"finished": True}],
    )

    assert capture_live_gameweek.capture(1, "2026-27", output) is False
    assert output.read_text(encoding="utf-8") == "immutable bytes"


def test_scheduled_capture_reads_every_finished_deadline(tmp_path: Path) -> None:
    deadlines = tmp_path / "deadlines.json"
    deadlines.write_text(
        '{"deadlines":['
        '{"event":2,"finished":false},'
        '{"event":1,"finished":true},'
        '{"event":3,"finished":true}'
        "]}",
        encoding="utf-8",
    )

    assert capture_live_gameweek.finished_events(deadlines) == [1, 3]
