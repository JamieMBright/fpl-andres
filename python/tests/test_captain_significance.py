"""Whether a captaincy thesis beat the incumbent, or topped a table by luck.

Ten policies over about 127 gameweeks is ten chances to win by accident, and
the first run proved the risk was real: one arithmetic fix moved `template`
from last to first. These tests pin the properties that make the interval
trustworthy -- above all that the comparison is paired, because every policy
captains in the same weeks and an unpaired test would charge a shortlist-wide
blank to whoever was sampled into it.
"""

from __future__ import annotations

import pytest

from fpl_andres.backtesting.captain_significance import MINIMUM_WEEKS, compare_policies

_WEEKS = MINIMUM_WEEKS


def _flat(value: int) -> list[int]:
    return [value] * _WEEKS


class TestTheVerdict:
    def test_a_policy_that_always_scores_more_is_called_better(self) -> None:
        verdicts = compare_policies(
            {"expected_points": _flat(5), "candidate": _flat(8)},
            resamples=200,
        )

        assert len(verdicts) == 1
        assert verdicts[0].better
        assert verdicts[0].improvement == pytest.approx(3.0)
        assert verdicts[0].lower > 0

    def test_a_policy_that_always_scores_less_is_not(self) -> None:
        verdicts = compare_policies(
            {"expected_points": _flat(8), "candidate": _flat(5)},
            resamples=200,
        )

        assert not verdicts[0].better
        assert verdicts[0].improvement == pytest.approx(-3.0)

    def test_a_captain_who_lost_points_is_scored_rather_than_refused(self) -> None:
        # This is what broke the first CI run. A red card is -3 and an own goal
        # -2, so a captain's return goes negative, and the promotion primitive
        # refuses a negative row because its own metrics are error magnitudes.
        # Both series are lifted by one constant, which the paired difference
        # cannot see, and the means are reported unlifted.
        baseline = _flat(5)
        candidate = _flat(5)
        baseline[0] = -3
        candidate[0] = 4

        verdicts = compare_policies(
            {"expected_points": baseline, "candidate": candidate},
            resamples=200,
        )

        assert verdicts[0].baseline_mean == pytest.approx(sum(baseline) / _WEEKS)
        assert verdicts[0].mean == pytest.approx(sum(candidate) / _WEEKS)
        assert verdicts[0].improvement == pytest.approx(7 / _WEEKS)

    def test_lifting_every_week_by_a_constant_changes_no_verdict(self) -> None:
        # The shift is exact, not an approximation, so the interval measured on
        # a series containing a red card must equal the one measured after the
        # whole series is moved into positive territory by hand.
        baseline = [-3, *_flat(5)[1:]]
        candidate = [4, *_flat(6)[1:]]
        signed = compare_policies(
            {"expected_points": baseline, "candidate": candidate},
            resamples=200,
        )[0]
        lifted = compare_policies(
            {
                "expected_points": [value + 10 for value in baseline],
                "candidate": [value + 10 for value in candidate],
            },
            resamples=200,
        )[0]

        assert signed.improvement == pytest.approx(lifted.improvement)
        assert signed.lower == pytest.approx(lifted.lower)
        assert signed.upper == pytest.approx(lifted.upper)
        assert signed.better == lifted.better

    def test_an_identical_policy_is_not_an_improvement(self) -> None:
        verdicts = compare_policies(
            {"expected_points": _flat(6), "candidate": _flat(6)},
            resamples=200,
        )

        assert not verdicts[0].better
        assert verdicts[0].improvement == pytest.approx(0.0)

    def test_a_noisy_edge_does_not_clear_the_bar(self) -> None:
        # The shape of the real result: a small mean gap inside a wide spread,
        # where the candidate wins some weeks and loses others. Sorting a table
        # would call this a winner. Measured, not guessed: this pair means 5.50
        # against 5.75, and the interval runs -0.44 to +0.94.
        baseline = [0, 14, 12, 0, 2, 9, 6, 1] * 4
        candidate = [2, 11, 14, 0, 0, 11, 5, 3] * 4
        verdicts = compare_policies(
            {"expected_points": baseline, "candidate": candidate},
            resamples=400,
        )

        assert verdicts[0].improvement == pytest.approx(0.25)
        assert verdicts[0].lower < 0
        assert not verdicts[0].better
        assert "ci_includes_zero" in verdicts[0].reason_codes

    def test_the_baseline_is_not_compared_against_itself(self) -> None:
        verdicts = compare_policies(
            {"expected_points": _flat(5), "a": _flat(6), "b": _flat(7)},
            resamples=200,
        )

        assert {verdict.label for verdict in verdicts} == {"a", "b"}

    def test_the_strongest_gap_is_reported_first(self) -> None:
        verdicts = compare_policies(
            {"expected_points": _flat(5), "small": _flat(6), "large": _flat(9)},
            resamples=200,
        )

        assert [verdict.label for verdict in verdicts] == ["large", "small"]


class TestTheComparisonIsSound:
    def test_a_policy_scored_on_different_weeks_is_refused_not_truncated(self) -> None:
        # Trimming would compare two different populations and call it a
        # comparison.
        with pytest.raises(ValueError, match="cannot be paired"):
            compare_policies(
                {"expected_points": _flat(5), "short": _flat(5)[:10]},
                resamples=200,
            )

    def test_a_missing_baseline_is_refused(self) -> None:
        with pytest.raises(KeyError, match="not among the scored policies"):
            compare_policies({"a": _flat(5)}, resamples=200)

    def test_under_a_season_of_weeks_nothing_is_promoted(self) -> None:
        # The sample floor is the promotion gate's, and it executes no
        # resamples rather than reporting a confident interval over ten weeks.
        verdicts = compare_policies(
            {"expected_points": [5] * 10, "candidate": [9] * 10},
            resamples=200,
        )

        assert not verdicts[0].better
        assert "insufficient_sample" in verdicts[0].reason_codes

    def test_the_comparison_is_paired_not_pooled(self) -> None:
        # Both policies total the same, so an unpaired test sees a tie. Paired,
        # the week-by-week differences are what the interval is built from, and
        # they are not all zero. Pooling would throw that away.
        baseline = [0, 10] * (_WEEKS // 2)
        candidate = [1, 9] * (_WEEKS // 2)
        verdicts = compare_policies(
            {"expected_points": baseline, "candidate": candidate},
            resamples=400,
        )

        assert sum(baseline) == sum(candidate)
        assert verdicts[0].improvement == pytest.approx(0.0)
        # Pooled, the weekly differences would vanish. Paired, they are +1 and
        # -1 alternating, so the interval keeps real width around zero.
        assert verdicts[0].lower < 0 < verdicts[0].upper
        assert not verdicts[0].better
