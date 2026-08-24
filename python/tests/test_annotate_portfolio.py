"""Annotate a portfolio file with the realised points per element.

The sidecar file is a fact-of-record: what FPL says each held player scored.
These tests cover the file-writing logic and the behaviour when data is absent,
without hitting the live endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fpl_andres.cli.annotate_portfolio import (
    SCHEMA_VERSION,
    _output_path,
    annotate,
    main,
)


def _write_portfolio(directory: Path, event: int, element_ids: list[int]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"gw{event:02d}.json").write_text(
        json.dumps(
            {
                "event": event,
                "holdings": [
                    {
                        "elementId": eid,
                        "captainedShare": 0.0,
                        "ownedShare": 0.5,
                        "startedShare": 0.5,
                        "effectiveOwnership": 0.5,
                        "owned": 250,
                        "started": 250,
                        "captained": 0,
                        "viceCaptained": 0,
                    }
                    for eid in element_ids
                ],
            }
        ),
        encoding="utf-8",
    )


def _live_payload(points_by_element: dict[int, int]) -> dict[int, int]:
    """What `_fetch_live` returns: element id to realised points, already parsed."""
    return dict(points_by_element)


class TestAnnotate:
    def test_writes_a_sidecar_with_points_for_held_elements(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11, 22, 33])
        live = _live_payload({11: 8, 22: 3, 33: 0, 99: 12})

        with patch("fpl_andres.cli.annotate_portfolio._fetch_live", return_value=live):
            result = annotate(1, tmp_path)

        assert result == {11: 8, 22: 3, 33: 0}
        output = json.loads(_output_path(tmp_path, 1).read_text(encoding="utf-8"))
        assert output["schemaVersion"] == SCHEMA_VERSION
        assert output["event"] == 1
        assert output["elementPoints"] == {"11": 8, "22": 3, "33": 0}

    def test_elements_not_in_live_data_are_silently_omitted(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11, 22, 44])

        with patch("fpl_andres.cli.annotate_portfolio._fetch_live", return_value={11: 8, 22: 3}):
            result = annotate(1, tmp_path)

        assert result is not None
        assert 44 not in result

    def test_returns_none_when_portfolio_is_missing(self, tmp_path: Path) -> None:
        with patch("fpl_andres.cli.annotate_portfolio._fetch_live", return_value={11: 5}):
            assert annotate(99, tmp_path) is None

    def test_returns_none_when_live_endpoint_returns_nothing(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11, 22])
        with patch("fpl_andres.cli.annotate_portfolio._fetch_live", return_value={}):
            assert annotate(1, tmp_path) is None

    def test_output_keys_are_sorted_strings(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [300, 11, 55])
        with patch(
            "fpl_andres.cli.annotate_portfolio._fetch_live",
            return_value={300: 6, 11: 9, 55: 4},
        ):
            annotate(1, tmp_path)

        output = json.loads(_output_path(tmp_path, 1).read_text(encoding="utf-8"))
        keys = list(output["elementPoints"].keys())
        assert keys == sorted(keys, key=int)

    def test_sidecar_carries_a_fetched_at_timestamp(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 2, [11])
        with patch("fpl_andres.cli.annotate_portfolio._fetch_live", return_value={11: 7}):
            annotate(2, tmp_path)

        output = json.loads(_output_path(tmp_path, 2).read_text(encoding="utf-8"))
        assert "fetchedAt" in output
        assert output["fetchedAt"].endswith("Z")


class TestMain:
    def test_exits_zero_on_success(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11, 22])
        with patch("fpl_andres.cli.annotate_portfolio._fetch_live", return_value={11: 8, 22: 3}):
            code = main(["--event", "1", "--portfolio-dir", str(tmp_path)])
        assert code == 0

    def test_exits_nonzero_when_portfolio_is_absent(self, tmp_path: Path) -> None:
        code = main(["--event", "99", "--portfolio-dir", str(tmp_path)])
        assert code != 0

    def test_exits_nonzero_when_scores_are_not_published(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11])
        with patch("fpl_andres.cli.annotate_portfolio._fetch_live", return_value={}):
            code = main(["--event", "1", "--portfolio-dir", str(tmp_path)])
        assert code != 0
