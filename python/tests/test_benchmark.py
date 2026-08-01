"""A rival model is the strongest validation available, and may not flatter us.

Both models must be scored on the same players against the same realised points,
or the comparison is theatre. This asserts the harness refuses the ways that go
wrong rather than quietly producing a number.

The rival column cannot be fetched here: FPL Review's robots.txt carries
`User-agent: ClaudeBot / Disallow: /` and `Content-Signal: ai-train=no`, and
fplkiwi.com does not resolve. It arrives from the owner.
"""

from __future__ import annotations

import unittest

from fpl_andres.models.benchmark import BenchmarkUnavailable, compare_projections

CODES = list(range(1, 41))


def _sets(shift_ours: float = 0.0, shift_theirs: float = 0.0):
    actual = {code: float(code % 11) for code in CODES}
    ours = {code: actual[code] + shift_ours for code in CODES}
    theirs = {code: actual[code] + shift_theirs for code in CODES}
    return ours, theirs, actual


class PopulationTest(unittest.TestCase):
    def test_only_the_intersection_is_scored(self) -> None:
        ours, theirs, actual = _sets()
        ours[999] = 50.0  # a player the rival never rated

        comparison = compare_projections(ours=ours, theirs=theirs, actual=actual)

        self.assertEqual(comparison.players, len(CODES))

    def test_too_small_an_overlap_is_refused(self) -> None:
        ours, theirs, actual = _sets()
        trimmed = {code: theirs[code] for code in CODES[:5]}

        with self.assertRaises(BenchmarkUnavailable):
            compare_projections(ours=ours, theirs=trimmed, actual=actual)

    def test_a_flat_projection_is_refused_rather_than_ranked(self) -> None:
        _, theirs, actual = _sets()
        flat = dict.fromkeys(CODES, 4.0)

        with self.assertRaises(BenchmarkUnavailable):
            compare_projections(ours=flat, theirs=theirs, actual=actual)


class ScoringTest(unittest.TestCase):
    def test_a_perfect_projection_scores_perfectly(self) -> None:
        ours, theirs, actual = _sets()

        comparison = compare_projections(ours=ours, theirs=theirs, actual=actual)

        self.assertAlmostEqual(comparison.ours.mean_absolute_error, 0.0)
        self.assertAlmostEqual(comparison.ours.spearman, 1.0)
        self.assertAlmostEqual(comparison.ours.bias, 0.0)

    def test_the_closer_model_wins_and_the_gap_is_signed(self) -> None:
        ours, theirs, actual = _sets(shift_ours=0.5, shift_theirs=2.0)

        comparison = compare_projections(ours=ours, theirs=theirs, actual=actual)

        self.assertTrue(comparison.we_win)
        self.assertAlmostEqual(comparison.error_gap, 0.5 - 2.0)

    def test_losing_is_reported_as_losing(self) -> None:
        ours, theirs, actual = _sets(shift_ours=3.0, shift_theirs=0.25)

        comparison = compare_projections(ours=ours, theirs=theirs, actual=actual)

        self.assertFalse(comparison.we_win)
        self.assertGreater(comparison.error_gap, 0.0)

    def test_bias_keeps_its_sign(self) -> None:
        ours, theirs, actual = _sets(shift_ours=-1.5)

        comparison = compare_projections(ours=ours, theirs=theirs, actual=actual)

        self.assertAlmostEqual(comparison.ours.bias, -1.5)

    def test_a_constant_offset_does_not_move_the_ranking(self) -> None:
        """MAE punishes an offset; rank correlation should not."""
        ours, theirs, actual = _sets(shift_ours=5.0)

        comparison = compare_projections(ours=ours, theirs=theirs, actual=actual)

        self.assertAlmostEqual(comparison.ours.spearman, 1.0)
        self.assertAlmostEqual(comparison.ours.mean_absolute_error, 5.0)

    def test_ties_do_not_distort_the_rank_correlation(self) -> None:
        _, theirs, actual = _sets()
        ours = {code: float(code % 2) for code in CODES}

        comparison = compare_projections(ours=ours, theirs=theirs, actual=actual)

        self.assertLess(abs(comparison.ours.spearman), 1.0)

    def test_top_n_hit_rate_is_a_share_of_the_truly_best(self) -> None:
        ours, theirs, actual = _sets()

        comparison = compare_projections(ours=ours, theirs=theirs, actual=actual, top_n=10)

        self.assertEqual(comparison.top_n, 10)
        self.assertAlmostEqual(comparison.ours.top_n_hit_rate, 1.0)

    def test_a_nonsense_top_n_is_refused(self) -> None:
        ours, theirs, actual = _sets()

        with self.assertRaises(BenchmarkUnavailable):
            compare_projections(ours=ours, theirs=theirs, actual=actual, top_n=0)


if __name__ == "__main__":
    unittest.main()
