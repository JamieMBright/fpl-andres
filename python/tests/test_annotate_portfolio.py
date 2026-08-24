"""Annotate a portfolio file with the realised points per element.

The sidecar file is a fact-of-record: what FPL says each held player scored.
These tests cover the file-writing logic, the finality gate that decides when a
round has stopped moving, and the behaviour when data is absent — all without
hitting the live endpoint.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fpl_andres.cli.annotate_portfolio import (
    SCHEMA_VERSION,
    _output_path,
    annotate,
    main,
    round_is_complete,
)


@contextmanager
def _fpl(points: dict[int, int], *, complete: bool = True) -> Iterator[None]:
    """Stand in for both FPL endpoints at once.

    Every test here has to answer the fixture question as well as the points
    one, because the gate is asked first. Left to each test it would be four
    lines of `patch` before the line under test.
    """
    fixtures = [{"id": 1, "event": 1, "finished": complete}]
    with (
        patch("fpl_andres.cli.annotate_portfolio._fetch_fixtures", return_value=fixtures),
        patch("fpl_andres.cli.annotate_portfolio._fetch_live", return_value=points),
    ):
        yield


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


class TestRoundIsComplete:
    """The gate that decides whether the round's points have stopped moving.

    FPL flips `finished_provisional` at full time and `finished` once bonus is
    confirmed. Reading the live endpoint before then records a scoreline that
    is still changing, into a file this repository calls a fact of record.
    """

    def test_a_round_whose_fixtures_have_all_finished_is_complete(self) -> None:
        assert round_is_complete([{"event": 3, "finished": True}, {"event": 3, "finished": True}])

    def test_one_unfinished_fixture_holds_the_whole_round_open(self) -> None:
        assert not round_is_complete(
            [{"event": 3, "finished": True}, {"event": 3, "finished": False}]
        )

    def test_full_time_is_not_final_because_bonus_has_not_landed(self) -> None:
        # `finished_provisional` is the whistle; `finished` is the confirmed
        # scoreline. Between them every player in the match can still gain
        # three points.
        assert not round_is_complete(
            [{"event": 3, "finished": False, "finished_provisional": True}]
        )

    def test_a_round_with_no_fixtures_is_not_complete(self) -> None:
        # An empty list is a fixture list FPL has not published, not a round
        # that finished. `all([])` is True, which is the trap this closes.
        assert not round_is_complete([])


class TestAnnotate:
    def test_writes_a_sidecar_with_points_for_held_elements(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11, 22, 33])

        with _fpl(_live_payload({11: 8, 22: 3, 33: 0, 99: 12})):
            result = annotate(1, tmp_path)

        assert result == {11: 8, 22: 3, 33: 0}
        output = json.loads(_output_path(tmp_path, 1).read_text(encoding="utf-8"))
        assert output["schemaVersion"] == SCHEMA_VERSION
        assert output["event"] == 1
        assert output["elementPoints"] == {"11": 8, "22": 3, "33": 0}

    def test_elements_not_in_live_data_are_silently_omitted(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11, 22, 44])

        with _fpl({11: 8, 22: 3}):
            result = annotate(1, tmp_path)

        assert result is not None
        assert 44 not in result

    def test_returns_none_when_portfolio_is_missing(self, tmp_path: Path) -> None:
        with _fpl({11: 5}):
            assert annotate(99, tmp_path) is None

    def test_returns_none_when_live_endpoint_returns_nothing(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11, 22])
        with _fpl({}):
            assert annotate(1, tmp_path) is None

    def test_writes_nothing_while_a_fixture_is_still_to_finish(self, tmp_path: Path) -> None:
        # The live endpoint answers all week. Reading it mid-round records a
        # scoreline that is still moving, so the gate refuses before the fetch.
        _write_portfolio(tmp_path, 1, [11, 22])
        with _fpl({11: 8, 22: 3}, complete=False):
            assert annotate(1, tmp_path) is None
        assert not _output_path(tmp_path, 1).exists()

    def test_writes_nothing_when_the_fixture_list_cannot_be_read(self, tmp_path: Path) -> None:
        # Unreachable is not the same as finished. Without an answer the round
        # stays open, and the next scheduled run asks again.
        _write_portfolio(tmp_path, 1, [11])
        with (
            patch("fpl_andres.cli.annotate_portfolio._fetch_fixtures", return_value=None),
            patch("fpl_andres.cli.annotate_portfolio._fetch_live", return_value={11: 8}),
        ):
            assert annotate(1, tmp_path) is None
        assert not _output_path(tmp_path, 1).exists()

    def test_output_keys_are_sorted_strings(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [300, 11, 55])
        with _fpl({300: 6, 11: 9, 55: 4}):
            annotate(1, tmp_path)

        output = json.loads(_output_path(tmp_path, 1).read_text(encoding="utf-8"))
        keys = list(output["elementPoints"].keys())
        assert keys == sorted(keys, key=int)

    def test_sidecar_carries_a_fetched_at_timestamp(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 2, [11])
        with _fpl({11: 7}):
            annotate(2, tmp_path)

        output = json.loads(_output_path(tmp_path, 2).read_text(encoding="utf-8"))
        assert "fetchedAt" in output
        assert output["fetchedAt"].endswith("Z")


class TestBackfill:
    """With no event named, every captured week missing a sidecar is attempted.

    The round a capture describes finishes days after the deadline that
    triggered it, and a job that only ever looks at the week it just captured
    leaves every earlier week unannotated forever.
    """

    def test_annotates_every_captured_week_that_has_no_sidecar(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11])
        _write_portfolio(tmp_path, 2, [22])

        with _fpl({11: 9, 22: 4}):
            assert main(["--portfolio-dir", str(tmp_path)]) == 0

        assert _output_path(tmp_path, 1).exists()
        assert _output_path(tmp_path, 2).exists()

    def test_a_week_already_annotated_is_not_fetched_again(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11])
        with _fpl({11: 9}):
            main(["--portfolio-dir", str(tmp_path)])
        written = _output_path(tmp_path, 1).read_text(encoding="utf-8")

        with patch("fpl_andres.cli.annotate_portfolio._fetch_live") as live:
            assert main(["--portfolio-dir", str(tmp_path)]) == 0
        assert live.call_count == 0
        assert _output_path(tmp_path, 1).read_text(encoding="utf-8") == written

    def test_a_round_still_in_play_is_left_for_the_next_run(self, tmp_path: Path) -> None:
        # The expected state on most days. A red job every day until the round
        # ends is a job nobody reads.
        _write_portfolio(tmp_path, 1, [11])
        with _fpl({11: 9}, complete=False):
            assert main(["--portfolio-dir", str(tmp_path)]) == 0
        assert not _output_path(tmp_path, 1).exists()

    def test_no_captures_at_all_is_not_a_failure(self, tmp_path: Path) -> None:
        assert main(["--portfolio-dir", str(tmp_path)]) == 0

    def test_the_sidecar_is_never_mistaken_for_a_capture(self, tmp_path: Path) -> None:
        # `gw01-points.json` sits beside `gw01.json` and matches `gw*.json`.
        _write_portfolio(tmp_path, 1, [11])
        with _fpl({11: 9}):
            main(["--portfolio-dir", str(tmp_path)])
            assert main(["--portfolio-dir", str(tmp_path)]) == 0
        assert not (tmp_path / "gw01-points-points.json").exists()


class TestMain:
    def test_exits_zero_on_success(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11, 22])
        with _fpl({11: 8, 22: 3}):
            code = main(["--event", "1", "--portfolio-dir", str(tmp_path)])
        assert code == 0

    def test_exits_nonzero_when_portfolio_is_absent(self, tmp_path: Path) -> None:
        code = main(["--event", "99", "--portfolio-dir", str(tmp_path)])
        assert code != 0

    def test_exits_nonzero_when_scores_are_not_published(self, tmp_path: Path) -> None:
        _write_portfolio(tmp_path, 1, [11])
        with _fpl({}):
            code = main(["--event", "1", "--portfolio-dir", str(tmp_path)])
        assert code != 0

    def test_a_named_event_still_in_play_is_refused_out_loud(self, tmp_path: Path) -> None:
        # Asking for one week by name is a person asking a question. Silence
        # would read as "done", so the answer is an error.
        _write_portfolio(tmp_path, 1, [11])
        with _fpl({11: 8}, complete=False):
            code = main(["--event", "1", "--portfolio-dir", str(tmp_path)])
        assert code != 0
