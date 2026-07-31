"""Transfer planning over a horizon, and the premium-versus-spread question."""

from __future__ import annotations

from datetime import UTC, datetime

from fpl_andres.backtesting.projector import HorizonProjection
from fpl_andres.models.minutes import MinutesProjection
from fpl_andres.models.player_rates import PlayerRateProjection
from fpl_andres.planning import (
    TransferPlanSettings,
    plan_transfers,
    premium_is_justified,
)


def projection(
    element_id: int, points: float, price_tenths: int, position: int = 4
) -> HorizonProjection:
    return HorizonProjection(
        element_id=element_id,
        position=position,
        price_tenths=price_tenths,
        points_by_horizon={1: points / 5, 5: points},
        fixtures_by_horizon={1: 1, 5: 5},
        minutes=_MINUTES,
        rates=_RATES,
    )


_AVAILABLE_AT = datetime(2024, 10, 1, 12, 0, tzinfo=UTC)

_MINUTES = MinutesProjection(
    element_code=1,
    season="2024-25",
    event=8,
    probability_start=0.9,
    probability_appear=0.95,
    probability_sixty_minutes=0.9,
    expected_minutes=90.0,
    evidence_level="observed",
    reason_codes=(),
    data_available_at=_AVAILABLE_AT,
    source_hashes=(),
)
_RATES = PlayerRateProjection(
    element_code=1,
    season="2024-25",
    event=8,
    goals_per_90=0.5,
    assists_per_90=0.2,
    current_season_minutes=900.0,
    carried_season=None,
    carried_weight=0.0,
    evidence_level="observed",
    reason_codes=(),
    data_available_at=_AVAILABLE_AT,
    source_hashes=(),
)

TEAMS = {element_id: element_id for element_id in range(1, 40)}


def test_a_clear_upgrade_is_taken_with_the_free_transfer() -> None:
    squad = [1]
    pool = [projection(1, 10.0, 50), projection(2, 25.0, 50)]

    plan = plan_transfers(
        squad,
        pool,
        bank_tenths=0,
        team_by_element=TEAMS,
        settings=TransferPlanSettings(horizon=5, max_moves=1),
    )

    assert [move.in_element_id for move in plan.moves] == [2]
    assert plan.moves[0].cost == 0.0
    assert plan.squad_points_after > plan.squad_points_before


def test_a_marginal_upgrade_is_left_alone() -> None:
    squad = [1]
    pool = [projection(1, 10.0, 50), projection(2, 10.2, 50)]

    plan = plan_transfers(
        squad,
        pool,
        bank_tenths=0,
        team_by_element=TEAMS,
        settings=TransferPlanSettings(horizon=5),
    )

    assert plan.moves == ()


def test_a_second_move_must_clear_the_four_point_hit() -> None:
    squad = [1, 3]
    pool = [
        projection(1, 10.0, 50),
        projection(2, 25.0, 50),
        projection(3, 10.0, 50),
        projection(4, 12.0, 50),
    ]

    plan = plan_transfers(
        squad,
        pool,
        bank_tenths=0,
        team_by_element=TEAMS,
        settings=TransferPlanSettings(horizon=5, free_transfers=1, max_moves=4),
    )

    # The second swap gains only two points, under the cost of a hit.
    assert len(plan.moves) == 1


def test_a_big_second_move_does_justify_the_hit() -> None:
    squad = [1, 3]
    pool = [
        projection(1, 10.0, 50),
        projection(2, 25.0, 50),
        projection(3, 10.0, 50),
        projection(4, 30.0, 50),
    ]

    plan = plan_transfers(
        squad,
        pool,
        bank_tenths=0,
        team_by_element=TEAMS,
        settings=TransferPlanSettings(horizon=5, free_transfers=1, max_moves=4),
    )

    assert len(plan.moves) == 2
    assert plan.moves[1].cost == 4.0


def test_an_unaffordable_upgrade_is_not_planned() -> None:
    squad = [1]
    pool = [projection(1, 10.0, 40), projection(2, 40.0, 130)]

    plan = plan_transfers(
        squad,
        pool,
        bank_tenths=0,
        team_by_element=TEAMS,
        settings=TransferPlanSettings(horizon=5),
    )

    assert plan.moves == ()


def test_the_club_limit_blocks_a_fourth_from_the_same_side() -> None:
    squad = [1, 2, 3, 4]
    pool = [projection(element_id, 10.0, 50) for element_id in (1, 2, 3)]
    # Element 4 is the weakest, so it is the move the planner would make if the
    # club limit did not exist. It plays for a different side, so taking it out
    # for another element of club 7 would put four of them in the squad.
    pool.append(projection(4, 5.0, 50))
    pool.append(projection(5, 30.0, 50))
    same_club = {1: 7, 2: 7, 3: 7, 4: 9, 5: 7}

    plan = plan_transfers(
        squad,
        pool,
        bank_tenths=0,
        team_by_element=same_club,
        settings=TransferPlanSettings(horizon=5, club_limit=3, max_moves=1),
    )

    assert [move.in_element_id for move in plan.moves] == [5]
    assert plan.moves[0].out_element_id in {1, 2, 3}


def test_a_premium_that_outscores_the_field_is_justified() -> None:
    premium = projection(1, 60.0, 150)
    alternatives = [projection(element_id, 12.0, 70) for element_id in range(2, 10)]

    assert premium_is_justified(premium, alternatives, horizon=5, spare_tenths=0)


def test_a_premium_that_two_cheaper_players_beat_is_not() -> None:
    premium = projection(1, 20.0, 150)
    alternatives = [projection(element_id, 18.0, 70) for element_id in range(2, 10)]

    assert not premium_is_justified(premium, alternatives, horizon=5, spare_tenths=0)


def test_a_premium_stands_when_the_money_cannot_buy_replacements() -> None:
    premium = projection(1, 20.0, 80)
    alternatives = [projection(element_id, 30.0, 200) for element_id in range(2, 5)]

    assert premium_is_justified(premium, alternatives, horizon=5, spare_tenths=0)
