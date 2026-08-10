"""Reading this season's elite off the Overall league instead of every id.

The id sweep walks thirteen million entries to find the two in ten thousand
who finish inside the top ten thousand. The Overall league is the same
information from the other end: an ordinary classic league holding every
entry, ordered by rank, fifty to a page. Two hundred requests where the sweep
needs thirteen million.

What it cannot do is reach backwards, and these pin that too.
"""

from __future__ import annotations

import pytest

from fpl_andres.cohorts.league import (
    PAGE_SIZE,
    StandingRow,
    pages_for,
    parse_standings,
    unseen,
)


def _payload(rows: list[dict[str, object]], *, has_next: bool = False, page: int = 1) -> dict:
    return {"standings": {"has_next": has_next, "page": page, "results": rows}}


class TestReadingAPage:
    def test_a_standing_carries_the_entry_its_rank_and_its_points(self) -> None:
        page = parse_standings(
            _payload([{"entry": 429, "rank": 1, "total": 2708, "player_name": "A Manager"}])
        )
        assert page is not None

        assert page.rows == (StandingRow(entry_id=429, rank=1, total=2708),)

    def test_the_next_page_is_reported_so_paging_can_stop(self) -> None:
        page = parse_standings(_payload([], has_next=True, page=3))
        assert page is not None

        assert (page.page, page.has_next) == (3, True)

    def test_a_league_with_no_standings_yet_is_empty_rather_than_absent(self) -> None:
        """Between seasons the league is real and nobody has played.

        That is a different answer from being handed something that is not a
        league, and a harvester that cannot tell them apart would treat the
        pre-season as a fault every day until August.
        """
        page = parse_standings(_payload([]))

        assert page is not None
        assert page.rows == ()

    def test_something_that_is_not_a_league_is_refused(self) -> None:
        assert parse_standings({"detail": "Not found."}) is None
        assert parse_standings({"standings": {"results": "nope"}}) is None

    def test_a_row_without_a_rank_is_dropped_rather_than_ranked_nought(self) -> None:
        page = parse_standings(
            _payload(
                [
                    {"entry": 1, "rank": 0, "total": 10},
                    {"entry": 2, "rank": None, "total": 10},
                    {"entry": 3, "rank": 4, "total": 10},
                ]
            )
        )
        assert page is not None

        assert [row.entry_id for row in page.rows] == [3]


class TestWhatItCosts:
    def test_the_top_ten_thousand_is_two_hundred_pages(self) -> None:
        """The whole reason this exists beside the id sweep."""
        assert pages_for(10_000) == 200
        assert PAGE_SIZE == 50

    def test_a_partial_page_still_counts_as_one(self) -> None:
        assert pages_for(1) == 1
        assert pages_for(51) == 2

    def test_no_ceiling_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            pages_for(0)


class TestNotFetchingTheSameHistoryTwice:
    """A manager's past seasons never change, so a history is fetched once."""

    def test_only_the_unknown_are_returned(self) -> None:
        rows = [
            StandingRow(entry_id=1, rank=1, total=0),
            StandingRow(entry_id=2, rank=2, total=0),
            StandingRow(entry_id=3, rank=3, total=0),
        ]

        assert unseen(rows, frozenset({2})) == (1, 3)

    def test_a_page_already_catalogued_costs_nothing(self) -> None:
        rows = [StandingRow(entry_id=7, rank=1, total=0)]

        assert unseen(rows, frozenset({7})) == ()
