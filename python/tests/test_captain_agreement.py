"""Agreement is a description of the cohort, not a score, and has to stay one.

The failure this file exists to prevent is a reader — or a future version of
this project — reading a high agreement rate as evidence a thesis is good. The
tests below pin the three things that keep the number honest: unanimous weeks
are identified and set aside, a tie has no winner, and a missing pick is not a
miss.
"""

from __future__ import annotations

import pytest

from fpl_andres.cohorts.captain_agreement import (
    SPLIT_THRESHOLD,
    CohortWeek,
    score_agreement,
)


def _week(event: int, shares: dict[int, float], counted: int = 500) -> CohortWeek:
    return CohortWeek(event=event, counted=counted, share_by_element=shares)


class TestTheCohortWeek:
    def test_the_modal_captain_is_the_plurality_not_the_majority(self) -> None:
        # Nobody has half the cohort, but 40% is still the answer to "who did
        # they captain". Requiring a majority would blank most real weeks.
        week = _week(5, {11: 0.40, 22: 0.35, 33: 0.25})
        assert week.modal_captain == 11

    def test_a_tie_has_no_modal_captain(self) -> None:
        # Breaking the tie by element id would score one thesis as agreeing
        # with a cohort that did not agree with itself.
        assert _week(5, {11: 0.4, 22: 0.4, 33: 0.2}).modal_captain is None

    def test_an_empty_week_has_no_modal_captain(self) -> None:
        assert _week(5, {}).modal_captain is None
        assert _week(5, {}).unanimity == 0.0

    def test_a_near_unanimous_week_is_not_a_contested_one(self) -> None:
        # 85% on one player: every sensible thesis picks him, so the week
        # separates nothing and inflates every rate equally.
        week = _week(5, {11: 0.85, 22: 0.10, 33: 0.05})
        assert week.unanimity == pytest.approx(0.85)
        assert not week.is_split

    def test_the_split_threshold_is_the_boundary_not_a_strict_one(self) -> None:
        # Exactly at the threshold counts as contested: half the cohort went
        # elsewhere, which is information.
        assert _week(5, {11: SPLIT_THRESHOLD, 22: 0.5}).is_split


class TestScoreAgreement:
    def _cohort(self) -> list[CohortWeek]:
        return [
            # Two near-unanimous weeks, then two genuinely contested ones.
            _week(1, {11: 0.90, 22: 0.10}),
            _week(2, {11: 0.88, 33: 0.12}),
            _week(3, {22: 0.40, 33: 0.35, 44: 0.25}),
            _week(4, {33: 0.45, 22: 0.30, 44: 0.25}),
        ]

    def test_a_thesis_that_only_wins_the_easy_weeks_is_ranked_below_one_that_does_not(
        self,
    ) -> None:
        # `obvious` agrees on both unanimous weeks and neither contested one:
        # 50% overall. `contested` agrees on neither unanimous week and both
        # contested ones: also 50% overall. Ranking on the overall rate would
        # call that a tie, and it is not one -- only `contested` said anything
        # the cohort did not already agree on.
        results = score_agreement(
            {
                "obvious": {1: 11, 2: 11, 3: 44, 4: 44},
                "contested": {1: 22, 2: 33, 3: 22, 4: 33},
            },
            self._cohort(),
        )
        assert [entry.label for entry in results] == ["contested", "obvious"]
        assert results[0].modal_rate == pytest.approx(0.5)
        assert results[1].modal_rate == pytest.approx(0.5)
        assert results[0].split_modal_rate == pytest.approx(1.0)
        assert results[1].split_modal_rate == pytest.approx(0.0)

    def test_only_the_contested_weeks_are_counted_as_contested(self) -> None:
        results = score_agreement({"any": {1: 11, 2: 11, 3: 22, 4: 33}}, self._cohort())
        assert results[0].weeks == 4
        assert results[0].split_weeks == 2

    def test_a_near_miss_scores_above_a_miss(self) -> None:
        # Both agree with the plurality in zero weeks. One picked the cohort's
        # second choice every time and the other picked its last. A modal rate
        # alone reports those as identical.
        results = score_agreement(
            {
                "second": {3: 33, 4: 22},
                "last": {3: 44, 4: 44},
            },
            self._cohort(),
        )
        by_label = {entry.label: entry for entry in results}
        assert by_label["second"].modal_rate == 0.0
        assert by_label["last"].modal_rate == 0.0
        assert by_label["second"].mean_share == pytest.approx(0.325)
        assert by_label["last"].mean_share == pytest.approx(0.25)

    def test_a_week_with_no_pick_is_skipped_rather_than_scored_as_wrong(self) -> None:
        # A blank gameweek can leave a thesis with nothing to pick. Counting
        # that as a miss grades the fixture list, not the thesis.
        results = score_agreement({"partial": {3: 22}}, self._cohort())
        assert results[0].weeks == 1
        assert results[0].modal_rate == pytest.approx(1.0)

    def test_a_pick_for_an_uncaptured_gameweek_is_skipped(self) -> None:
        results = score_agreement({"early": {1: 11, 99: 11}}, self._cohort())
        assert results[0].weeks == 1

    def test_a_thesis_with_no_overlapping_week_is_left_out_entirely(self) -> None:
        # Not reported as zero: zero agreement and no measurement are different
        # claims, and a zero would rank it last as if it had been tested.
        assert score_agreement({"absent": {99: 11}}, self._cohort()) == []

    def test_an_element_nobody_captained_scores_a_zero_share(self) -> None:
        results = score_agreement({"lonely": {3: 999}}, self._cohort())
        assert results[0].mean_share == 0.0
        assert results[0].modal_rate == 0.0

    def test_a_cohort_with_no_captured_weeks_scores_nothing(self) -> None:
        assert score_agreement({"any": {1: 11}}, []) == []
