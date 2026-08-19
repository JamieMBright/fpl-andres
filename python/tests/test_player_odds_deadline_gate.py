from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_andres.cli import ingest_player_odds
from fpl_andres.cli.ingest_player_odds import (
    FixtureDiagnostic,
    deadline_proximity,
    merge_fixture_diagnostics,
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


def _diagnostic(
    event_id: str,
    home: str,
    away: str,
    kickoff: datetime,
    *,
    status: str = "returned",
    visited_at: datetime | None = NOW,
) -> FixtureDiagnostic:
    return FixtureDiagnostic(
        event_id=event_id,
        home_team=home,
        away_team=away,
        home_short=None,
        away_short=None,
        kickoff=kickoff,
        status=status,
        visited_at=visited_at,
        books=1 if visited_at else 0,
        outcomes=1 if visited_at else 0,
        offered_markets=("player_goal_scorer_anytime",) if visited_at else (),
        missing_markets=(),
        player_rows_parsed=1 if visited_at else 0,
        player_rows_matched=1 if visited_at else 0,
        unmatched_names=(),
        error=None,
    )


def test_fixture_diagnostics_replace_fresh_retain_old_and_name_unvisited() -> None:
    first = datetime(2026, 8, 21, 19, 0, tzinfo=UTC)
    second = datetime(2026, 8, 22, 14, 0, tzinfo=UTC)
    third = datetime(2026, 8, 23, 13, 0, tzinfo=UTC)
    events = [
        {
            "id": "first",
            "home_team": "Arsenal",
            "away_team": "Coventry City",
            "commence_time": first.isoformat(),
        },
        {
            "id": "second",
            "home_team": "Leeds United",
            "away_team": "Nottingham Forest",
            "commence_time": second.isoformat(),
        },
        {
            "id": "third",
            "home_team": "Brentford",
            "away_team": "Tottenham Hotspur",
            "commence_time": third.isoformat(),
        },
    ]
    previous = [
        _diagnostic("first", "Arsenal", "Coventry City", first),
        _diagnostic("second", "Leeds United", "Nottingham Forest", second),
    ]
    fresh = [
        _diagnostic(
            "first",
            "Arsenal",
            "Coventry City",
            first,
            status="requested-markets-empty",
            visited_at=datetime(2026, 8, 19, 9, 0, tzinfo=UTC),
        )
    ]

    merged = merge_fixture_diagnostics(previous, fresh, events)

    assert [row.event_id for row in merged] == ["first", "second", "third"]
    assert merged[0].status == "requested-markets-empty"
    assert merged[1] == previous[1]
    assert merged[2].status == "unvisited"
    assert merged[2].visited_at is None


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "teams": [
                {"id": 1, "name": "Arsenal", "short_name": "ARS"},
                {"id": 2, "name": "Coventry", "short_name": "COV"},
                {"id": 3, "name": "Leeds", "short_name": "LEE"},
                {"id": 4, "name": "Nott'm Forest", "short_name": "NFO"},
            ],
            "elements": [
                {
                    "id": 10,
                    "first_name": "Kai",
                    "second_name": "Havertz",
                    "web_name": "Havertz",
                    "team": 1,
                }
            ],
        }


class _Client:
    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, _url: str, **_kwargs: object) -> _Response:
        return _Response()


def test_an_empty_in_window_run_still_publishes_fixture_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        {
            "id": "ars-cov",
            "home_team": "Arsenal",
            "away_team": "Coventry City",
            "commence_time": "2026-08-18T19:00:00Z",
        },
        {
            "id": "nfo-lee",
            "home_team": "Nottingham Forest",
            "away_team": "Leeds United",
            "commence_time": "2026-08-19T14:00:00Z",
        },
    ]
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key")
    monkeypatch.setattr(ingest_player_odds, "datetime", _FrozenClock)
    monkeypatch.setattr(ingest_player_odds.httpx, "Client", lambda **_kwargs: _Client())
    monkeypatch.setattr(
        ingest_player_odds,
        "list_events",
        lambda _client, _key: (events, ingest_player_odds.Quota(0, 100, 400)),
    )
    monkeypatch.setattr(
        ingest_player_odds,
        "fetch_event_odds",
        lambda _client, _key, event_id: (
            {
                **next(event for event in events if event["id"] == event_id),
                "bookmakers": [],
            },
            ingest_player_odds.Quota(0, 100, 400),
        ),
    )
    output = tmp_path / "player-odds.json"

    result = ingest_player_odds.main(
        [
            "--season",
            "2026-27",
            "--output",
            str(output),
            "--deadlines",
            str(artifact(tmp_path, "2026-08-18T09:00:00Z")),
        ]
    )

    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 1
    assert payload["clubQuoteFloor"] == 18
    assert payload["quota"] == {
        "opening": {"cost": 0, "used": 100, "remaining": 400},
        "closing": {"cost": 0, "used": 100, "remaining": 400},
        "spentThisRun": 0,
    }
    assert payload["nameMappingGaps"] == []
    assert payload["players"] == []
    assert payload["coverage"] == {
        "fixturesListed": 2,
        "fixturesVisitedThisRun": 2,
        "fixturesWithQuotes": 0,
    }
    assert [fixture["status"] for fixture in payload["fixtures"]] == [
        "no-bookmaker",
        "no-bookmaker",
    ]
    assert [(row["home_short"], row["away_short"]) for row in payload["fixtures"]] == [
        ("ARS", "COV"),
        ("NFO", "LEE"),
    ]


