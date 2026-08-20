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
from fpl_andres.cli.ingest_player_odds import can_request_fixture, spent_after_response
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

    def test_the_run_cap_uses_the_provider_measured_delta(self) -> None:
        opening = Quota(cost=0, used=100, remaining=400)
        closing = Quota(cost=None, used=127, remaining=373)

        spent = spent_after_response(opening=opening, closing=closing, local_spent=0)

        assert spent == 27
        assert can_request_fixture(spent=spent, budget=50)
        assert not can_request_fixture(spent=54, budget=50)

    def test_missing_provider_counters_fall_back_to_response_cost(self) -> None:
        opening = Quota(cost=None, used=None, remaining=None)
        closing = Quota(cost=8, used=None, remaining=None)

        assert spent_after_response(opening=opening, closing=closing, local_spent=16) == 24


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
    {
        "id": 224,
        "first_name": "Eddie",
        "second_name": "Nketiah",
        "web_name": "Nketiah",
        "team": 2,
    },
    {
        "id": 262,
        "first_name": "Emile",
        "second_name": "Smith Rowe",
        "web_name": "Smith Rowe",
        "team": 2,
    },
    {
        "id": 337,
        "first_name": "Brenden",
        "second_name": "Aaronson",
        "web_name": "Aaronson",
        "team": 2,
    },
    {
        "id": 364,
        "first_name": "Kostas",
        "second_name": "Tsimikas",
        "web_name": "Tsimikas",
        "team": 2,
    },
    {
        "id": 377,
        "first_name": "Daniel",
        "second_name": "Muñoz Mejía",
        "web_name": "Muñoz",
        "team": 2,
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


@pytest.mark.parametrize(
    ("quoted", "element_id"),
    [
        ("Brendan Aaronson", 337),
        ("Edward Nketiah", 224),
        ("Emile Smith-Rowe", 262),
        ("Konstantinos Tsimikas", 364),
        ("Alvaro Daniel Rodriguez Munoz", 201),
    ],
)
def test_live_provider_name_overrides_match_explicit_fpl_players(
    quoted: str,
    element_id: int,
) -> None:
    elements = [
        *ELEMENTS,
        {
            "id": element_id,
            "first_name": "",
            "second_name": "",
            "web_name": "",
            "team": 2,
        },
    ]
    matched, unmatched = crosswalk([_row(quoted)], elements, {1: "ARS", 2: "BOU"})

    assert unmatched == ()
    assert matched[0].element_id == element_id


@pytest.mark.parametrize(
    ("quoted", "element_id"),
    [
        ("Abdul Fatawu Issahaku", 315),
        ("Alvaro Daniel Rodriguez Munoz", 201),
        ("Alysson Edward", 52),
        ("Chiedoze Ogbene", 314),
        ("Christopher Rigg", 548),
        ("Damian Emiliano Martinez", 28),
        ("Degnand Wilfried Gnonto", 341),
        ("Iliman-Cheikh Ndiaye", 237),
        ("Iliya Gruev", 344),
        ("Iyenoma Destiny Udogie", 506),
        ("Jaden Philogene-Bidace", 318),
        ("Jens Hjerto Dahl", 574),
        ("Jocelin Ta Bi", 550),
        ("Joseph Willock", 460),
        ("Joshua Kofi Acheampong", 151),
        ("Kaine Hayden", 177),
        ("Kai Andrews", 192),
        ("Marcelino Ignacio Nunez Espinoza", 309),
        ("Mickey van de Ven", 503),
        ("Mamodou Sarr", 150),
        ("Niko O'Reilly", 387),
        ("Nilson David Angulo Ramirez", 551),
        ("Ogochukwu Onyeka Frank", 104),
        ("Oliver McBurnie", 295),
        ("Omari Giraud-Hutchinson", 484),
        ("Rayan Ait Nouri", 392),
        ("Valentino Livramento", 450),
        ("Vitaliy Mykolenko", 233),
        ("Yeremi Pino", 211),
    ],
)
def test_live_provider_name_overrides_cover_current_bootstrap_aliases(
    quoted: str,
    element_id: int,
) -> None:
    elements = [{"id": element_id, "first_name": "", "second_name": "", "web_name": "", "team": 2}]
    matched, unmatched = crosswalk([_row(quoted)], elements, {2: "BOU"})

    assert unmatched == ()
    assert matched[0].element_id == element_id


def test_a_stale_provider_name_override_is_not_used_without_that_fpl_player() -> None:
    matched, unmatched = crosswalk([_row("Yeremi Pino")], ELEMENTS, {1: "ARS", 2: "BOU"})

    assert unmatched == ("Yeremi Pino",)
    assert matched[0].element_id is None


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


def test_a_first_scorer_price_above_the_anytime_price_is_refused() -> None:
    """Scoring first requires scoring, so the bound needs no model behind it.

    Eleven players carried a first-scorer probability near 0.5 on 2026-08-20
    from books that priced them anytime between 0.04 and 0.20. Whatever the
    provider meant by it, it is not a first-scorer probability.
    """
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_goal_scorer_anytime",
                [{"description": "Jake Bidwell", "name": "Yes", "price": 21.0}],
            ),
            {
                "key": "unibet",
                "markets": [
                    {
                        "key": "player_first_goal_scorer",
                        "outcomes": [
                            {
                                "description": "Jake Bidwell",
                                "name": "Yes",
                                "price": 1.99,
                            }
                        ],
                    }
                ],
            },
        )
    )

    (row,) = rows
    # The impossible reading goes; the sound one beside it stays, because it is
    # the one that prices a scoring route.
    assert row.first_goal is None
    assert row.anytime_goal is not None
    assert row.anytime_goal == pytest.approx(1 / 21.0, rel=1e-6)


