"""The file a scheduled capture asks before it does anything expensive.

Six captures a weekend, most of which should stop immediately. What decides
that is `--due-within`, and it decides it from a committed file rather than
from the network, so these pin the window arithmetic and the exit codes that
a workflow branches on.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fpl_andres.cli import publish_deadlines
from fpl_andres.cli.publish_deadlines import due_within

NOW = datetime(2026, 8, 21, 20, 0, tzinfo=UTC)


def _rows() -> list[dict[str, object]]:
    return [
        {"event": 1, "deadline": "2026-08-21T17:30:00Z", "finished": False},
        {"event": 2, "deadline": "2026-08-28T17:30:00Z", "finished": False},
    ]


class TestWhetherADeadlineHasJustPassed:
    def test_a_deadline_two_hours_behind_is_inside_a_six_hour_window(self) -> None:
        assert due_within(_rows(), 6, NOW) == 1

    def test_a_deadline_two_hours_behind_is_outside_a_one_hour_window(self) -> None:
        assert due_within(_rows(), 1, NOW) is None

    def test_a_deadline_still_ahead_is_not_answered(self) -> None:
        """Picks are private until the deadline passes. Ahead is useless."""
        assert due_within(_rows(), 6, NOW - timedelta(days=1)) is None

    def test_the_most_recent_deadline_wins_when_two_could_match(self) -> None:
        rows = [
            {"event": 1, "deadline": "2026-08-21T15:00:00Z", "finished": False},
            {"event": 2, "deadline": "2026-08-21T17:30:00Z", "finished": False},
        ]

        assert due_within(rows, 8, NOW) == 2

    def test_a_deadline_that_is_not_a_timestamp_is_skipped_not_fatal(self) -> None:
        rows = [
            {"event": 1, "deadline": "2026-08-21T17:30:00Z", "finished": False},
            {"event": 2, "deadline": "soon", "finished": False},
        ]

        assert due_within(rows, 6, NOW) == 1

    def test_a_season_with_no_deadlines_answers_nothing(self) -> None:
        assert due_within([], 6, NOW) is None


class TestReadingTheBootstrap:
    def test_every_gameweek_is_kept_in_order_with_its_deadline(self) -> None:
        rows = publish_deadlines._events(
            {
                "events": [
                    {"id": 2, "deadline_time": "2026-08-28T17:30:00Z", "finished": False},
                    {"id": 1, "deadline_time": "2026-08-21T17:30:00Z", "finished": True},
                ]
            }
        )

        assert [row["event"] for row in rows] == [1, 2]
        assert rows[0]["finished"] is True

    def test_an_event_without_a_deadline_is_dropped_rather_than_defaulted(self) -> None:
        """A missing deadline is a missing rule, and inventing one is worse."""
        rows = publish_deadlines._events(
            {
                "events": [
                    {"id": 1, "finished": False},
                    {"id": 2, "deadline_time": "2026-08-28T17:30:00Z", "finished": False},
                ]
            }
        )

        assert [row["event"] for row in rows] == [2]

    def test_a_bootstrap_without_events_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            publish_deadlines._events({"elements": []})

    def test_a_bootstrap_that_is_not_an_object_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            publish_deadlines._events(["events"])

    def test_the_global_fallback_keeps_only_browser_contract_fields(self) -> None:
        bootstrap = {
            "elements": [
                {
                    **{field: 0 for field in publish_deadlines._BOOTSTRAP_FIELDS["elements"]},
                    "id": 1,
                    "code": 2,
                    "web_name": "Player",
                    "status": "a",
                    "squad_number": None,
                    "extra_private_noise": "drop me",
                }
            ],
            "element_types": [{"id": 1, "singular_name_short": "GKP"}],
            "teams": [{"id": 1, "code": 3, "short_name": "ARS", "name": "Arsenal"}],
            "events": [{"id": 1, "finished": False, "deadline_time": "2026-08-21T17:30:00Z"}],
        }

        artifact = publish_deadlines.global_payload(
            bootstrap,
            [{"event": 1, "team_h": 1, "team_a": 2, "kickoff_time": "drop me"}],
            generated_at="2026-08-11T04:20:00Z",
        )

        element = artifact["bootstrap"]["elements"][0]  # type: ignore[index]
        assert "extra_private_noise" not in element
        assert artifact["fixtures"] == [{"event": 1, "team_h": 1, "team_a": 2}]

    def test_the_global_fallback_refuses_a_partial_player_row(self) -> None:
        with pytest.raises(ValueError, match="required field"):
            publish_deadlines.global_payload(
                {
                    "elements": [{"id": 1}],
                    "element_types": [],
                    "teams": [],
                    "events": [],
                },
                [],
                generated_at="2026-08-11T04:20:00Z",
            )


class TestAskingTheCommittedFile:
    def _saved(self, tmp_path: Path) -> Path:
        path = tmp_path / "deadlines.json"
        path.write_text(
            json.dumps({"schemaVersion": 1, "deadlines": _rows()}) + "\n",
            encoding="utf-8",
        )
        return path

    def test_it_prints_the_gameweek_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = self._saved(tmp_path)
        monkeypatch.setattr(publish_deadlines, "datetime", _FrozenClock)

        assert publish_deadlines.main(["--output", str(path), "--due-within", "6"]) == 0

        assert capsys.readouterr().out.strip() == "1"

    def test_it_exits_one_when_there_is_nothing_to_capture(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The common case. A workflow branches on this and does no work."""
        path = self._saved(tmp_path)
        monkeypatch.setattr(publish_deadlines, "datetime", _FrozenClock)

        assert publish_deadlines.main(["--output", str(path), "--due-within", "0.5"]) == 1

        assert capsys.readouterr().out == ""


class _FrozenClock(datetime):
    """`datetime.now` only, so the window is arithmetic rather than weather."""

    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return NOW
