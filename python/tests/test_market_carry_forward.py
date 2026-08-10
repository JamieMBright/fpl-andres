"""A bookmaker's price is about one fixture. The route it feeds is not.

A book quotes a striker to score against the champions and quotes the same
striker to score against a promoted side, and the two numbers are miles apart
for reasons that have nothing to do with him. This artifact publishes a route
against an average opponent and lets the browser bend it by whichever gameweek
is being read, so a quote has to have its own fixture divided back out before it
can be published -- otherwise the opponent is applied twice.

The property that follows is the one worth pinning: the best-priced scorer in a
hard week is still the best-priced scorer in an easy week, only at a bigger
number. These assert it arithmetically rather than trusting the comment.
"""

from __future__ import annotations

import unittest
from datetime import date

from fpl_andres.cli.publish_season_inputs import _market_attacking
from fpl_andres.models.market_routes import market_attack

FORWARD = 4
#: Two gameweeks: a hard one where a striker is expected to do less, and an easy
#: one where he is expected to do more.
MULTIPLIERS = [0.70, 1.40]
HARD = date(2026, 8, 22)
EASY = date(2026, 8, 29)
SLOTS = {HARD: 0, EASY: 1}
#: The market's view alone, so the de-fixturing is not hidden behind a blend.
ALL_MARKET = 1.0
RECORD = {"expectedGoals": 0.30, "expectedAssists": 0.20}


def route(
    *,
    goal: float | None = 0.30,
    assist: float | None = 0.15,
    quoted_on: date = HARD,
    weight: float = ALL_MARKET,
) -> float | None:
    return _market_attacking(
        (market_attack(goal, assist), quoted_on),
        FORWARD,
        RECORD,
        MULTIPLIERS,
        SLOTS,
        weight,
    )


class TheFixtureIsDividedBackOut(unittest.TestCase):
    def test_the_same_price_says_more_about_a_man_facing_the_harder_week(self) -> None:
        # An identical quote is a better footballer if the opponent was worse
        # for him. Publishing the price as-is would have said they were equal.
        assert route(quoted_on=HARD) > route(quoted_on=EASY)  # type: ignore[operator]

    def test_the_gap_is_exactly_the_ratio_of_the_two_fixtures(self) -> None:
        hard = route(quoted_on=HARD)
        easy = route(quoted_on=EASY)
        assert hard is not None and easy is not None

        self.assertAlmostEqual(hard / easy, MULTIPLIERS[1] / MULTIPLIERS[0], places=9)

    def test_the_best_priced_scorer_stays_the_best_priced_scorer(self) -> None:
        # The reader's question, in one assertion. A striker quoted better in a
        # hard week must not be overtaken by a worse-quoted striker whose only
        # advantage is an easy week.
        better_in_a_hard_week = route(goal=0.30, quoted_on=HARD)
        worse_in_an_easy_week = route(goal=0.40, quoted_on=EASY)
        assert better_in_a_hard_week is not None
        assert worse_in_an_easy_week is not None

        # 0.30 against a 0.70 fixture is a rate of 0.51 an average match;
        # 0.40 against a 1.40 fixture is 0.36. The harder week wins.
        assert better_in_a_hard_week > worse_in_an_easy_week

    def test_an_ordering_survives_the_week_it_was_quoted_in(self) -> None:
        # Two men quoted identically in different weeks are ranked by their
        # fixtures; two men quoted differently in the SAME week are ranked by
        # their prices, and nothing else moves.
        cheap = route(goal=0.20, quoted_on=EASY)
        dear = route(goal=0.35, quoted_on=EASY)
        assert cheap is not None and dear is not None

        assert dear > cheap


class WhereItRefusesToSpeak(unittest.TestCase):
    def test_a_quote_on_a_day_with_no_gameweek_is_dropped(self) -> None:
        assert route(quoted_on=date(2026, 12, 25)) is None

    def test_a_blank_gameweek_divides_by_nothing_and_is_dropped(self) -> None:
        blank = date(2026, 9, 5)
        assert (
            _market_attacking(
                (market_attack(0.30, 0.15), blank),
                FORWARD,
                RECORD,
                [*MULTIPLIERS, 0.0],
                {**SLOTS, blank: 2},
                ALL_MARKET,
            )
            is None
        )

    def test_silence_from_the_book_leaves_the_record_standing(self) -> None:
        assert _market_attacking(None, FORWARD, RECORD, MULTIPLIERS, SLOTS, ALL_MARKET) is None

    def test_a_projection_with_no_attacking_rates_is_refused_not_ignored(self) -> None:
        # Returning None here would read as "the book said nothing" and hide a
        # stale artifact behind a plausible number.
        with self.assertRaises(ValueError):
            _market_attacking(
                (market_attack(0.30, 0.15), HARD),
                FORWARD,
                {},
                MULTIPLIERS,
                SLOTS,
                ALL_MARKET,
            )


class TheBlendIsWhatDecidesHowMuchOfItLands(unittest.TestCase):
    def test_a_weight_of_nothing_leaves_the_record_untouched(self) -> None:
        recorded = route(weight=0.0)
        assert recorded is not None

        # Both fixtures give the same answer, because neither is being read.
        self.assertAlmostEqual(recorded, route(quoted_on=EASY, weight=0.0) or 0.0, places=9)

    def test_a_partial_weight_lands_between_the_two(self) -> None:
        recorded = route(weight=0.0)
        market = route(weight=1.0)
        half = route(weight=0.5)
        assert recorded is not None and market is not None and half is not None

        assert min(recorded, market) < half < max(recorded, market)
