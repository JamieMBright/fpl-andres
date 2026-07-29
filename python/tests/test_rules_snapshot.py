import unittest

from fpl_andres.rules import RulesContractError, RulesSnapshot


def bootstrap_fixture() -> dict:
    return {
        "events": [
            {
                "id": 1,
                "name": "Gameweek 1",
                "chip_plays": [
                    {"chip_name": "wildcard", "num_played": 0},
                ],
            }
        ],
        "game_settings": {
            "squad_squadsize": 15,
            "squad_squadplay": 11,
            "squad_team_limit": 3,
            "squad_total_spend": 1000,
            "transfers_cap": 20,
            "transfers_sell_on_fee": 0.5,
            "max_extra_free_transfers": 4,
        },
        "element_types": [
            {
                "id": 1,
                "singular_name_short": "GKP",
                "squad_select": 2,
                "squad_min_play": 1,
                "squad_max_play": 1,
            },
            {
                "id": 2,
                "singular_name_short": "DEF",
                "squad_select": 5,
                "squad_min_play": 3,
                "squad_max_play": 5,
            },
            {
                "id": 3,
                "singular_name_short": "MID",
                "squad_select": 5,
                "squad_min_play": 2,
                "squad_max_play": 5,
            },
            {
                "id": 4,
                "singular_name_short": "FWD",
                "squad_select": 3,
                "squad_min_play": 1,
                "squad_max_play": 3,
            },
        ],
        "chips": [
            {"name": "wildcard", "start_event": 1, "stop_event": 19},
            {"name": "wildcard", "start_event": 20, "stop_event": 38},
            {"name": "freehit", "start_event": 1, "stop_event": 38},
        ],
    }


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
        self.assertEqual(rules.positions[2].minimum_start, 3)
        self.assertEqual(rules.max_extra_free_transfers, 4)
        self.assertEqual(rules.max_free_transfers, 5)
        self.assertEqual(
            [window.stop_event for window in rules.chips if window.name == "wildcard"],
            [19, 38],
        )

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


if __name__ == "__main__":
    unittest.main()
