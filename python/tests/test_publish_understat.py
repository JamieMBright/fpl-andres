"""The Understat artifact publisher.

The crosswalk is a research output with blocks the web app has no use for, so
the publisher's whole job is to reduce it and refuse when it cannot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpl_andres.artifacts import UNDERSTAT_SCHEMA_VERSION
from fpl_andres.cli.publish_understat import CrosswalkError, main

_SHOT = {
    "shots": 8,
    "shotsPer90": 0.9519,
    "expectedGoalsPerShot": 0.0774,
    "rawExpectedGoalsPerShot": 0.0273,
    "qualityWeight": 0.4444,
    "expectedGoalsPer90": 0.0737,
}
_PENALTY = {
    "expectedGoals": 0.9794,
    "nonPenaltyExpectedGoals": 0.2183,
    "penaltyExpectedGoals": 0.7612,
    "share": 0.7772,
    "penaltiesScored": 1,
    "expectedGoalsAtRiskPer90": 0.0886,
}


def _crosswalk(tmp_path: Path, **overrides: object) -> Path:
    document = {
        "generatedAt": "2026-08-01T12:03:03.367485+00:00",
        "season": "2025-26",
        "source": "understat",
        "coverage": 0.9487,
        "shotProfile": {"15157": dict(_SHOT), "9876": dict(_SHOT)},
        "penaltyExposure": {"15157": dict(_PENALTY), "9876": dict(_PENALTY)},
    }
    document.update(overrides)
    path = tmp_path / "crosswalk.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_publishes_one_row_per_joined_player(tmp_path: Path) -> None:
    output = tmp_path / "understat.json"

    assert main(["--crosswalk", str(_crosswalk(tmp_path)), "--output", str(output)]) == 0

    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["schemaVersion"] == UNDERSTAT_SCHEMA_VERSION
    assert artifact["season"] == "2025-26"
    assert [player["code"] for player in artifact["players"]] == [9876, 15157]


def test_spells_out_what_the_share_is_a_share_of(tmp_path: Path) -> None:
    output = tmp_path / "understat.json"
    main(["--crosswalk", str(_crosswalk(tmp_path)), "--output", str(output)])

    player = json.loads(output.read_text(encoding="utf-8"))["players"][0]
    assert player["penaltyShare"] == pytest.approx(0.7772)
    assert "share" not in player


def test_drops_a_player_present_in_only_one_block(tmp_path: Path) -> None:
    """Half a row would read as a player who took no penalties."""
    output = tmp_path / "understat.json"
    path = _crosswalk(tmp_path, penaltyExposure={"15157": dict(_PENALTY)})

    main(["--crosswalk", str(path), "--output", str(output)])

    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert [player["code"] for player in artifact["players"]] == [15157]


def test_refuses_a_crosswalk_for_a_different_season(tmp_path: Path) -> None:
    path = _crosswalk(tmp_path, season="2024-25")

    with pytest.raises(CrosswalkError, match="2024-25"):
        main(["--crosswalk", str(path), "--season", "2025-26"])


def test_refuses_a_crosswalk_without_the_derived_blocks(tmp_path: Path) -> None:
    path = _crosswalk(tmp_path, shotProfile=None)

    with pytest.raises(CrosswalkError, match="shotProfile"):
        main(["--crosswalk", str(path)])


def test_refuses_a_crosswalk_that_joins_to_nobody(tmp_path: Path) -> None:
    path = _crosswalk(tmp_path, shotProfile={}, penaltyExposure={})

    with pytest.raises(CrosswalkError, match="zero players"):
        main(["--crosswalk", str(path)])


def test_refuses_a_missing_crosswalk(tmp_path: Path) -> None:
    with pytest.raises(CrosswalkError, match="no Understat crosswalk"):
        main(["--crosswalk", str(tmp_path / "absent.json")])


def test_refuses_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "crosswalk.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(CrosswalkError, match="not readable JSON"):
        main(["--crosswalk", str(path)])


def test_refuses_a_document_that_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "crosswalk.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(CrosswalkError, match="not a JSON object"):
        main(["--crosswalk", str(path)])
