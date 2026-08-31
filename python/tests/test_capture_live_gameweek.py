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
        round_complete=True,
    )

    assert snapshot["schemaVersion"] == capture_live_gameweek.SCHEMA_VERSION
    assert snapshot["sourceHash"] == f"sha256:{hashlib.sha256(raw).hexdigest()}"
    assert snapshot["roundComplete"] is True
    assert snapshot["elements"][0]["stats"]["starts"] == 1
    assert snapshot["elements"][0]["stats"]["saves"] == 3
    assert snapshot["elements"][0]["stats"]["total_points"] == 6


def _fixtures(monkeypatch, rows) -> None:
    monkeypatch.setattr(capture_live_gameweek, "_fetch_fixtures", lambda _event: rows)


def _live(monkeypatch, raw: bytes) -> None:
    monkeypatch.setattr(capture_live_gameweek, "_get_bytes", lambda _url: raw)


def test_capture_writes_the_round_being_played_once_a_match_kicks_off(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A gameweek can run for four days; the site should not wait for day four."""
    output = tmp_path / "gw02.json"
    _fixtures(monkeypatch, [{"finished": False, "started": True}, {"finished": False}])
    _live(monkeypatch, _raw_live())

    assert capture_live_gameweek.capture(2, "2026-27", output) is True

    snapshot = json.loads(output.read_text(encoding="utf-8"))
    assert snapshot["roundComplete"] is False
    assert snapshot["elements"][0]["stats"]["total_points"] == 6


def test_capture_waits_for_the_first_kickoff(tmp_path: Path, monkeypatch) -> None:
    """Before any match starts there is nothing measured to publish."""
    output = tmp_path / "gw02.json"
    _fixtures(monkeypatch, [{"finished": False, "started": False}])
    _live(monkeypatch, _raw_live())

    assert capture_live_gameweek.capture(2, "2026-27", output) is False
    assert not output.exists()


def test_capture_replaces_the_round_being_played_as_matches_land(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "gw02.json"
    _fixtures(monkeypatch, [{"finished": False, "started": True}])
    _live(monkeypatch, _raw_live())
    assert capture_live_gameweek.capture(2, "2026-27", output) is True

    moved = _raw_live().replace(b'"total_points":6', b'"total_points":9')
    _live(monkeypatch, moved)

    assert capture_live_gameweek.capture(2, "2026-27", output) is True
    snapshot = json.loads(output.read_text(encoding="utf-8"))
    assert snapshot["elements"][0]["stats"]["total_points"] == 9
    assert snapshot["roundComplete"] is False


def test_capture_leaves_the_snapshot_alone_when_the_round_has_not_moved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Two-hourly polling must not commit an identical round every two hours."""
    output = tmp_path / "gw02.json"
    _fixtures(monkeypatch, [{"finished": False, "started": True}])
    _live(monkeypatch, _raw_live())
    assert capture_live_gameweek.capture(2, "2026-27", output) is True
    before = output.read_text(encoding="utf-8")

    assert capture_live_gameweek.capture(2, "2026-27", output) is False
    assert output.read_text(encoding="utf-8") == before


def test_capture_freezes_the_round_once_every_match_is_confirmed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "gw02.json"
    _fixtures(monkeypatch, [{"finished": False, "started": True}])
    _live(monkeypatch, _raw_live())
    assert capture_live_gameweek.capture(2, "2026-27", output) is True

    settled = _raw_live().replace(b'"bonus":3', b'"bonus":2')
    _fixtures(monkeypatch, [{"finished": True, "started": True}])
    _live(monkeypatch, settled)

    assert capture_live_gameweek.capture(2, "2026-27", output) is True
    assert json.loads(output.read_text(encoding="utf-8"))["roundComplete"] is True


def test_capture_never_rewrites_a_settled_snapshot(tmp_path: Path, monkeypatch) -> None:
    """The settled archive is the immutable evidence every projection rests on."""
    output = tmp_path / "gw02.json"
    _fixtures(monkeypatch, [{"finished": True, "started": True}])
    _live(monkeypatch, _raw_live())
    assert capture_live_gameweek.capture(2, "2026-27", output) is True
    before = output.read_text(encoding="utf-8")

    _live(monkeypatch, _raw_live().replace(b'"total_points":6', b'"total_points":99'))

    assert capture_live_gameweek.capture(2, "2026-27", output) is False
    assert output.read_text(encoding="utf-8") == before


def test_capture_refuses_an_unstarted_round_or_an_unreadable_output(
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

    # Bytes that do not parse cannot be shown to be replaceable, so they are
    # left where they are rather than overwritten on a guess.
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
