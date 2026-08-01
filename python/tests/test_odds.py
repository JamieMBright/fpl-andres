"""Quoted prices are not probabilities, and the obvious repair is the wrong one.

The reciprocals of decimal odds sum to more than one because the excess is the
bookmaker's income. Dividing through by the total assumes that margin sits
evenly across outcomes. It does not: longshots carry more of it. That bias runs
straight into the cheap differential punts FPL rewards, so it is the one method
not to use.
"""

from __future__ import annotations

import math
import unittest

from fpl_andres.models.odds import (
    OddsUnavailable,
    clean_sheet_probability,
    devig_power,
    devig_proportional,
    devig_shin,
    implied_probabilities,
    overround,
)

# A plausible 1X2 book: short home favourite, long away side.
MATCH = (1.40, 5.00, 8.50)
# A near-even two-way market, where every method should almost agree.
EVEN = (1.95, 1.95)


class MarketTest(unittest.TestCase):
    def test_raw_reciprocals_sum_above_one(self) -> None:
        raw = implied_probabilities(MATCH)

        self.assertGreater(sum(raw), 1.0)

    def test_overround_is_the_excess(self) -> None:
        self.assertAlmostEqual(overround(MATCH), sum(implied_probabilities(MATCH)) - 1.0)
        self.assertGreater(overround(MATCH), 0.0)

    def test_a_market_that_does_not_pay_the_bookmaker_is_refused(self) -> None:
        with self.assertRaises(OddsUnavailable):
            overround((3.0, 3.0, 3.0))

    def test_odds_at_or_below_evens_are_refused(self) -> None:
        for bad in ((1.0, 2.0), (0.5, 3.0), (-2.0, 3.0)):
            with self.subTest(bad=bad), self.assertRaises(OddsUnavailable):
                implied_probabilities(bad)

    def test_a_single_outcome_is_not_a_market(self) -> None:
        with self.assertRaises(OddsUnavailable):
            implied_probabilities((1.5,))


class NormalisationTest(unittest.TestCase):
    def test_every_method_returns_a_distribution(self) -> None:
        for method in (devig_proportional, devig_power, devig_shin):
            with self.subTest(method=method.__name__):
                probabilities = method(MATCH)
                self.assertAlmostEqual(sum(probabilities), 1.0, places=9)
                self.assertTrue(all(0.0 < p < 1.0 for p in probabilities))

    def test_every_method_keeps_the_favourite_favourite(self) -> None:
        for method in (devig_proportional, devig_power, devig_shin):
            with self.subTest(method=method.__name__):
                probabilities = method(MATCH)
                self.assertEqual(list(probabilities), sorted(probabilities, reverse=True))

    def test_a_symmetric_market_is_split_evenly(self) -> None:
        for method in (devig_proportional, devig_power, devig_shin):
            with self.subTest(method=method.__name__):
                first, second = method(EVEN)
                self.assertAlmostEqual(first, 0.5, places=6)
                self.assertAlmostEqual(second, 0.5, places=6)


class FavouriteLongshotTest(unittest.TestCase):
    def test_proportional_prices_the_longshot_higher_than_the_alternatives(self) -> None:
        """The whole reason not to use it."""
        longshot = -1
        proportional = devig_proportional(MATCH)[longshot]

        self.assertGreater(proportional, devig_power(MATCH)[longshot])
        self.assertGreater(proportional, devig_shin(MATCH)[longshot])

    def test_proportional_prices_the_favourite_lower(self) -> None:
        favourite = 0
        proportional = devig_proportional(MATCH)[favourite]

        self.assertLess(proportional, devig_power(MATCH)[favourite])
        self.assertLess(proportional, devig_shin(MATCH)[favourite])

    def test_longshot_overpricing_worsens_as_the_market_gets_lopsided(self) -> None:
        """Measured as a ratio, not a difference.

        The absolute gap does not widen, because an extreme longshot's
        probability is tiny to begin with. The proportional overpricing does:
        2.7% in a mild market, 4.8% in a medium one, 20.8% in an extreme one.
        """

        def overpricing(market: tuple[float, ...]) -> float:
            return devig_proportional(market)[-1] / devig_shin(market)[-1]

        mild = overpricing((1.80, 3.60, 4.20))
        medium = overpricing((1.40, 5.00, 8.50))
        extreme = overpricing((1.10, 12.0, 30.0))

        self.assertAlmostEqual(mild, 1.027, places=2)
        self.assertAlmostEqual(extreme, 1.208, places=2)
        self.assertLess(mild, medium)
        self.assertLess(medium, extreme)


class CleanSheetTest(unittest.TestCase):
    def test_a_clean_sheet_is_the_poisson_zero(self) -> None:
        self.assertAlmostEqual(clean_sheet_probability(1.2), math.exp(-1.2))

    def test_a_goalless_opponent_never_scores(self) -> None:
        self.assertEqual(clean_sheet_probability(0.0), 1.0)

    def test_a_stronger_opponent_lowers_the_chance(self) -> None:
        self.assertLess(clean_sheet_probability(2.4), clean_sheet_probability(0.8))

    def test_a_negative_expectation_is_refused(self) -> None:
        with self.assertRaises(OddsUnavailable):
            clean_sheet_probability(-0.1)

    def test_an_infinite_expectation_is_refused(self) -> None:
        with self.assertRaises(OddsUnavailable):
            clean_sheet_probability(float("inf"))


if __name__ == "__main__":
    unittest.main()
