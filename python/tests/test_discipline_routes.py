"""Cards, own goals and missed penalties are four routes, not one.

They were summed into a single `discipline` number at the last line of
`supporting_breakdown`. Every one of them was already priced separately, so the
sum threw away a split that had already been paid for -- and a bookmaker
prices a booking directly and prices nothing else in that bundle, so there was
nothing on the row a card quote could replace.

These pin two things: that splitting them changed no arithmetic, and that the
four are still reachable as one number for anything that wants the old view.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.fixtures import RouteAdjustment
from fpl_andres.backtesting.rates import league_rates
from fpl_andres.backtesting.scoring import supporting_breakdown
from fpl_andres.planning.fixture_routes import ROUTE_KEYS

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
MIDFIELDER = 3
PRIOR_NINETIES = 10.0

NEUTRAL = RouteAdjustment(
    attacking=1.0,
    clean_sheet=1.0,
    conceding=1.0,
    saves=1.0,
    defensive_contribution=1.0,
)


class _Minutes:
    probability_appear = 1.0
    probability_sixty_minutes = 1.0
    expected_minutes = 90.0


def _rows(
    *,
    matches: int,
    yellow: int = 0,
    red: int = 0,
    own_goals: int = 0,
    missed: int = 0,
    element_id: int = 1,
) -> list[ElementRow]:
    """One booking per match until the count runs out, so a rate is measurable."""
    return [
        ElementRow(
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
            price_tenths=50,
            selected=1000,
            kickoff_time=KICKOFF + timedelta(days=7 * index),
            clean_sheets=0,
            saves=0,
            bonus=0,
            goals_conceded=1,
            yellow_cards=1 if index <= yellow else 0,
            red_cards=1 if index <= red else 0,
            own_goals=1 if index <= own_goals else 0,
            penalties_missed=1 if index <= missed else 0,
        )
        for index in range(1, matches + 1)
    ]


def _breakdown(own: list[ElementRow]) -> object:
    clean = _rows(matches=40, element_id=2)
    positions = {row.element_id: MIDFIELDER for row in [*own, *clean]}
    return supporting_breakdown(
        own,
        MIDFIELDER,
        _Minutes(),  # type: ignore[arg-type]
        league_rates([*own, *clean], positions),
        PRIOR_NINETIES,
        NEUTRAL,
    )


class TestFourRoutesRatherThanOne:
    def test_a_booked_player_is_docked_on_the_yellow_route_alone(self) -> None:
        booked = _breakdown(_rows(matches=20, yellow=10))

        assert booked.yellow_cards < 0  # type: ignore[attr-defined]
        assert booked.red_cards == 0  # type: ignore[attr-defined]
        assert booked.own_goals == 0  # type: ignore[attr-defined]
        assert booked.penalties_missed == 0  # type: ignore[attr-defined]

    def test_a_red_costs_three_times_what_a_yellow_costs_at_the_same_rate(self) -> None:
        """FPL pays -1 and -3. The routes have to keep that apart to be priced."""
        yellows = _breakdown(_rows(matches=20, yellow=4))
        reds = _breakdown(_rows(matches=20, red=4))

        assert reds.red_cards == pytest.approx(yellows.yellow_cards * 3)  # type: ignore[attr-defined]

    def test_the_four_still_add_up_to_the_number_they_replaced(self) -> None:
        row = _breakdown(_rows(matches=20, yellow=6, red=1, own_goals=1, missed=1))

        assert row.discipline == pytest.approx(  # type: ignore[attr-defined]
            row.yellow_cards + row.red_cards + row.own_goals + row.penalties_missed  # type: ignore[attr-defined]
        )

    def test_a_clean_player_is_docked_only_what_the_league_is(self) -> None:
        """Shrinkage means nobody is priced at zero cards on twenty matches."""
        clean = _breakdown(_rows(matches=20))

        assert clean.yellow_cards <= 0  # type: ignore[attr-defined]


def test_the_published_route_names_carry_the_split() -> None:
    """A reader walks `ROUTE_KEYS`, so a name missing here is a route dropped."""
    assert "discipline" not in ROUTE_KEYS
    for name in ("yellowCards", "redCards", "ownGoals", "penaltiesMissed"):
        assert name in ROUTE_KEYS
