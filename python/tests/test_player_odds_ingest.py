"""Reading a book's player markets, and joining them to FPL.

The fetch cannot run anywhere but a runner, so everything worth asserting is
in the parser and the crosswalk. Both refuse rather than guess, which is the
behaviour these pin.
"""

from __future__ import annotations

import pytest

from fpl_andres.adapters.player_crosswalk import crosswalk, fold_name
from fpl_andres.adapters.the_odds_api import (
    Quota,
    by_kickoff,
    classify_event,
    describe_event,
    read_event,
)
from fpl_andres.models.player_odds import PlayerMatchOdds


def _event(*bookmakers: dict[str, object]) -> dict[str, object]:
    return {
        "home_team": "Arsenal",
        "away_team": "Bournemouth",
        "commence_time": "2026-08-21T19:00:00Z",
        "bookmakers": list(bookmakers),
    }


def _book(key: str, market: str, outcomes: list[dict[str, object]]):
    return {"key": key, "markets": [{"key": market, "outcomes": outcomes}]}


def test_a_lone_quote_reads_as_its_implied_probability() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_goal_scorer_anytime",
                [{"description": "Kai Havertz", "name": "Yes", "price": 2.5}],
            )
        )
    )

    assert len(rows) == 1
    assert rows[0].quoted_name == "Kai Havertz"
    assert rows[0].anytime_goal == 0.4
    assert rows[0].books == 1
    assert rows[0].home_team == "Arsenal"
    assert rows[0].away_team == "Bournemouth"
    # The book says nothing about which side he plays for.
    assert rows[0].club is None


def test_a_complete_two_way_book_is_devigged() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_goal_scorer_anytime",
                [
                    {"description": "Kai Havertz", "name": "Yes", "price": 1.9},
                    {"description": "Kai Havertz", "name": "No", "price": 1.9},
                ],
            )
        )
    )

    # Implied is 0.526 either way; the margin comes out and leaves a half.
    assert rows[0].anytime_goal is not None
    assert abs(rows[0].anytime_goal - 0.5) < 1e-6


def test_a_shots_on_target_line_becomes_an_expected_count() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_shots_on_target",
                [
                    {
                        "description": "Bukayo Saka",
                        "name": "Over",
                        "price": 2.0,
                        "point": 1.5,
                    },
                    {
                        "description": "Bukayo Saka",
                        "name": "Under",
                        "price": 2.0,
                        "point": 1.5,
                    },
                ],
            )
        )
    )

    assert len(rows) == 1
    assert rows[0].shots_on_target == pytest.approx(1.678, abs=0.001)


def test_first_and_last_scorer_markets_are_retained() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_first_goal_scorer",
                [{"description": "Bukayo Saka", "name": "Yes", "price": 5.0}],
            ),
            _book(
                "bet365",
                "player_last_goal_scorer",
                [{"description": "Bukayo Saka", "name": "Yes", "price": 4.0}],
            ),
        )
    )

    assert len(rows) == 1
    assert rows[0].first_goal == 0.2
    assert rows[0].last_goal == 0.25
    assert rows[0].priced


def test_no_scorer_is_not_emitted_as_a_player() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_first_goal_scorer",
                [
                    {"description": "Bukayo Saka", "name": "Yes", "price": 5.0},
                    {"name": "No Scorer", "price": 12.0},
                ],
            )
        )
    )

    assert [row.quoted_name for row in rows] == ["Bukayo Saka"]


def test_a_book_quoting_no_margin_does_not_stop_the_fixture() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_goal_scorer_anytime",
                [
                    {"description": "Saka", "name": "Yes", "price": 2.0},
                    {"description": "Saka", "name": "No", "price": 2.0},
                ],
            )
        )
    )

    assert rows[0].anytime_goal == 0.5


def test_books_are_medianed_not_averaged() -> None:
    rows = read_event(
        _event(
            _book(
                "a",
                "player_goal_scorer_anytime",
                [{"description": "Saka", "name": "Yes", "price": 4.0}],
            ),
            _book(
                "b",
                "player_goal_scorer_anytime",
                [{"description": "Saka", "name": "Yes", "price": 5.0}],
            ),
            _book(
                "c",
                "player_goal_scorer_anytime",
                [{"description": "Saka", "name": "Yes", "price": 100.0}],
            ),
        )
    )

    # A mean would be 0.145; the stale hundred must not drag it.
    assert rows[0].anytime_goal == 0.2
    assert rows[0].books == 3


def test_a_market_nobody_asked_for_is_ignored() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "h2h",
                [{"description": "Arsenal", "name": "Arsenal", "price": 1.5}],
            )
        )
    )

    assert rows == []


def test_an_event_with_no_teams_is_refused() -> None:
    try:
        read_event({"bookmakers": []})
    except ValueError as error:
        assert "named no teams" in str(error)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("an event with no teams must not parse")


