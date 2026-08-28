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

from fpl_andres.cli.publish_fpl500 import _portfolio_captains, _portfolio_series


def _capture(
    directory: Path,
    event: int,
    shares: dict[int, float],
    *,
    basis: str = "catalogue-at-deadline",
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"gw{event:02d}.json").write_text(
        json.dumps(
            {
                "event": event,
                "capturedAt": "2026-08-21T19:13:44Z",
                "basis": basis,
                "attempted": 500 if basis == "ranked-500" else 2_786,
                "responded": 500 if basis == "ranked-500" else 2_786,
                "counted": 500,
                "coverage": 1.0,
                "membership": (
                    {
                        "label": "post-deadline capture-era FPL500 membership",
                        "sourceTiming": "post-deadline",
                        "sourceGeneratedAt": "2026-08-21T17:42:14Z",
                        "secondsFromDeadline": 734,
                        "sourceCommit": "7ee37f9ef2eb40502b94cba4e2bd0a10cd84b1ad",
                        "size": 500,
                    }
                    if basis == "ranked-500"
                    else None
                ),
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

    def test_catalogue_and_exact_500_are_published_as_separate_series(self, tmp_path: Path) -> None:
        catalogue = tmp_path / "portfolio"
        exact = catalogue / "fpl500"
        _capture(catalogue, 1, {11: 0.62})
        _capture(exact, 1, {22: 0.54}, basis="ranked-500")

        catalogue_series = _portfolio_series(
            catalogue,
            basis="catalogue-at-deadline",
            label="Catalogue at deadline",
        )
        exact_series = _portfolio_series(
            exact,
            basis="ranked-500",
            label="Exact FPL500",
        )

        assert catalogue_series["captains"]["01"][0]["elementId"] == 11
        assert catalogue_series["samples"]["01"]["attempted"] == 2_786
        assert exact_series["captains"]["01"][0]["elementId"] == 22
        assert exact_series["samples"]["01"]["attempted"] == 500
        assert (
            exact_series["samples"]["01"]["membershipLabel"]
            == "post-deadline capture-era FPL500 membership"
        )

    def test_exact_series_publishes_all_holdings_and_accumulates_raw_returns(
        self, tmp_path: Path
    ) -> None:
        _capture(tmp_path, 1, {11: 0.62, 22: 0.38}, basis="ranked-500")
        _sidecar(tmp_path, 1, {11: 8, 22: 3})
        _capture(tmp_path, 2, {11: 0.50, 33: 0.50}, basis="ranked-500")
        _sidecar(tmp_path, 2, {11: 2, 33: 10})

        series = _portfolio_series(tmp_path, basis="ranked-500", label="Exact FPL500")

        first = series["holdings"]["01"]
        second = series["holdings"]["02"]
        expected = {
            "elementId": 11,
            "ownedShare": 0.0,
            "startedShare": 0.0,
            "captainedShare": 0.62,
            "effectiveOwnership": 0.0,
            "lastWeekPoints": 8,
            "pointsSinceFirstCapture": 8,
            "weightedContribution": 0.0,
        }
        assert {key: first[0][key] for key in expected} == expected
        assert (
            next(row for row in second if row["elementId"] == 11)["pointsSinceFirstCapture"] == 10
        )

    def test_an_unfinished_round_omits_popularity_squad_points(self, tmp_path: Path) -> None:
        _capture(tmp_path, 1, {11: 0.62}, basis="ranked-500")
        (tmp_path / "gw01-structure-v3.json").write_text(
            json.dumps(
                {
                    "cohortRevision": None,
                    "popularitySquad": {"starters": [11]},
                }
            ),
            encoding="utf-8",
        )

        series = _portfolio_series(tmp_path, basis="ranked-500", label="Exact FPL500")
        popularity = series["samples"]["01"]["structure"]["popularitySquad"]

        assert "rawGameweekPoints" not in popularity
