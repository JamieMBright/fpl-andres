"""The projector hardcodes scoring values; the rules snapshot publishes them.

Two pricings of the same rules exist. `expected_points.py` reads every value
from the snapshot and fails visibly on a rule change. `projector.py` is the
live path and hardcodes them, so a rule change would leave it quietly doing
stale arithmetic. This is the guard that makes that impossible.

The position codes in the snapshot are FPL's own; the projector keys on
element_type integers, so the mapping between them is asserted too.
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres.backtesting import projector
from fpl_andres.rules import RulesSnapshot, ScoringRules

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fpl" / "bootstrap_rules_2026_27.json"
HASH = "sha256:" + "e" * 64
AVAILABLE_AT = datetime(2025, 8, 15, 9, 0, tzinfo=UTC)

GOALKEEPER, DEFENDER, MIDFIELDER, FORWARD = 1, 2, 3, 4
POSITION_CODE = {GOALKEEPER: "GKP", DEFENDER: "DEF", MIDFIELDER: "MID", FORWARD: "FWD"}


def _scoring() -> ScoringRules:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snapshot = RulesSnapshot.from_bootstrap(
        document["payload"],
        season="2026-27",
        source_hash=HASH,
        weekly_free_transfers=1,
    )
    return snapshot.scoring


class ProjectorMatchesPublishedRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scoring = _scoring()

    def test_goal_points_agree_per_position(self) -> None:
        for position, code in POSITION_CODE.items():
            with self.subTest(position=code):
                self.assertEqual(
                    projector._GOAL_POINTS[position],
                    self.scoring.goals_scored[code],
                )

    def test_clean_sheet_points_agree_per_position(self) -> None:
        for position, code in POSITION_CODE.items():
            with self.subTest(position=code):
                self.assertEqual(
                    projector._CLEAN_SHEET_POINTS[position],
                    self.scoring.clean_sheets[code],
                )

    def test_goals_conceded_points_agree_per_position(self) -> None:
        for position, code in POSITION_CODE.items():
            with self.subTest(position=code):
                self.assertEqual(
                    projector._CONCEDED_POINTS[position],
                    self.scoring.goals_conceded[code],
                )

    def test_defensive_contribution_points_agree_per_position(self) -> None:
        for position, code in POSITION_CODE.items():
            with self.subTest(position=code):
                self.assertEqual(
                    projector._DEFCON_POINTS[position],
                    self.scoring.defensive_contribution[code],
                )

    def test_flat_route_values_agree(self) -> None:
        self.assertEqual(projector._ASSIST_POINTS, self.scoring.assists)
        self.assertEqual(projector._YELLOW_CARD_POINTS, self.scoring.yellow_cards)
        self.assertEqual(projector._RED_CARD_POINTS, self.scoring.red_cards)
        self.assertEqual(projector._OWN_GOAL_POINTS, self.scoring.own_goals)
        self.assertEqual(projector._PENALTY_SAVE_POINTS, self.scoring.penalties_saved)
        self.assertEqual(projector._PENALTY_MISS_POINTS, self.scoring.penalties_missed)


if __name__ == "__main__":
    unittest.main()
