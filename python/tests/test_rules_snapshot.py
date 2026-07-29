import json
import unittest
from pathlib import Path
from typing import Any

from fpl_andres.rules import RulesContractError, RulesSnapshot

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fpl" / "bootstrap_rules_2026_27.json"


def bootstrap_fixture() -> dict[str, Any]:
    document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return document["payload"]


class RulesSnapshotTests(unittest.TestCase):
    def test_extracts_controlling_rules_from_bootstrap(self) -> None:
        rules = RulesSnapshot.from_bootstrap(
            bootstrap_fixture(),
            season="2026-27",
            source_hash="sha256:fixture",
            weekly_free_transfers=1,
        )

        self.assertEqual(rules.squad_size, 15)
        self.assertEqual(rules.starting_size, 11)
        self.assertEqual(rules.club_limit, 3)
        self.assertEqual(rules.budget_tenths, 1000)
        self.assertEqual(rules.max_free_transfers, 5)
        self.assertFalse(rules.sell_at_purchase_price)
        self.assertEqual(rules.currency_multiplier, 10)
        self.assertEqual(rules.positions[2].minimum_start, 3)
        self.assertEqual(rules.scoring.long_play, 2)
        self.assertEqual(rules.scoring.goals_scored["MID"], 5)
        self.assertEqual(rules.scoring.defensive_contribution["DEF"], 2)
        self.assertEqual(rules.max_extra_free_transfers, 4)
        self.assertEqual(rules.max_free_transfers, 5)
        self.assertEqual(
            [window.stop_event for window in rules.chips if window.name == "wildcard"],
            [19, 38],
        )
        self.assertEqual(rules.chips[0].chip_type, "transfer")
        bench_boost = next(chip for chip in rules.chips if chip.id == 4)
        self.assertEqual(bench_boost.chip_type, "team")
        self.assertIsNone(bench_boost.pick_multiplier)

    def test_rejects_missing_controlling_rule_instead_of_defaulting(self) -> None:
        bootstrap = bootstrap_fixture()
        del bootstrap["game_settings"]["squad_total_spend"]

        with self.assertRaisesRegex(
            RulesContractError,
            "game_settings.squad_total_spend",
        ):
            RulesSnapshot.from_bootstrap(
                bootstrap,
                season="2026-27",
                source_hash="sha256:fixture",
                weekly_free_transfers=1,
            )

    def test_rejects_missing_position_scoring_instead_of_defaulting(self) -> None:
        bootstrap = bootstrap_fixture()
        del bootstrap["game_config"]["scoring"]["goals_scored"]["MID"]

        with self.assertRaisesRegex(
            RulesContractError,
            "game_config.scoring.goals_scored.MID",
        ):
            RulesSnapshot.from_bootstrap(
                bootstrap,
                season="2026-27",
                source_hash="sha256:fixture",
                weekly_free_transfers=1,
            )

    def test_rejects_missing_published_scoring_field_even_if_not_yet_modeled(self) -> None:
        bootstrap = bootstrap_fixture()
        del bootstrap["game_config"]["scoring"]["bps"]

        with self.assertRaisesRegex(RulesContractError, "game_config.scoring.bps"):
            RulesSnapshot.from_bootstrap(
                bootstrap,
                season="2026-27",
                source_hash="sha256:fixture",
                weekly_free_transfers=1,
            )

    def test_rejects_missing_chip_override_key_instead_of_inferring_it(self) -> None:
        bootstrap = bootstrap_fixture()
        del bootstrap["chips"][3]["overrides"]["pick_multiplier"]

        with self.assertRaisesRegex(
            RulesContractError,
            r"chips\[3\]\.overrides\.pick_multiplier",
        ):
            RulesSnapshot.from_bootstrap(
                bootstrap,
                season="2026-27",
                source_hash="sha256:fixture",
                weekly_free_transfers=1,
            )

    def test_rejects_disagreement_between_mirrored_rule_sources(self) -> None:
        bootstrap = bootstrap_fixture()
        bootstrap["game_settings"]["squad_total_spend"] = 999

        with self.assertRaisesRegex(
            RulesContractError,
            "game_settings.squad_total_spend.*game_config.rules.squad_total_spend",
        ):
            RulesSnapshot.from_bootstrap(
                bootstrap,
                season="2026-27",
                source_hash="sha256:fixture",
                weekly_free_transfers=1,
            )

    def test_rejects_inverted_chip_window(self) -> None:
        bootstrap = bootstrap_fixture()
        bootstrap["chips"][0]["start_event"] = 20
        bootstrap["chips"][0]["stop_event"] = 19

        with self.assertRaisesRegex(RulesContractError, r"chips\[0\].*window"):
            RulesSnapshot.from_bootstrap(
                bootstrap,
                season="2026-27",
                source_hash="sha256:fixture",
                weekly_free_transfers=1,
            )

    def test_rejects_duplicate_chip_id(self) -> None:
        bootstrap = bootstrap_fixture()
        bootstrap["chips"][1]["id"] = bootstrap["chips"][0]["id"]

        with self.assertRaisesRegex(RulesContractError, "duplicate chip id"):
            RulesSnapshot.from_bootstrap(
                bootstrap,
                season="2026-27",
                source_hash="sha256:fixture",
                weekly_free_transfers=1,
            )

    def test_rejects_invalid_position_formation_bounds(self) -> None:
        bootstrap = bootstrap_fixture()
        bootstrap["element_types"][1]["squad_min_play"] = 6

        with self.assertRaisesRegex(RulesContractError, r"element_types\[1\].*formation"):
            RulesSnapshot.from_bootstrap(
                bootstrap,
                season="2026-27",
                source_hash="sha256:fixture",
                weekly_free_transfers=1,
            )


if __name__ == "__main__":
    unittest.main()
