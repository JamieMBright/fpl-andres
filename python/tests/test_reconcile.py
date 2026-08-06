"""Rebuilding realised points from their own component columns.

The card claimed a season reconciles to within one point. A total is the
weakest form of that claim -- offsetting errors sum to nothing -- so these
tests pin the per-row behaviour and, above all, that a disagreement is
*reported* rather than absorbed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.reconcile import reconcile_row, reconcile_season

_KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)


def _row(element_id: int = 1, gameweek: int = 1, **fields: object) -> ElementRow:
    defaults: dict[str, object] = {
        "gameweek": gameweek,
        "element_id": element_id,
        "element_code": 100 + element_id,
        "fixture_id": 1,
        "minutes": 90,
        "started": True,
        "goals": 0,
        "assists": 0,
        "expected_goals": None,
        "expected_assists": None,
        "total_points": 2,
        "price_tenths": 50,
        "selected": 1000,
        "kickoff_time": _KICKOFF,
    }
    defaults.update(fields)
    return ElementRow(**defaults)  # type: ignore[arg-type]


class TestOneRow:
    def test_ninety_minutes_and_nothing_else_is_two_points(self) -> None:
        assert sum(reconcile_row(_row(), position=3).values()) == 2

    def test_under_an_hour_is_one_point_and_no_clean_sheet(self) -> None:
        routes = reconcile_row(_row(minutes=45, clean_sheets=1), position=2)
        assert routes["appearance"] == 1
        assert routes["clean_sheet"] == 0

    def test_a_goal_is_worth_what_the_position_says(self) -> None:
        assert reconcile_row(_row(goals=1), position=1)["goals"] == 10
        assert reconcile_row(_row(goals=1), position=2)["goals"] == 6
        assert reconcile_row(_row(goals=1), position=3)["goals"] == 5
        assert reconcile_row(_row(goals=1), position=4)["goals"] == 4

    def test_goals_conceded_are_charged_in_pairs_to_the_back_only(self) -> None:
        assert reconcile_row(_row(goals_conceded=3), position=1)["conceding"] == -1
        assert reconcile_row(_row(goals_conceded=4), position=2)["conceding"] == -2
        assert reconcile_row(_row(goals_conceded=4), position=3)["conceding"] == 0

    def test_saves_pay_once_every_three(self) -> None:
        assert reconcile_row(_row(saves=5), position=1)["saves"] == 1
        assert reconcile_row(_row(saves=6), position=1)["saves"] == 2

    def test_defensive_contribution_clears_a_bar_or_pays_nothing(self) -> None:
        assert (
            reconcile_row(_row(defensive_contribution=9), position=2)["defensive_contribution"] == 0
        )
        assert (
            reconcile_row(_row(defensive_contribution=10), position=2)["defensive_contribution"]
            == 2
        )
        assert (
            reconcile_row(_row(defensive_contribution=11), position=3)["defensive_contribution"]
            == 0
        )

    def test_a_season_before_the_route_existed_pays_nothing_for_it(self) -> None:
        # `None` is absence of the rule, not a missing measurement.
        routes = reconcile_row(_row(defensive_contribution=None), position=2)
        assert routes["defensive_contribution"] == 0

    def test_a_keeper_has_no_defensive_contribution_bar_at_all(self) -> None:
        routes = reconcile_row(_row(defensive_contribution=40), position=1)
        assert routes["defensive_contribution"] == 0


class TestASeason:
    def _positions(self) -> dict[int, int]:
        return {1: 3, 2: 2}

    def _names(self) -> dict[int, str]:
        return {1: "Midfielder", 2: "Defender"}

    def test_a_season_that_reconciles_reports_no_residual(self) -> None:
        rows = {1: [_row(element_id=1, total_points=2), _row(element_id=2, total_points=2)]}

        outcome = reconcile_season(rows, self._positions(), self._names(), season="2025-26")

        assert outcome.rows == 2
        assert outcome.exact == 2
        assert outcome.residual == 0
        assert outcome.absolute == 0
        assert outcome.worst == []

    def test_offsetting_errors_do_not_cancel_into_a_clean_bill(self) -> None:
        # The whole reason the absolute residual exists. These two rows sum to
        # zero disagreement and neither is right.
        rows = {
            1: [
                _row(element_id=1, total_points=5),
                _row(element_id=2, total_points=-1),
            ]
        }

        outcome = reconcile_season(rows, self._positions(), self._names(), season="2025-26")

        assert outcome.residual == 0
        assert outcome.absolute == 6
        assert outcome.exact == 0

    def test_a_disagreement_names_the_row_and_its_routes(self) -> None:
        rows = {7: [_row(element_id=1, gameweek=7, goals=1, total_points=3)]}

        outcome = reconcile_season(rows, self._positions(), self._names(), season="2025-26")

        assert len(outcome.worst) == 1
        worst = outcome.worst[0]
        assert worst.gameweek == 7
        assert worst.name == "Midfielder"
        assert worst.awarded == 3
        assert worst.rebuilt == 7
        assert worst.residual == 4
        assert worst.routes["goals"] == 5

    def test_the_residual_is_attributed_to_a_position(self) -> None:
        rows = {1: [_row(element_id=2, goals=1, total_points=2)]}

        outcome = reconcile_season(rows, self._positions(), self._names(), season="2025-26")

        assert outcome.by_position == {2: 6}

    def test_the_worst_rows_are_capped_but_the_count_is_not(self) -> None:
        rows = {1: [_row(element_id=index, goals=1, total_points=0) for index in range(1, 12)]}
        positions = dict.fromkeys(range(1, 12), 4)

        outcome = reconcile_season(rows, positions, {}, season="2025-26", keep_worst=3)

        assert outcome.rows == 11
        assert outcome.exact == 0
        assert len(outcome.worst) == 3
        # Every row still counts toward the totals, not just the kept ones.
        assert outcome.absolute == 11 * 6

    def test_an_unnamed_player_is_identified_by_his_id(self) -> None:
        rows = {1: [_row(element_id=9, goals=1, total_points=0)]}

        outcome = reconcile_season(rows, {9: 4}, {}, season="2025-26")

        assert outcome.worst[0].name == "#9"
