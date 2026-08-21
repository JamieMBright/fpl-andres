"""Keeping the odds, not just the median that reached the model."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime

import pytest

from fpl_andres.adapters.odds_archive import (
    archive_path,
    flatten_event,
    write_archive,
)

FETCHED = datetime(2026, 8, 21, 9, 42, 26, tzinfo=UTC)

PAYLOAD = {
    "id": "abc123",
    "commence_time": "2026-08-21T19:00:00Z",
    "home_team": "Arsenal",
    "away_team": "Coventry City",
    "bookmakers": [
        {
            "key": "bet365",
            "last_update": "2026-08-21T09:40:00Z",
            "markets": [
                {
                    "key": "player_goal_scorer_anytime",
                    "last_update": "2026-08-21T09:39:00Z",
                    "outcomes": [
                        {"description": "Kai Havertz", "name": "Yes", "price": 2.5},
                        {"description": "Kai Havertz", "name": "No", "price": 1.5},
                    ],
                },
                {
                    "key": "player_shots_on_target",
                    "last_update": "2026-08-21T09:38:00Z",
                    "outcomes": [
                        {
                            "description": "Bukayo Saka",
                            "name": "Over",
                            "price": 1.9,
                            "point": 0.5,
                        }
                    ],
                },
            ],
        },
        {
            "key": "unibet",
            "last_update": "2026-08-21T09:41:00Z",
            "markets": [
                {
                    "key": "player_goal_scorer_anytime",
                    "outcomes": [{"description": "Kai Havertz", "name": "Yes", "price": 2.6}],
                }
            ],
        },
    ],
}


def test_every_book_is_kept_not_just_the_median() -> None:
    """The published artifact keeps one number; this keeps the twenty-one.

    A median cannot be un-taken, so an archive of medians can never answer how
    far the books disagreed or which of them moved first.
    """
    rows = list(flatten_event(PAYLOAD, fetched_at=FETCHED))

    havertz = [row for row in rows if row["player"] == "Kai Havertz" and row["selection"] == "Yes"]

    assert {row["bookmaker"] for row in havertz} == {"bet365", "unibet"}
    assert sorted(row["price"] for row in havertz) == [2.5, 2.6]


def test_a_row_carries_when_it_was_seen() -> None:
    """How early a price can be trusted is only answerable from a series."""
    rows = list(flatten_event(PAYLOAD, fetched_at=FETCHED))

    assert {row["fetchedAt"] for row in rows} == {FETCHED.isoformat()}
    # The provider's own timestamps too: a book that has not moved since
    # Tuesday is a different thing from one repriced this morning.
    assert any(row["bookmakerUpdated"] == "2026-08-21T09:40:00Z" for row in rows)


def test_the_line_is_kept_for_a_market_that_has_one() -> None:
    rows = list(flatten_event(PAYLOAD, fetched_at=FETCHED))

    shots = next(row for row in rows if row["market"] == "player_shots_on_target")

    # Without the point, "over" prices nothing.
    assert shots["point"] == 0.5
    assert shots["selection"] == "Over"
    assert shots["player"] == "Bukayo Saka"


def test_the_fixture_is_named_on_every_row() -> None:
    rows = list(flatten_event(PAYLOAD, fetched_at=FETCHED))

    assert rows
    for row in rows:
        assert row["home"] == "Arsenal"
        assert row["away"] == "Coventry City"
        assert row["commenceTime"] == "2026-08-21T19:00:00Z"
        assert row["eventId"] == "abc123"


def test_a_market_nothing_models_yet_is_still_kept() -> None:
    """The archive is for training, so it keeps what the projection ignores."""
    payload = {
        "home_team": "Arsenal",
        "away_team": "Coventry City",
        "bookmakers": [
            {
                "key": "bet365",
                "markets": [
                    {
                        "key": "player_tackles",
                        "outcomes": [{"description": "Declan Rice", "name": "Over", "price": 1.8}],
                    }
                ],
            }
        ],
    }

    rows = list(flatten_event(payload, fetched_at=FETCHED))

    assert [row["market"] for row in rows] == ["player_tackles"]


def test_a_fetch_is_written_once_and_never_rewritten(tmp_path) -> None:
    """Two fetches of the same fixture are both evidence, not a replacement."""
    later = FETCHED.replace(hour=17)

    first = write_archive(
        flatten_event(PAYLOAD, fetched_at=FETCHED),
        season="2026-27",
        fetched_at=FETCHED,
        root=tmp_path,
    )
    second = write_archive(
        flatten_event(PAYLOAD, fetched_at=later),
        season="2026-27",
        fetched_at=later,
        root=tmp_path,
    )

    assert first is not None and second is not None
    assert first != second
    assert first.exists() and second.exists()


def test_the_archive_reads_back_as_rows(tmp_path) -> None:
    path = write_archive(
        flatten_event(PAYLOAD, fetched_at=FETCHED),
        season="2026-27",
        fetched_at=FETCHED,
        root=tmp_path,
    )

    assert path is not None
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]

    assert len(rows) == 4
    assert {row["market"] for row in rows} == {
        "player_goal_scorer_anytime",
        "player_shots_on_target",
    }


def test_a_run_that_priced_nothing_writes_nothing(tmp_path) -> None:
    assert write_archive([], season="2026-27", fetched_at=FETCHED, root=tmp_path) is None


def test_the_path_is_named_for_the_fetch_and_the_season(tmp_path) -> None:
    path = archive_path("2026-27", FETCHED, root=tmp_path)

    assert path.parent.name == "2026-27"
    assert path.name == "20260821T094226Z.jsonl.gz"


@pytest.mark.parametrize(
    "payload",
    [
        {"bookmakers": "not a list"},
        {"bookmakers": [{"markets": [{"outcomes": [None]}]}]},
        {},
    ],
)
def test_a_misshapen_payload_yields_nothing_rather_than_raising(
    payload: dict[str, object],
) -> None:
    assert list(flatten_event(payload, fetched_at=FETCHED)) == []
