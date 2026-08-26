from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_andres.cli.build_gw1_review import write_once
from fpl_andres.gw1_review import band_for, build_review_artifact, frozen_points_at_event
from fpl_andres.jsonio import read_json_file

ROOT = Path(__file__).resolve().parents[2]
RECORDED_CODE_REVISION = "20d43acd502730f7281d196f0584bb8c610965a7"

EXPECTED_XPTS = {
    1: 5.912784,
    4: 4.509314,
    481: 4.324672,
    426: 4.087918,
    498: 3.817712,
    106: 3.710518,
    388: 3.670659,
    387: 3.558042,
    368: 3.463480,
    82: 3.285647,
    124: 2.953886,
    68: 2.592972,
    346: 2.531466,
    61: 2.430679,
    465: 1.964351,
}


def _frozen_inputs() -> dict[str, object]:
    source = subprocess.run(
        [
            "git",
            "show",
            f"{RECORDED_CODE_REVISION}:apps/web/src/data/season-inputs.json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(source)


def _picks() -> dict[str, object]:
    rows = [
        (1, 1, 2, True, False),
        (4, 2, 1, False, True),
        (388, 3, 1, False, False),
        (387, 4, 1, False, False),
        (498, 5, 1, False, False),
        (426, 6, 1, False, False),
        (68, 7, 1, False, False),
        (481, 8, 1, False, False),
        (368, 9, 1, False, False),
        (124, 10, 1, False, False),
        (106, 11, 1, False, False),
        (82, 12, 0, False, False),
        (61, 13, 0, False, False),
        (346, 14, 0, False, False),
        (465, 15, 0, False, False),
    ]
    return {
        "active_chip": None,
        "entry_history": {"event": 1, "points": 56},
        "picks": [
            {
                "element": element,
                "position": position,
                "multiplier": multiplier,
                "is_captain": captain,
                "is_vice_captain": vice,
            }
            for element, position, multiplier, captain, vice in rows
        ],
    }


def test_frozen_gw1_xpts_matches_every_shipped_team_value() -> None:
    inputs = _frozen_inputs()
    players = {int(row["id"]): row for row in inputs["players"]}

    assert set(EXPECTED_XPTS) <= set(players)
    for element_id, expected in EXPECTED_XPTS.items():
        assert frozen_points_at_event(inputs, players[element_id], 0) == pytest.approx(
            expected,
            abs=0.000001,
        )


def test_review_keeps_raw_grades_and_observed_armbands() -> None:
    review = build_review_artifact(
        _frozen_inputs(),
        read_json_file(ROOT / "data" / "live" / "2026-27" / "gw01.json"),
        _picks(),
        entry_id=2_822_737,
        generated_at=datetime(2026, 8, 26, 12, tzinfo=UTC),
        canonical_manifest_revision="916de48afecfa174c58d759c3de4a5262dad140c",
        recorded_code_revision=RECORDED_CODE_REVISION,
        canonical_model_version="8.6",
        canonical_deadline="2026-08-21T17:30:00+00:00",
        canonical_frozen_at="2026-08-21T09:44:27+00:00",
        live_source_hash="sha256:" + "a" * 64,
        picks_source_hash="sha256:" + "b" * 64,
    )

    assert review["team"]["points"] == 56
    assert review["team"]["benchPoints"] == 13
    assert review["canonicalModelVersion"] == "8.6"
    assert review["canonicalDeadline"] == "2026-08-21T17:30:00+00:00"
    raya = next(row for row in review["picks"] if row["elementId"] == 1)
    assert raya["isCaptain"] is True
    assert raya["actualPoints"] == 6
    assert raya["countedPoints"] == 12
    assert raya["frozenXpts"] == pytest.approx(EXPECTED_XPTS[1], abs=0.000001)
    assert raya["band"] == "as_projected"
    assert raya["actual"]["saves"] == 1
    assert raya["actual"]["cleanSheets"] == 1
    assert raya["actual"]["bonus"] == 0
    gabriel = next(row for row in review["picks"] if row["elementId"] == 4)
    assert gabriel["isViceCaptain"] is True
    guehi = next(row for row in review["picks"] if row["elementId"] == 388)
    assert guehi["band"] == "haul"


def test_review_artifacts_are_written_once(tmp_path: Path) -> None:
    output = tmp_path / "review.json"

    assert write_once(output, {"schemaVersion": 1}) is True
    assert write_once(output, {"schemaVersion": 2}) is False
    assert json.loads(output.read_text(encoding="utf-8")) == {"schemaVersion": 1}


@pytest.mark.parametrize(
    ("actual", "expected", "band"),
    [
        (6, EXPECTED_XPTS[1], "as_projected"),
        (5, EXPECTED_XPTS[4], "as_projected"),
        (10, EXPECTED_XPTS[388], "haul"),
        (10, EXPECTED_XPTS[68], "haul"),
        (8, EXPECTED_XPTS[368], "haul"),
        (7, EXPECTED_XPTS[82], "above"),
        (4, EXPECTED_XPTS[465], "above"),
        (2, EXPECTED_XPTS[387], "below"),
        (3, EXPECTED_XPTS[498], "below"),
        (2, EXPECTED_XPTS[426], "below"),
        (2, EXPECTED_XPTS[481], "below"),
        (2, EXPECTED_XPTS[124], "below"),
        (0, EXPECTED_XPTS[106], "below"),
        (1, EXPECTED_XPTS[61], "below"),
        (1, EXPECTED_XPTS[346], "below"),
    ],
)
def test_review_bands_grade_raw_player_points(actual: int, expected: float, band: str) -> None:
    assert band_for(actual, expected) == band
