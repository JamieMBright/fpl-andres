"""A cohort filtered on past rank cannot tell you whether past rank predicts rank.

The sweep keeps a manager only if they already have two top-10k seasons. Both
the elite group and everyone left to compare them against are therefore
pre-selected for exactly the outcome being measured.

Run on the swept file anyway, the lift came out *below one* in every recent
season pair - 0.67, 0.58, 0.55, 0.60 - with a base rate of 48% to 60% against a
true population rate near 0.15%. That is the selection showing through, not
evidence that good managers get worse. So the function refuses.
"""

from __future__ import annotations

import unittest

from fpl_andres.cohorts.sweep import (
    ManagerRecord,
    PersistenceNotMeasurable,
    SeasonFinish,
    repeat_rate,
)

CEILING = 10_000


def _manager(entry_id: int, ranks: dict[str, int]) -> ManagerRecord:
    return ManagerRecord(
        entry_id=entry_id,
        seasons=tuple(
            SeasonFinish(season=season, points=2000, rank=rank, percentile=None)
            for season, rank in sorted(ranks.items())
        ),
    )


class RefusalTest(unittest.TestCase):
    def test_a_filtered_cohort_is_refused(self) -> None:
        records = [_manager(1, {"2023/24": 500, "2024/25": 900})]

        with self.assertRaises(PersistenceNotMeasurable):
            repeat_rate(records, rank_ceiling=CEILING, unfiltered=False)

    def test_the_refusal_names_the_fix(self) -> None:
        with self.assertRaises(PersistenceNotMeasurable) as caught:
            repeat_rate([], rank_ceiling=CEILING, unfiltered=False)

        self.assertIn("every entry", str(caught.exception))

    def test_no_consecutive_seasons_is_refused_rather_than_zero(self) -> None:
        records = [_manager(1, {"2020/21": 500, "2023/24": 400})]

        with self.assertRaises(PersistenceNotMeasurable):
            repeat_rate(records, rank_ceiling=CEILING, unfiltered=True)


class RateTest(unittest.TestCase):
    def test_a_manager_who_repeats_counts_once_per_pair(self) -> None:
        records = [_manager(1, {"2023/24": 500, "2024/25": 900})]

        self.assertEqual(repeat_rate(records, rank_ceiling=CEILING, unfiltered=True), 1.0)

    def test_a_manager_who_falls_away_counts_as_a_miss(self) -> None:
        records = [_manager(1, {"2023/24": 500, "2024/25": 900_000})]

        self.assertEqual(repeat_rate(records, rank_ceiling=CEILING, unfiltered=True), 0.0)

    def test_only_managers_above_the_ceiling_start_a_pair(self) -> None:
        """Someone outside the ceiling in season N is not being tested."""
        records = [
            _manager(1, {"2023/24": 500, "2024/25": 500}),
            _manager(2, {"2023/24": 900_000, "2024/25": 900_000}),
        ]

        self.assertEqual(repeat_rate(records, rank_ceiling=CEILING, unfiltered=True), 1.0)

    def test_a_missing_next_season_is_skipped_not_counted_against(self) -> None:
        records = [
            _manager(1, {"2023/24": 500, "2024/25": 500}),
            _manager(2, {"2023/24": 500}),
        ]

        self.assertEqual(repeat_rate(records, rank_ceiling=CEILING, unfiltered=True), 1.0)

    def test_the_rate_is_pooled_across_every_pair(self) -> None:
        records = [
            _manager(1, {"2022/23": 500, "2023/24": 500, "2024/25": 900_000}),
            _manager(2, {"2022/23": 500, "2023/24": 900_000}),
        ]

        # Manager 1 contributes hit then miss; manager 2 contributes one miss.
        self.assertAlmostEqual(repeat_rate(records, rank_ceiling=CEILING, unfiltered=True), 1 / 3)


if __name__ == "__main__":
    unittest.main()
