"""The armband the site draws, and what it returned.

`_portfolio_captains` is what puts real data on the FPL500 page as soon as a
deadline has passed. Once the round finishes, `annotate_portfolio` writes a
sidecar beside the capture, and the captain entries carry what each pick
actually scored. Without that the page can only ever say who the cohort
backed, never whether backing them worked.
"""

from __future__ import annotations

import json
from pathlib import Path

from fpl_andres.cli.publish_fpl500 import _portfolio_captains


def _capture(directory: Path, event: int, shares: dict[int, float]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"gw{event:02d}.json").write_text(
        json.dumps(
            {
                "event": event,
                "counted": 500,
                "holdings": [
                    {"elementId": element, "captainedShare": share}
                    for element, share in shares.items()
                ],
            }
        ),
        encoding="utf-8",
    )


def _sidecar(directory: Path, event: int, points: dict[int, int]) -> None:
    (directory / f"gw{event:02d}-points.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "event": event,
                "fetchedAt": "2026-08-24T06:00:00Z",
                "elementPoints": {str(element): score for element, score in points.items()},
            }
        ),
        encoding="utf-8",
    )


class TestPortfolioCaptains:
    def test_a_captain_carries_what_the_pick_scored(self, tmp_path: Path) -> None:
        _capture(tmp_path, 1, {11: 0.62, 22: 0.38})
        _sidecar(tmp_path, 1, {11: 13, 22: 2})

        captains = _portfolio_captains(tmp_path)

        assert captains["01"] == [
            {"elementId": 11, "share": 0.62, "points": 13},
            {"elementId": 22, "share": 0.38, "points": 2},
        ]

    def test_a_round_still_in_play_carries_no_points_at_all(self, tmp_path: Path) -> None:
        # No sidecar until the round is final, and a zero here would read as
        # "captained and blanked" rather than "not scored yet".
        _capture(tmp_path, 1, {11: 0.62})

        entry = _portfolio_captains(tmp_path)["01"][0]

        assert "points" not in entry

    def test_a_captain_absent_from_the_sidecar_carries_no_points(self, tmp_path: Path) -> None:
        _capture(tmp_path, 1, {11: 0.62, 22: 0.38})
        _sidecar(tmp_path, 1, {11: 13})

        captains = _portfolio_captains(tmp_path)

        assert captains["01"][0]["points"] == 13
        assert "points" not in captains["01"][1]

    def test_the_sidecar_is_not_read_as_a_gameweek_of_its_own(self, tmp_path: Path) -> None:
        _capture(tmp_path, 1, {11: 0.62})
        _sidecar(tmp_path, 1, {11: 13})

        assert list(_portfolio_captains(tmp_path)) == ["01"]
