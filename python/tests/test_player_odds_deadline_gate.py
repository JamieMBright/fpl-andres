from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_andres.cli import ingest_player_odds
from fpl_andres.cli.ingest_player_odds import (
    deadline_proximity,
    merge_fixture_rows,
    prioritise_uncovered_events,
)
from fpl_andres.models.player_odds import PlayerMatchOdds

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


def _quoted(
    home: str,
    away: str,
    kickoff: datetime,
    *,
    probability: float,
    observed_at: datetime,
) -> PlayerMatchOdds:
    return PlayerMatchOdds(
        element_id=1,
        quoted_name="Player One",
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        anytime_goal=probability,
        observed_at=observed_at,
    )


def test_uncovered_fixtures_are_visited_before_refreshing_an_old_quote() -> None:
    soon = {
        "id": "soon",
        "home_team": "Arsenal",
        "away_team": "Coventry City",
        "commence_time": "2026-08-21T19:00:00Z",
    }
    later = {
        "id": "later",
        "home_team": "Leeds United",
        "away_team": "Nottingham Forest",
        "commence_time": "2026-08-22T14:00:00Z",
    }
    previous = [
        _quoted(
            "Arsenal",
            "Coventry City",
            datetime(2026, 8, 21, 19, 0, tzinfo=UTC),
            probability=0.3,
            observed_at=NOW,
        )
    ]

    ordered = prioritise_uncovered_events([soon, later], previous)

    assert [event["id"] for event in ordered] == ["later", "soon"]


def test_a_fresh_fixture_replaces_itself_and_retains_other_current_quotes() -> None:
    old_time = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)
    fresh_time = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
    arsenal_kickoff = datetime(2026, 8, 21, 19, 0, tzinfo=UTC)
    leeds_kickoff = datetime(2026, 8, 22, 14, 0, tzinfo=UTC)
    previous = [
        _quoted(
            "Arsenal",
            "Coventry City",
            arsenal_kickoff,
            probability=0.25,
            observed_at=old_time,
        ),
        _quoted(
            "Leeds United",
            "Nottingham Forest",
            leeds_kickoff,
            probability=0.2,
            observed_at=old_time,
        ),
    ]
    fresh = [
        _quoted(
            "Arsenal",
            "Coventry City",
            arsenal_kickoff,
            probability=0.4,
            observed_at=fresh_time,
        )
    ]
    current = {
        ("Arsenal", "Coventry City", arsenal_kickoff),
        ("Leeds United", "Nottingham Forest", leeds_kickoff),
    }

    merged = merge_fixture_rows(previous, fresh, current)

    by_fixture = {(row.home_team, row.away_team): row for row in merged}
    assert by_fixture[("Arsenal", "Coventry City")].anytime_goal == 0.4
    assert by_fixture[("Arsenal", "Coventry City")].observed_at == fresh_time
    assert by_fixture[("Leeds United", "Nottingham Forest")].observed_at == old_time
