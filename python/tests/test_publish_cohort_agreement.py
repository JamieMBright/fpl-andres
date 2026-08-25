"""publish_cohort_agreement writes a JSON summary of cohort captain choices.

The output is a description, not a score. These tests verify the file shape and
that the summary counts are correct.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpl_andres.cli.publish_cohort_agreement import main


def _capture(directory: Path, event: int, shares: dict[int, float], counted: int = 500) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"gw{event:02d}.json").write_text(
        json.dumps(
            {
                "event": event,
                "counted": counted,
                "holdings": [
                    {"elementId": element, "captainedShare": share}
                    for element, share in shares.items()
                ],
            }
        ),
        encoding="utf-8",
    )


class TestPublishCohortAgreement:
    def test_exits_zero_when_no_captures_exist(self, tmp_path: Path) -> None:
        output = tmp_path / "agreement.json"
        code = main(
            [
                "--portfolio-dir",
                str(tmp_path / "empty"),
                "--output",
                str(output),
            ]
        )
        assert code == 0
        assert not output.exists()

    def test_writes_output_with_correct_week_count(self, tmp_path: Path) -> None:
        portfolio = tmp_path / "portfolio"
        _capture(portfolio, 1, {11: 0.91, 22: 0.09})
        _capture(portfolio, 2, {11: 0.40, 22: 0.35, 33: 0.25})
        output = tmp_path / "agreement.json"
        code = main(["--portfolio-dir", str(portfolio), "--output", str(output)])
        assert code == 0
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["capturedWeeks"] == 2
        assert data["contestedWeeks"] == 1

    def test_each_week_carries_modal_captain_and_unanimity(self, tmp_path: Path) -> None:
        portfolio = tmp_path / "portfolio"
        _capture(portfolio, 1, {11: 0.65, 22: 0.35})
        output = tmp_path / "agreement.json"
        main(["--portfolio-dir", str(portfolio), "--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        week = data["weeks"][0]
        assert week["event"] == 1
        assert week["modalCaptain"] == 11
        assert week["unanimity"] == pytest.approx(0.65, abs=1e-4)

    def test_top_captains_are_sorted_by_share_descending(self, tmp_path: Path) -> None:
        portfolio = tmp_path / "portfolio"
        _capture(portfolio, 1, {11: 0.40, 22: 0.35, 33: 0.25})
        output = tmp_path / "agreement.json"
        main(["--portfolio-dir", str(portfolio), "--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        shares = [entry["share"] for entry in data["weeks"][0]["topCaptains"]]
        assert shares == sorted(shares, reverse=True)

    def test_captains_below_minimum_share_are_excluded(self, tmp_path: Path) -> None:
        portfolio = tmp_path / "portfolio"
        # One player below the 0.01 threshold
        _capture(portfolio, 1, {11: 0.995, 22: 0.005})
        output = tmp_path / "agreement.json"
        main(["--portfolio-dir", str(portfolio), "--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        element_ids = {e["elementId"] for e in data["weeks"][0]["topCaptains"]}
        assert 22 not in element_ids

    def test_output_carries_schema_version(self, tmp_path: Path) -> None:
        portfolio = tmp_path / "portfolio"
        _capture(portfolio, 1, {11: 1.0})
        output = tmp_path / "agreement.json"
        main(["--portfolio-dir", str(portfolio), "--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        assert "schemaVersion" in data
        assert "generatedAt" in data
