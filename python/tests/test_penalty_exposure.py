"""Projecting from total xG quietly assumes a player keeps the penalty duty.

Measured on 2025-26: penalties are 5.9% of league xG, but 44.5% of Cole
Palmer's and 38.3% of Bruno Fernandes's, and 24 regulars sit above 15%. Losing
the duty would cost Palmer 0.205 xG a 90, about 0.82 FPL points a 90.
"""

from __future__ import annotations

import unittest

from fpl_andres.models.penalties import PenaltySplitUnavailable, penalty_exposure

FORWARD_GOAL_POINTS = 4


def _palmer():
    """Cole Palmer's real 2025-26 line, rounded to the reported figures."""
    return penalty_exposure(
        expected_goals=10.26,
        non_penalty_expected_goals=5.69,
        goals=9,
        non_penalty_goals=3,
        minutes=2005,
    )


class SplitTest(unittest.TestCase):
    def test_penalty_xg_is_the_difference(self) -> None:
        self.assertAlmostEqual(_palmer().penalty_expected_goals, 4.57, places=2)

    def test_share_matches_the_measured_figure(self) -> None:
        self.assertAlmostEqual(_palmer().share, 0.445, places=2)

    def test_penalties_scored_comes_from_exact_goal_counts(self) -> None:
        """Derived from integers, so it needs no assumed xG per penalty."""
        self.assertEqual(_palmer().penalties_scored, 6)

    def test_points_at_risk_scales_with_position(self) -> None:
        exposure = _palmer()
        per_ninety = exposure.expected_goals_at_risk_per_90()

        self.assertAlmostEqual(per_ninety, 0.205, places=2)
        self.assertAlmostEqual(
            exposure.points_at_risk_per_90(FORWARD_GOAL_POINTS),
            per_ninety * FORWARD_GOAL_POINTS,
        )

    def test_a_player_who_takes_none_is_unexposed(self) -> None:
        exposure = penalty_exposure(
            expected_goals=8.0,
            non_penalty_expected_goals=8.0,
            goals=7,
            non_penalty_goals=7,
            minutes=2700,
        )

        self.assertEqual(exposure.share, 0.0)
        self.assertEqual(exposure.penalties_scored, 0)
        self.assertEqual(exposure.points_at_risk_per_90(FORWARD_GOAL_POINTS), 0.0)


class RefusalTest(unittest.TestCase):
    def test_a_contradictory_split_is_refused_not_clamped(self) -> None:
        with self.assertRaises(PenaltySplitUnavailable):
            penalty_exposure(
                expected_goals=5.0,
                non_penalty_expected_goals=6.0,
                goals=4,
                non_penalty_goals=4,
                minutes=900,
            )

    def test_more_open_play_goals_than_goals_is_refused(self) -> None:
        with self.assertRaises(PenaltySplitUnavailable):
            penalty_exposure(
                expected_goals=5.0,
                non_penalty_expected_goals=4.0,
                goals=3,
                non_penalty_goals=4,
                minutes=900,
            )

    def test_negative_inputs_are_refused(self) -> None:
        with self.assertRaises(PenaltySplitUnavailable):
            penalty_exposure(
                expected_goals=-1.0,
                non_penalty_expected_goals=0.0,
                goals=0,
                non_penalty_goals=0,
                minutes=900,
            )

    def test_no_minutes_means_no_per_90_rather_than_a_divide_by_zero(self) -> None:
        exposure = penalty_exposure(
            expected_goals=0.0,
            non_penalty_expected_goals=0.0,
            goals=0,
            non_penalty_goals=0,
            minutes=0,
        )

        self.assertEqual(exposure.expected_goals_at_risk_per_90(), 0.0)
        self.assertEqual(exposure.share, 0.0)


if __name__ == "__main__":
    unittest.main()
