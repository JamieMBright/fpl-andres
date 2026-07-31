"""The club limit binds differently on selection and on holding.

Rule as stated by the owner, who plays the game: you can never select a fourth
player from a club, but a player moving between clubs mid-season can leave you
holding four, and the next transfer must correct it.
"""

from __future__ import annotations

import unittest

from fpl_andres.simulation.squad import (
    Candidate,
    SquadRules,
    clubs_over_limit,
    transfer_respects_club_limit,
)

RULES = SquadRules(budget_tenths=1000, club_limit=3, position_counts={1: 2, 2: 5, 3: 5, 4: 3})
ARSENAL = 1
CHELSEA = 2
EVERTON = 3


def player(element_id: int, team: int, position: int = 3) -> Candidate:
    return Candidate(
        element_id=element_id,
        element_code=element_id * 10,
        position=position,
        team_id=team,
        price_tenths=50,
        web_name=f"P{element_id}",
    )


def _four_at_arsenal() -> list[Candidate]:
    return [player(index, ARSENAL) for index in range(1, 5)] + [
        player(5, CHELSEA),
        player(6, EVERTON),
    ]


class ClubsOverLimitTest(unittest.TestCase):
    def test_a_legal_squad_reports_nothing(self) -> None:
        squad = [player(index, ARSENAL) for index in range(1, 4)]

        self.assertEqual(clubs_over_limit(squad, RULES), {})

    def test_a_squad_holding_four_reports_the_club(self) -> None:
        self.assertEqual(clubs_over_limit(_four_at_arsenal(), RULES), {ARSENAL: 4})


class TransferClubLimitTest(unittest.TestCase):
    def test_a_legal_squad_cannot_transfer_into_a_fourth(self) -> None:
        squad = [player(index, ARSENAL) for index in range(1, 4)]
        squad.append(player(4, CHELSEA))

        self.assertFalse(
            transfer_respects_club_limit(squad, player(4, CHELSEA), player(9, ARSENAL), RULES)
        )

    def test_a_legal_squad_may_transfer_within_the_limit(self) -> None:
        squad = [player(index, ARSENAL) for index in range(1, 4)]
        squad.append(player(4, CHELSEA))

        self.assertTrue(
            transfer_respects_club_limit(squad, player(4, CHELSEA), player(9, EVERTON), RULES)
        )

    def test_holding_four_the_correction_is_compulsory(self) -> None:
        """A transfer that leaves the breach standing is refused."""
        squad = _four_at_arsenal()

        self.assertFalse(
            transfer_respects_club_limit(squad, player(5, CHELSEA), player(9, EVERTON), RULES)
        )

    def test_holding_four_a_transfer_that_corrects_it_is_allowed(self) -> None:
        squad = _four_at_arsenal()

        self.assertTrue(
            transfer_respects_club_limit(squad, player(1, ARSENAL), player(9, EVERTON), RULES)
        )

    def test_holding_four_swapping_arsenal_for_arsenal_does_not_correct_it(self) -> None:
        squad = _four_at_arsenal()

        self.assertFalse(
            transfer_respects_club_limit(squad, player(1, ARSENAL), player(9, ARSENAL), RULES)
        )


if __name__ == "__main__":
    unittest.main()