class TestDescribingWhyNothingWasQuoted:
    """Ten fixtures priced and nought players quoted has three causes.

    The ingest reported the same line for all three, so a run that had been
    refused, a run before the markets opened and a run whose market keys were
    wrong were indistinguishable in the log. Nothing here can be reproduced
    locally -- the host fails at the TLS handshake -- so the run has to say it.
    """

    def test_a_fixture_no_book_priced_says_so(self) -> None:
        assert describe_event(_event()) == "no bookmaker priced it"

    def test_a_book_offering_nothing_is_not_the_same_as_no_book(self) -> None:
        assert describe_event(_event({"key": "bet365", "markets": []})) == "1 books, no markets"

    def test_the_markets_that_did_arrive_are_named(self) -> None:
        described = describe_event(
            _event(
                _book(
                    "bet365",
                    "player_goal_scorer_anytime",
                    [{"description": "Kai Havertz", "name": "Yes", "price": 2.5}],
                )
            )
        )

        assert "1 books" in described
        assert "1 outcomes" in described
        assert "player_goal_scorer_anytime" in described

    def test_the_markets_that_did_not_arrive_are_named_too(self) -> None:
        """The case that decides whether the keys are wrong or the market is shut."""
        described = describe_event(
            _event(
                _book(
                    "bet365",
                    "player_goal_scorer_anytime",
                    [{"description": "Kai Havertz", "name": "Yes", "price": 2.5}],
                )
            )
        )

        assert "absent" in described
        assert "player_assists" in described

    def test_a_book_pricing_only_the_result_names_what_it_did_offer(self) -> None:
        described = describe_event(
            _event(
                _book(
                    "bet365",
                    "h2h",
                    [{"name": "Arsenal", "price": 1.5}, {"name": "Bournemouth", "price": 6.0}],
                )
            )
        )

        assert "'h2h'" in described
        assert "2 outcomes" in described


class TestClassifyingWhyNothingWasQuoted:
    def test_no_bookmaker_is_distinct_from_no_markets(self) -> None:
        assert classify_event(_event()).status == "no-bookmaker"
        assert classify_event(_event({"key": "bet365", "markets": []})).status == "no-markets"

    def test_unrequested_markets_are_not_reported_as_player_markets(self) -> None:
        summary = classify_event(
            _event(
                _book(
                    "bet365",
                    "h2h",
                    [{"name": "Arsenal", "price": 1.5}],
                )
            )
        )

        assert summary.status == "requested-markets-absent"
        assert summary.offered_markets == ("h2h",)
        assert set(summary.missing_markets) == set(summary.requested_markets)

    def test_an_open_requested_market_with_no_rows_is_empty(self) -> None:
        summary = classify_event(_event(_book("bet365", "player_goal_scorer_anytime", [])))

        assert summary.status == "requested-markets-empty"
        assert summary.outcomes == 0

    def test_a_returned_player_market_names_coverage_and_gaps(self) -> None:
        summary = classify_event(
            _event(
                _book(
                    "bet365",
                    "player_goal_scorer_anytime",
                    [{"description": "Kai Havertz", "name": "Yes", "price": 2.5}],
                )
            )
        )

        assert summary.status == "returned"
        assert summary.books == 1
        assert summary.outcomes == 1
        assert summary.offered_markets == ("player_goal_scorer_anytime",)
        assert "player_assists" in summary.missing_markets
        assert set(summary.offered_markets).isdisjoint(summary.missing_markets)


class TestSpendingTheMonthlyBudget:
    """Where a capped run points itself, and what it knows about the bill.

    The free tier is 500 requests a month and the repository documented one
    request per fixture without ever measuring it. Neither the cost nor the
    balance can be checked from here, so both come off the response and into
    the log; the ordering is what stops a capped run spending them all on
    fixtures no book has opened a player market on yet.
    """

    def test_the_soonest_fixture_is_priced_first(self) -> None:
        ordered = by_kickoff(
            [
                {"id": "late", "commence_time": "2026-12-26T15:00:00Z"},
                {"id": "soon", "commence_time": "2026-08-21T19:00:00Z"},
                {"id": "middle", "commence_time": "2026-09-13T13:00:00Z"},
            ]
        )

        assert [event["id"] for event in ordered] == ["soon", "middle", "late"]

    def test_an_unreadable_kickoff_sorts_last_rather_than_vanishing(self) -> None:
        """Dropping it would hide a fixture; sorting it last only defers it."""
        ordered = by_kickoff(
            [
                {"id": "undated", "commence_time": "not a date"},
                {"id": "dated", "commence_time": "2026-12-26T15:00:00Z"},
            ]
        )

        assert [event["id"] for event in ordered] == ["dated", "undated"]

    def test_the_counters_are_read_off_the_response(self) -> None:
        quota = Quota.from_headers(
            {"x-requests-last": "10", "x-requests-used": "120", "x-requests-remaining": "380"}
        )

        assert (quota.cost, quota.used, quota.remaining) == (10, 120, 380)
        assert str(quota) == "cost 10, used 120, 380 left"

    def test_zero_counters_are_reported_as_zero(self) -> None:
        quota = Quota.from_headers(
            {"x-requests-last": "0", "x-requests-used": "123", "x-requests-remaining": "377"}
        )

        assert str(quota) == "cost 0, used 123, 377 left"

    def test_a_host_that_reports_no_counters_says_so_rather_than_reading_zero(self) -> None:
        """Nought left and no answer must not look alike; one stops the run."""
        quota = Quota.from_headers({})

        assert quota.remaining is None
        assert str(quota) == "quota not reported"

    def test_a_counter_that_is_not_a_number_is_not_believed(self) -> None:
        quota = Quota.from_headers({"x-requests-remaining": "unlimited"})

        assert quota.remaining is None


