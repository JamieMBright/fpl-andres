from __future__ import annotations

import json
from pathlib import Path

from fpl_andres.recent_transfers import _blocked_recent_transfer_codes


def _write_inputs(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "players": [
                    {
                        "code": 440993,
                        "club": "MCI",
                        "recentClubChange": {
                            "from": "EVE",
                            "to": "MCI",
                            "detectedAt": "2026-09-04T06:58:57Z",
                            "avoidUntilEvent": 3,
                        },
                    },
                    {"code": 1001, "club": "ARS"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_a_recent_arrival_is_blocked_through_the_named_gameweek(tmp_path: Path) -> None:
    inputs = tmp_path / "season-inputs.json"
    _write_inputs(inputs)

    assert _blocked_recent_transfer_codes(inputs, 3) == {440993}


def test_a_recent_arrival_returns_after_the_named_gameweek(tmp_path: Path) -> None:
    inputs = tmp_path / "season-inputs.json"
    _write_inputs(inputs)

    assert _blocked_recent_transfer_codes(inputs, 4) == set()


def test_a_missing_inputs_artifact_blocks_nobody(tmp_path: Path) -> None:
    assert _blocked_recent_transfer_codes(tmp_path / "missing.json", 3) == set()
