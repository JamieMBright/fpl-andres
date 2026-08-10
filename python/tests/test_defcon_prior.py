"""What a defender is paid for defensive contribution before anybody has seen him.

The route arrived in 2025/26, so every season the corpus holds before it has a
null column. `defensive_contribution_points` used to pay nothing at all when a
player had no observed defcon minutes, which is not "nothing is known" -- it is
a claim that he never clears the bar.

It fell on exactly the players it should not have: a promoted squad, an arrival
from abroad, anyone whose Premier League record predates the route. Defensive
contribution is 7.5% of every point FPL awards, more than assists.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.rates import LeagueRates, league_rates
from fpl_andres.backtesting.scoring import defensive_contribution_points

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
DEFENDER = 2
KEEPER = 1
PRIOR_NINETIES = 10.0
NINETY = 1.0


def _row(
    index: int,
    *,
    actions: int | None,
    element_id: int = 1,
) -> ElementRow:
    """One appearance. `actions` of None is a season before the route existed."""
    return ElementRow(
        gameweek=index,
        element_id=element_id,
        element_code=1000 + element_id,
        fixture_id=index,
        minutes=90,
        started=True,
        goals=0,
        assists=0,
        expected_goals=0.0,
        expected_assists=0.0,
        total_points=2,
        price_tenths=45,
        selected=1000,
        kickoff_time=KICKOFF + timedelta(days=7 * index),
        clean_sheets=0,
        saves=0,
        bonus=0,
        goals_conceded=1,
        clearances_blocks_interceptions=None if actions is None else actions,
        tackles=None if actions is None else 0,
        recoveries=None if actions is None else 0,
        defensive_contribution=actions,
    )


def _league(clears: int) -> LeagueRates:
    """A league where the typical defender clears the bar in `clears` of 20."""
    rows = [
        _row(index, actions=14 if index <= clears else 2, element_id=2) for index in range(1, 21)
    ]
    return league_rates(rows, {2: DEFENDER})


class TestADefenderNobodyHasSeenDefend:
    def test_he_is_paid_the_league_rate_rather_than_nothing(self) -> None:
        blind = [_row(index, actions=None) for index in range(1, 21)]

        paid = defensive_contribution_points(
            blind, DEFENDER, NINETY, _league(10), PRIOR_NINETIES, 1.0
        )

        assert paid > 0.0

    def test_what_he_is_paid_follows_the_league_he_is_compared_to(self) -> None:
        """The number is a prior, so it has to move with the prior."""
        blind = [_row(index, actions=None) for index in range(1, 21)]

        busy = defensive_contribution_points(
            blind, DEFENDER, NINETY, _league(16), PRIOR_NINETIES, 1.0
        )
        quiet = defensive_contribution_points(
            blind, DEFENDER, NINETY, _league(4), PRIOR_NINETIES, 1.0
        )

        assert busy > quiet

    def test_a_player_with_a_record_is_paid_on_it_instead(self) -> None:
        league = _league(4)
        blind = [_row(index, actions=None) for index in range(1, 21)]
        seen = [_row(index, actions=14) for index in range(1, 21)]

        assert defensive_contribution_points(
            seen, DEFENDER, NINETY, league, PRIOR_NINETIES, 1.0
        ) > defensive_contribution_points(blind, DEFENDER, NINETY, league, PRIOR_NINETIES, 1.0)

    def test_a_keeper_is_still_paid_nothing(self) -> None:
        """There is no bar for a goalkeeper to clear, so there is no prior."""
        blind = [_row(index, actions=None) for index in range(1, 21)]

        paid = defensive_contribution_points(
            blind, KEEPER, NINETY, _league(10), PRIOR_NINETIES, 1.0
        )

        assert paid == pytest.approx(0.0)
