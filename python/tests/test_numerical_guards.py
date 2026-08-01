"""Numerical guards that were asserted rather than measured.

Four sentinels and constants in the statistical layer that behaved worse than
their comments claimed. Each test below pins the corrected behaviour against a
number, not against a promise.
"""

from __future__ import annotations

import math
import unittest

from scipy.stats import poisson

from fpl_andres.models.expected_points import (
    _expected_floor_divide,
    _poisson_truncation,
)
from fpl_andres.models.promotion import _quantile


class PoissonTruncationTest(unittest.TestCase):
    def test_the_cut_grows_with_the_rate(self) -> None:
        """A fixed cut generous at rate 1 is severe at rate 20."""
        self.assertLess(_poisson_truncation(1.0), _poisson_truncation(20.0))

    def test_the_tail_left_behind_is_negligible_at_every_realistic_rate(self) -> None:
        for rate in (0.5, 3.0, 7.0, 9.0, 14.0, 18.0, 20.0):
            with self.subTest(rate=rate):
                tail = 1.0 - poisson.cdf(_poisson_truncation(rate), rate)
                self.assertLess(tail, 1e-12)

    def test_the_old_flat_cut_was_not_negligible(self) -> None:
        """Recorded so the regression is recognisable if it returns."""
        self.assertGreater(1.0 - poisson.cdf(15, 14.0), 0.3)
        self.assertGreater(1.0 - poisson.cdf(15, 20.0), 0.8)

    def test_a_busy_keeper_no_longer_loses_points_to_the_tail(self) -> None:
        exact = sum((k // 3) * poisson.pmf(k, 14.0) for k in range(0, 300))

        self.assertAlmostEqual(_expected_floor_divide(14.0, 3), exact, places=9)

    def test_a_low_rate_is_unchanged(self) -> None:
        exact = sum((k // 3) * poisson.pmf(k, 1.5) for k in range(0, 300))

        self.assertAlmostEqual(_expected_floor_divide(1.5, 3), exact, places=11)

    def test_a_zero_rate_pays_nothing(self) -> None:
        self.assertEqual(_expected_floor_divide(0.0, 3), 0.0)


class QuantileTest(unittest.TestCase):
    def test_it_interpolates_between_order_statistics(self) -> None:
        self.assertAlmostEqual(_quantile([0.0, 1.0], 0.5), 0.5)

    def test_the_ends_are_the_extremes(self) -> None:
        ordered = [1.0, 2.0, 3.0, 4.0]

        self.assertEqual(_quantile(ordered, 0.0), 1.0)
        self.assertEqual(_quantile(ordered, 1.0), 4.0)

    def test_one_sample_is_its_own_quantile(self) -> None:
        self.assertEqual(_quantile([7.0], 0.975), 7.0)

    def test_an_empty_sample_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _quantile([], 0.5)

    def test_it_no_longer_snaps_inward_on_a_small_resample_count(self) -> None:
        """The old ceil(f*n)-1 indexing biased the bound toward the middle."""
        ordered = [float(index) for index in range(200)]
        old_upper = ordered[min(199, math.ceil(0.975 * 200) - 1)]

        self.assertGreater(_quantile(ordered, 0.975), old_upper)

    def test_the_interval_is_ordered(self) -> None:
        ordered = [float(index) for index in range(100)]

        self.assertLess(_quantile(ordered, 0.025), _quantile(ordered, 0.975))


if __name__ == "__main__":
    unittest.main()
