"""The loader has to turn a capture file into weeks without inventing any.

The capture format stores a share for every holding, most of which nobody
captained. Reading those in as zero-share candidates would make every week look
contested, which is the exact conclusion this command exists to test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpl_andres.cli.cohort_captains import load_weeks, main


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


class TestLoadWeeks:
    def test_a_missing_directory_is_an_empty_series_not_a_crash(self, tmp_path: Path) -> None:
        assert load_weeks(tmp_path / "never-ran") == []

    def test_holdings_nobody_captained_are_not_candidates(self, tmp_path: Path) -> None:
        # 14 of the 15 in a squad carry a zero armband share. Keeping them would
        # put the modal captain on 60% of a field of fifteen instead of one.
        _capture(tmp_path, 7, {11: 0.62, 22: 0.0, 33: 0.0, 44: 0.38})
        week = load_weeks(tmp_path)[0]
        assert set(week.share_by_element) == {11, 44}
        assert week.modal_captain == 11

    def test_weeks_come_back_in_gameweek_order(self, tmp_path: Path) -> None:
        _capture(tmp_path, 12, {11: 1.0})
        _capture(tmp_path, 3, {22: 1.0})
        assert [week.event for week in load_weeks(tmp_path)] == [3, 12]

    def test_a_week_the_job_ran_and_found_nothing_is_still_a_week(self, tmp_path: Path) -> None:
        # Dropping it would leave a gap indistinguishable from a week the job
        # never ran, and only one of those needs chasing.
        _capture(tmp_path, 9, {}, counted=0)
        weeks = load_weeks(tmp_path)
        assert [week.event for week in weeks] == [9]
        assert weeks[0].modal_captain is None

    def test_the_points_sidecar_is_not_a_second_gameweek(self, tmp_path: Path) -> None:
        # `annotate_portfolio` writes `gwNN-points.json` beside the capture. It
        # carries the same `event` and no holdings, so a glob that accepts it
        # doubles the series and files an uncontested empty week against a
        # gameweek that was captured properly.
        _capture(tmp_path, 1, {11: 0.62, 22: 0.38})
        (tmp_path / "gw01-points.json").write_text(
            json.dumps({"schemaVersion": 1, "event": 1, "elementPoints": {"11": 13}}),
            encoding="utf-8",
        )
        weeks = load_weeks(tmp_path)
        assert [week.event for week in weeks] == [1]
        assert weeks[0].modal_captain == 11


class TestCommand:
    def test_no_captures_says_so_and_does_not_fail_the_run(self, tmp_path: Path) -> None:
        # The captures only exist once the season is under way. An empty series
        # is a fact about the calendar, not a broken job.
        assert main(["--captures", str(tmp_path / "absent")]) == 0

    def test_it_leads_with_how_many_weeks_were_contested(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _capture(tmp_path, 1, {11: 0.91, 22: 0.09})
        _capture(tmp_path, 2, {11: 0.40, 22: 0.35, 33: 0.25})
        assert main(["--captures", str(tmp_path)]) == 0
        printed = capsys.readouterr().out
        assert "captured weeks: 2" in printed
        assert "contested weeks" in printed
        assert printed.index("contested weeks") < printed.index("gw01")

    def test_picks_are_scored_against_the_cohort_when_supplied(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _capture(tmp_path, 1, {11: 0.40, 22: 0.35, 33: 0.25})
        picks = tmp_path / "picks.json"
        picks.write_text(json.dumps({"template": {"1": 11}}), encoding="utf-8")
        assert main(["--captures", str(tmp_path), "--picks", str(picks)]) == 0
        printed = capsys.readouterr().out
        assert "template" in printed
        assert "100%" in printed
