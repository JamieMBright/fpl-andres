"""The cohort rule judges recent seasons, and drops what it cannot verify."""

from __future__ import annotations

import unittest

from fpl_andres.cohorts.sweep import CohortRule, parse_history, qualifies

# Entry 1's real record: dreadful, then elite.
ENTRY_ONE = {
    "past": [
        {"season_name": "2014/15", "total_points": 1726, "rank": 1_490_762, "rank_percentage": 43},
        {"season_name": "2015/16", "total_points": 1245, "rank": 3_467_086, "rank_percentage": 93},
        {"season_name": "2021/22", "total_points": 2620, "rank": 11_513, "rank_percentage": 0.1},
        {"season_name": "2022/23", "total_points": 2613, "rank": 7_672, "rank_percentage": 0.1},
        {"season_name": "2023/24", "total_points": 2708, "rank": 19, "rank_percentage": 0.0},
        {"season_name": "2025/26", "total_points": 2419, "rank": 4_119, "rank_percentage": 0.0},
    ]
}
RULE = CohortRule(since_start_year=2021, rank_ceiling=10_000, minimum_qualifying_seasons=2)


class ParseHistoryTest(unittest.TestCase):
    def test_reads_every_completed_season(self) -> None:
        record = parse_history(1, ENTRY_ONE)

        assert record is not None
        self.assertEqual(len(record.seasons), 6)
        self.assertEqual(record.seasons[0].start_year, 2014)

    def test_drops_a_season_that_was_never_finished(self) -> None:
        record = parse_history(
            1, {"past": [{"season_name": "2024/25", "total_points": 0, "rank": None}]}
        )

        self.assertIsNone(record)

    def test_a_manager_with_no_completed_season_is_nobody(self) -> None:
        self.assertIsNone(parse_history(1, {"past": []}))
        self.assertIsNone(parse_history(1, {}))

    def test_a_missing_percentage_is_recorded_as_absent_not_zero(self) -> None:
        record = parse_history(
            1, {"past": [{"season_name": "2019/20", "total_points": 2104, "rank": 880_819}]}
        )

        assert record is not None
        self.assertIsNone(record.seasons[0].percentile)


class QualifiesTest(unittest.TestCase):
    def test_recent_elite_seasons_qualify(self) -> None:
        record = parse_history(1, ENTRY_ONE)

        assert record is not None
        self.assertTrue(qualifies(record, RULE))

    def test_old_glory_does_not_qualify(self) -> None:
        """Good seasons that ended a decade ago say nothing about now."""
        record = parse_history(
            2,
            {
                "past": [
                    {"season_name": "2014/15", "total_points": 2400, "rank": 500},
                    {"season_name": "2015/16", "total_points": 2400, "rank": 900},
                    {"season_name": "2024/25", "total_points": 1900, "rank": 3_000_000},
                ]
            },
        )

        assert record is not None
        self.assertFalse(qualifies(record, RULE))

    def test_one_good_recent_season_is_not_enough(self) -> None:
        record = parse_history(
            3,
            {
                "past": [
                    {"season_name": "2023/24", "total_points": 2600, "rank": 5_000},
                    {"season_name": "2024/25", "total_points": 1900, "rank": 2_000_000},
                ]
            },
        )

        assert record is not None
        self.assertFalse(qualifies(record, RULE))

    def test_the_bar_is_configurable(self) -> None:
        record = parse_history(
            3,
            {
                "past": [
                    {"season_name": "2023/24", "total_points": 2600, "rank": 5_000},
                    {"season_name": "2024/25", "total_points": 2500, "rank": 50_000},
                ]
            },
        )

        assert record is not None
        self.assertFalse(qualifies(record, RULE))
        self.assertTrue(
            qualifies(
                record,
                CohortRule(
                    since_start_year=2021,
                    rank_ceiling=100_000,
                    minimum_qualifying_seasons=2,
                ),
            )
        )

    def test_a_nonsense_rule_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            CohortRule(since_start_year=2021, rank_ceiling=0)
        with self.assertRaises(ValueError):
            CohortRule(since_start_year=2021, minimum_qualifying_seasons=0)


if __name__ == "__main__":
    unittest.main()
