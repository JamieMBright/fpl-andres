"""A booking costs a point; the ban behind it costs a gameweek.

Thresholds are supplied by the caller throughout. The repository's standing rule
is that a controlling rule which cannot be sourced fails visibly, and these have
changed before, so nothing here carries a default.
"""

from __future__ import annotations

import unittest

from fpl_andres.models.suspensions import (
    CardRateUnavailable,
    SuspensionRules,
    SuspensionThreshold,
    suspension_risk,
)

# Stand-in ladder for the tests only. Not a claim about the real rule.
LADDER = SuspensionRules(
    season="2025-26",
    thresholds=(
        SuspensionThreshold(cards=5, matches_banned=1, applies_through_event=19),
        SuspensionThreshold(cards=10, matches_banned=2, applies_through_event=32),
        SuspensionThreshold(cards=15, matches_banned=3, applies_through_event=38),
    ),
    source_reference="test fixture, not the published handbook",
)


def _risk(cards: list[int], *, event: int = 10, horizon: int = 5):
    return suspension_risk(yellow_cards=cards, rules=LADDER, current_event=event, horizon=horizon)


class RulesTest(unittest.TestCase):
    def test_rules_must_name_their_source(self) -> None:
        with self.assertRaises(ValueError):
            SuspensionRules(
                season="2025-26",
                thresholds=(SuspensionThreshold(5, 1, 19),),
                source_reference="   ",
            )

    def test_rules_cannot_be_empty(self) -> None:
        with self.assertRaises(ValueError):
            SuspensionRules(season="2025-26", thresholds=(), source_reference="x")

    def test_thresholds_must_ascend(self) -> None:
        with self.assertRaises(ValueError):
            SuspensionRules(
                season="2025-26",
                thresholds=(
                    SuspensionThreshold(10, 2, 32),
                    SuspensionThreshold(5, 1, 19),
                ),
                source_reference="x",
            )


class RiskTest(unittest.TestCase):
    def test_a_short_record_is_refused_rather_than_guessed(self) -> None:
        with self.assertRaises(CardRateUnavailable):
            _risk([1, 0, 1])

    def test_a_clean_player_carries_no_risk(self) -> None:
        risk = _risk([0] * 10)

        self.assertEqual(risk.probability_banned, 0.0)
        self.assertEqual(risk.expected_matches_missed, 0.0)
        self.assertEqual(risk.availability(5), 1.0)

    def test_a_booking_a_game_is_nearly_certain_to_reach_the_rung(self) -> None:
        """Four cards already, one needed, five matches to get it."""
        risk = _risk([1, 1, 1, 1, 0, 0, 0, 0], horizon=5)

        self.assertEqual(risk.cards_from_threshold, 1)
        self.assertGreater(risk.probability_banned, 0.8)
        self.assertGreater(risk.expected_matches_missed, 0.8)

    def test_availability_falls_as_the_threshold_approaches(self) -> None:
        near = _risk([1, 1, 1, 1, 0, 0, 0, 0], horizon=5)
        far = _risk([1, 0, 0, 0, 0, 0, 0, 0], horizon=5)

        self.assertLess(near.availability(5), far.availability(5))

    def test_an_expired_rung_cannot_be_triggered(self) -> None:
        """Past the reset, the five-card rung is gone and ten is a long way off."""
        early = _risk([1, 1, 1, 1, 0, 0, 0, 0], event=10)
        late = _risk([1, 1, 1, 1, 0, 0, 0, 0], event=25)

        self.assertEqual(early.next_threshold, 5)
        self.assertEqual(late.next_threshold, 10)
        self.assertLess(late.probability_banned, early.probability_banned)

    def test_a_player_past_every_live_rung_is_clear(self) -> None:
        risk = suspension_risk(
            yellow_cards=[1] * 16,
            rules=LADDER,
            current_event=38,
            horizon=5,
        )

        self.assertIsNone(risk.next_threshold)
        self.assertEqual(risk.probability_banned, 0.0)

    def test_a_longer_horizon_carries_more_risk(self) -> None:
        short = _risk([1, 1, 1, 0, 0, 0, 0, 0], horizon=2)
        long = _risk([1, 1, 1, 0, 0, 0, 0, 0], horizon=8)

        self.assertLess(short.probability_banned, long.probability_banned)


if __name__ == "__main__":
    unittest.main()
