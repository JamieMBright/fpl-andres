from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_andres.cli import ingest_player_odds
from fpl_andres.cli.ingest_player_odds import deadline_proximity

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)


def artifact(tmp_path: Path, deadline: str) -> Path:
    path = tmp_path / "deadlines.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "generatedAt": "2026-08-11T04:20:00Z",
                "deadlines": [{"event": 1, "deadline": deadline, "finished": False}],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_seven_days_or_less_is_close_enough(tmp_path: Path) -> None:
    decision = deadline_proximity(
        artifact(tmp_path, "2026-08-18T09:00:00Z"),
        within_days=7,
        now=NOW,
    )

    assert decision.due is True
    assert decision.event == 1
    assert decision.days == 7


def test_farther_than_seven_days_bails_cleanly(tmp_path: Path) -> None:
    decision = deadline_proximity(
        artifact(tmp_path, "2026-08-18T09:00:01Z"),
        within_days=7,
        now=NOW,
    )

    assert decision.due is False
    assert decision.event == 1


def test_no_upcoming_deadline_is_a_source_failure(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no upcoming deadline"):
        deadline_proximity(
            artifact(tmp_path, "2026-08-10T09:00:00Z"),
            within_days=7,
            now=NOW,
        )


def test_main_skips_before_reading_the_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    monkeypatch.setattr(ingest_player_odds, "datetime", _FrozenClock)
    result = ingest_player_odds.main(
        [
            "--season",
            "2026-27",
            "--deadlines",
            str(artifact(tmp_path, "2026-08-21T17:30:00Z")),
            "--within-days",
            "7",
        ]
    )

    assert result == 0
    assert "outside the 7-day player-market window" in capsys.readouterr().out


class _FrozenClock(datetime):
    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return NOW