def test_returned_rows_and_unmatched_names_are_attributed_to_the_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = {
        "id": "ars-cov",
        "home_team": "Arsenal",
        "away_team": "Coventry City",
        "commence_time": "2026-08-18T19:00:00Z",
    }
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key")
    monkeypatch.setattr(ingest_player_odds, "datetime", _FrozenClock)
    monkeypatch.setattr(ingest_player_odds.httpx, "Client", lambda **_kwargs: _Client())
    monkeypatch.setattr(
        ingest_player_odds,
        "list_events",
        lambda _client, _key: ([event], ingest_player_odds.Quota(0, 100, 400)),
    )
    monkeypatch.setattr(
        ingest_player_odds,
        "fetch_event_odds",
        lambda _client, _key, _event_id: (
            {
                **event,
                "bookmakers": [
                    {
                        "key": "bet365",
                        "markets": [
                            {
                                "key": "player_goal_scorer_anytime",
                                "outcomes": [
                                    {"description": "Kai Havertz", "name": "Yes", "price": 2.5},
                                    {"description": "Mystery Player", "name": "Yes", "price": 4.0},
                                ],
                            }
                        ],
                    }
                ],
            },
            ingest_player_odds.Quota(2, 102, 398),
        ),
    )
    output = tmp_path / "player-odds.json"

    result = ingest_player_odds.main(
        [
            "--season",
            "2026-27",
            "--output",
            str(output),
            "--deadlines",
            str(artifact(tmp_path, "2026-08-18T09:00:00Z")),
        ]
    )

    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    diagnostic = payload["fixtures"][0]
    assert diagnostic["status"] == "returned"
    assert diagnostic["player_rows_parsed"] == 2
    assert diagnostic["player_rows_matched"] == 1
    assert diagnostic["unmatched_names"] == ["Mystery Player"]
    assert diagnostic["offered_markets"] == ["player_goal_scorer_anytime"]
    assert "player_assists" in diagnostic["missing_markets"]
    assert payload["unmatched"] == ["Mystery Player"]
    assert payload["coverage"]["fixturesWithQuotes"] == 1


def test_a_malformed_event_persists_only_a_safe_error_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = {
        "id": "ars-cov",
        "home_team": "Arsenal",
        "away_team": "Coventry City",
        "commence_time": "2026-08-18T19:00:00Z",
    }
    monkeypatch.setenv("THE_ODDS_API_KEY", "secret-that-must-not-be-written")
    monkeypatch.setattr(ingest_player_odds, "datetime", _FrozenClock)
    monkeypatch.setattr(ingest_player_odds.httpx, "Client", lambda **_kwargs: _Client())
    monkeypatch.setattr(
        ingest_player_odds,
        "list_events",
        lambda _client, _key: ([event], ingest_player_odds.Quota(0, 100, 400)),
    )
    monkeypatch.setattr(
        ingest_player_odds,
        "fetch_event_odds",
        lambda _client, _key, _event_id: (
            {"bookmakers": []},
            ingest_player_odds.Quota(0, 100, 400),
        ),
    )
    output = tmp_path / "player-odds.json"

    result = ingest_player_odds.main(
        [
            "--season",
            "2026-27",
            "--output",
            str(output),
            "--deadlines",
            str(artifact(tmp_path, "2026-08-18T09:00:00Z")),
        ]
    )

    assert result == 0
    text = output.read_text(encoding="utf-8")
    assert "secret-that-must-not-be-written" not in text
    diagnostic = json.loads(text)["fixtures"][0]
    assert diagnostic["status"] == "parse-error"
    assert diagnostic["error"] == "ValueError"
