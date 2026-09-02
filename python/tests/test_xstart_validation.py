from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from fpl_andres.jsonio import read_json_file
from fpl_andres.xstart_validation import evaluate_xstart

ROOT = Path(__file__).resolve().parents[2]
RECORDED_CODE_REVISION = "20d43acd502730f7281d196f0584bb8c610965a7"


def _frozen_inputs(revision: str = RECORDED_CODE_REVISION) -> dict[str, object]:
    source = subprocess.run(
        [
            "git",
            "show",
            f"{revision}:apps/web/src/data/season-inputs.json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(source)


def test_frozen_shipped_xstart_matches_the_scoring_reference() -> None:
    result = evaluate_xstart(
        _frozen_inputs(),
        read_json_file(ROOT / "data" / "live" / "2026-27" / "gw01.json"),
    )

    assert result["field"] == "probabilitySixtyMinutesAsShipped"
    assert result["population"]["count"] == 486
    assert result["population"]["brier"] == pytest.approx(0.230679, abs=0.000001)
    assert result["population"]["logLoss"] == pytest.approx(0.658683, abs=0.000001)
    assert result["population"]["meanForecast"] == pytest.approx(0.496267, abs=0.000001)
    assert result["population"]["actualStartRate"] == pytest.approx(0.448560, abs=0.000001)
    assert result["topEleven"]["hits"] == 128
    assert result["topEleven"]["actualStarters"] == 218
    assert len(result["clubs"]) == 20
    leeds = next(club for club in result["clubs"] if club["club"] == "LEE")
    assert leeds["topElevenHits"] == 10
    assert leeds["brier"] == pytest.approx(0.174089, abs=0.000001)
    assert next(row for row in leeds["selected"] if row["elementId"] == 336) == {
        "elementId": 336,
        "probability": 0.463,
        "started": False,
    }
    assert leeds["missedStarters"] == [{"elementId": 385, "probability": 0.106}]
    assert "reliability" not in result


def test_top_eleven_scoring_refuses_an_incomplete_club_pool() -> None:
    inputs = _frozen_inputs()
    inputs["players"] = [
        player for player in inputs["players"] if player["club"] != "ARS" or int(player["id"]) <= 10
    ]

    with pytest.raises(ValueError, match="top-11 scoring requires eleven"):
        evaluate_xstart(
            inputs,
            read_json_file(ROOT / "data" / "live" / "2026-27" / "gw01.json"),
        )


def test_xstart_accepts_a_settled_gameweek_two_snapshot() -> None:
    result = evaluate_xstart(
        _frozen_inputs("8c9d2ae9064d49e3dae7407045c876e38d7ff654"),
        read_json_file(ROOT / "data" / "live" / "2026-27" / "gw02.json"),
    )

    assert result["population"]["count"] > 0
    assert len(result["clubs"]) == 20