ELEMENTS = [
    {"id": 1, "first_name": "Kai", "second_name": "Havertz", "web_name": "Havertz", "team": 1},
    {"id": 2, "first_name": "Bukayo", "second_name": "Saka", "web_name": "Saka", "team": 1},
    {
        "id": 5,
        "first_name": "Benjamin",
        "second_name": "White",
        "web_name": "White",
        "team": 1,
    },
    {
        "id": 6,
        "first_name": "Gabriel",
        "second_name": "dos Santos Magalhães",
        "web_name": "Gabriel",
        "team": 1,
    },
    # Two Rices: a surname alone must not decide between them.
    {"id": 3, "first_name": "Declan", "second_name": "Rice", "web_name": "Rice", "team": 1},
    {"id": 4, "first_name": "Sean", "second_name": "Rice", "web_name": "Rice", "team": 2},
]


def _row(name: str) -> PlayerMatchOdds:
    return PlayerMatchOdds(
        element_id=None,
        quoted_name=name,
        home_team="Arsenal",
        away_team="Bournemouth",
        kickoff=None,
        anytime_goal=0.3,
    )


def test_an_unambiguous_name_is_matched_and_given_its_club() -> None:
    matched, unmatched = crosswalk([_row("Kai Havertz")], ELEMENTS, {1: "ARS", 2: "BOU"})

    assert unmatched == ()
    assert matched[0].element_id == 1
    assert matched[0].club == "ARS"


def test_a_matched_row_keeps_every_market_probability() -> None:
    row = PlayerMatchOdds(
        element_id=None,
        quoted_name="Kai Havertz",
        home_team="Arsenal",
        away_team="Bournemouth",
        kickoff=None,
        anytime_goal=0.3,
        first_goal=0.12,
        last_goal=0.11,
        anytime_assist=0.2,
        any_card=0.1,
        red_card=0.01,
        shots=2.4,
        shots_on_target=1.2,
        books=3,
    )

    matched, unmatched = crosswalk([row], ELEMENTS, {1: "ARS", 2: "BOU"})

    assert unmatched == ()
    assert matched[0].anytime_goal == 0.3
    assert matched[0].first_goal == 0.12
    assert matched[0].last_goal == 0.11
    assert matched[0].anytime_assist == 0.2
    assert matched[0].any_card == 0.1
    assert matched[0].red_card == 0.01
    assert matched[0].shots == 2.4
    assert matched[0].shots_on_target == 1.2
    assert matched[0].books == 3


def test_a_controlled_short_first_name_matches_the_full_fpl_name() -> None:
    matched, unmatched = crosswalk([_row("Ben White")], ELEMENTS, {1: "ARS"})

    assert unmatched == ()
    assert matched[0].element_id == 5


def test_a_reversed_provider_name_matches_when_the_tokens_are_unique() -> None:
    matched, unmatched = crosswalk([_row("Magalhaes Gabriel")], ELEMENTS, {1: "ARS"})

    assert unmatched == ()
    assert matched[0].element_id == 6


def test_a_shared_surname_is_reported_rather_than_guessed() -> None:
    matched, unmatched = crosswalk([_row("Rice")], ELEMENTS, {1: "ARS", 2: "BOU"})

    assert unmatched == ("Rice",)
    assert matched[0].element_id is None
    # The row survives, so the gap is visible instead of vanishing.
    assert matched[0].quoted_name == "Rice"


def test_accents_and_case_do_not_stop_a_match() -> None:
    assert fold_name("Ødegaard") == fold_name("Odegaard")
    assert fold_name("N'Golo Kanté") == "ngolo kante"


def test_a_name_nobody_carries_is_unmatched() -> None:
    _matched, unmatched = crosswalk([_row("Nobody At All")], ELEMENTS, {})

    assert unmatched == ("Nobody At All",)
