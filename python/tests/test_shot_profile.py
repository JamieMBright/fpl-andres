"""Shot volume repeats; shot quality mostly does not.

Measured on four Understat seasons, players with 900+ minutes in both: volume
correlates 0.890 year to year, npxG/90 0.860, quality only 0.455. But quality
is not noise - discarding it for the league mean raises MAE from 0.0561 to
0.0666. Shrinking it by shot count wins, optimum near ten shots of prior.
"""

from __future__ import annotations

import unittest

from fpl_andres.models.shot_profile import (
    ShotProfileUnavailable,
    league_shot_quality,
    shot_profile,
)

LEAGUE_QUALITY = 0.1093  # measured pooled npxG per shot, 2022-23 to 2025-26


def _profile(shots: int, npxg: float, minutes: int = 2700, **kwargs):
    return shot_profile(
        shots=shots,
        minutes=minutes,
        non_penalty_expected_goals=npxg,
        league_quality=LEAGUE_QUALITY,
        **kwargs,
    )


class LeagueQualityTest(unittest.TestCase):
    def test_pooled_not_averaged_per_player(self) -> None:
        """A four-shot fringe player must not move the league rate."""
        pooled = league_shot_quality([(10.0, 100), (1.0, 4)])

        self.assertAlmostEqual(pooled, 11.0 / 104)

    def test_no_shots_is_refused(self) -> None:
        with self.assertRaises(ShotProfileUnavailable):
            league_shot_quality([(0.0, 0)])


class ShrinkageTest(unittest.TestCase):
    def test_a_thin_hot_record_is_pulled_toward_the_league(self) -> None:
        """Five shots at elite quality is five shots, not elite quality."""
        thin = _profile(shots=5, npxg=1.5)

        self.assertLess(thin.expected_goals_per_shot, thin.raw_expected_goals_per_shot)
        self.assertLess(thin.quality_weight, 0.5)

    def test_a_heavy_record_keeps_its_own_quality(self) -> None:
        heavy = _profile(shots=120, npxg=18.0)

        self.assertGreater(heavy.quality_weight, 0.9)
        self.assertAlmostEqual(
            heavy.expected_goals_per_shot, heavy.raw_expected_goals_per_shot, places=2
        )

    def test_shrinkage_is_not_a_one_way_discount(self) -> None:
        cold = _profile(shots=5, npxg=0.1)

        self.assertGreater(cold.expected_goals_per_shot, cold.raw_expected_goals_per_shot)

    def test_expected_goals_per_90_is_volume_times_quality(self) -> None:
        profile = _profile(shots=90, npxg=10.0, minutes=2700)

        self.assertAlmostEqual(profile.shots_per_90, 3.0)
        self.assertAlmostEqual(
            profile.expected_goals_per_90,
            profile.shots_per_90 * profile.expected_goals_per_shot,
        )

    def test_a_player_who_never_shoots_falls_back_to_league_quality(self) -> None:
        silent = _profile(shots=0, npxg=0.0)

        self.assertEqual(silent.shots_per_90, 0.0)
        self.assertEqual(silent.expected_goals_per_shot, LEAGUE_QUALITY)
        self.assertEqual(silent.expected_goals_per_90, 0.0)


class VolumeRegressionTest(unittest.TestCase):
    def test_volume_is_untouched_without_a_league_rate(self) -> None:
        profile = _profile(shots=90, npxg=10.0, minutes=2700)

        self.assertAlmostEqual(profile.shots_per_90, 3.0)

    def test_volume_regresses_toward_the_league_when_given_one(self) -> None:
        profile = _profile(shots=90, npxg=10.0, minutes=2700, league_shots_per_90=1.0)

        self.assertAlmostEqual(profile.shots_per_90, 0.9 * 3.0 + 0.1 * 1.0)


class RefusalTest(unittest.TestCase):
    def test_no_minutes_is_refused_rather_than_dividing_by_zero(self) -> None:
        with self.assertRaises(ShotProfileUnavailable):
            _profile(shots=10, npxg=1.0, minutes=0)

    def test_negative_shots_are_refused(self) -> None:
        with self.assertRaises(ShotProfileUnavailable):
            _profile(shots=-1, npxg=1.0)

    def test_a_league_quality_of_zero_is_refused(self) -> None:
        with self.assertRaises(ShotProfileUnavailable):
            shot_profile(
                shots=10,
                minutes=900,
                non_penalty_expected_goals=1.0,
                league_quality=0.0,
            )


if __name__ == "__main__":
    unittest.main()