def test_a_last_scorer_price_above_the_anytime_price_is_refused() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_goal_scorer_anytime",
                [{"description": "Jake Bidwell", "name": "Yes", "price": 21.0}],
            ),
            {
                "key": "unibet",
                "markets": [
                    {
                        "key": "player_last_goal_scorer",
                        "outcomes": [
                            {
                                "description": "Jake Bidwell",
                                "name": "Yes",
                                "price": 1.99,
                            }
                        ],
                    }
                ],
            },
        )
    )

    (row,) = rows
    assert row.last_goal is None
    assert row.anytime_goal is not None


def test_a_first_scorer_price_below_the_anytime_price_is_kept() -> None:
    rows = read_event(
        _event(
            _book(
                "bet365",
                "player_goal_scorer_anytime",
                [{"description": "Kai Havertz", "name": "Yes", "price": 2.5}],
            ),
            {
                "key": "unibet",
                "markets": [
                    {
                        "key": "player_first_goal_scorer",
                        "outcomes": [
                            {
                                "description": "Kai Havertz",
                                "name": "Yes",
                                "price": 9.0,
                            }
                        ],
                    }
                ],
            },
        )
    )

    (row,) = rows
    assert row.anytime_goal == pytest.approx(0.4)
    assert row.first_goal == pytest.approx(1 / 9.0, rel=1e-6)


def test_a_first_scorer_price_with_no_anytime_beside_it_is_left_alone() -> None:
    """Nothing to compare against is not evidence that the quote is wrong."""
    rows = read_event(
        _event(
            {
                "key": "unibet",
                "markets": [
                    {
                        "key": "player_first_goal_scorer",
                        "outcomes": [
                            {
                                "description": "Kai Havertz",
                                "name": "Yes",
                                "price": 9.0,
                            }
                        ],
                    }
                ],
            }
        )
    )

    (row,) = rows
    assert row.anytime_goal is None
    assert row.first_goal == pytest.approx(1 / 9.0, rel=1e-6)
