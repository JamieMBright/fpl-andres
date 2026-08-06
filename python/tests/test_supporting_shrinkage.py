"""Clean sheets and bonus were the last two supporting routes with no prior.

Every other route in `supporting_breakdown` is pulled toward the league rate in
proportion to how thin the evidence is. These two were the observed rate,
divided by appearances, used raw -- three lines above a comment reading "shrunk
like every other route", which is what makes it an oversight rather than a
decision.

The consequence was largest exactly where the model is used most. A defender
three matches into a season with two clean sheets was priced at a 67% rate for
the rest of it, and one early three-bonus haul became a bonus a match forever.
Clean sheets are 13% of every point FPL awards and bonus another 6.4%.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.fixtures import RouteAdjustment
from fpl_andres.backtesting.rates import league_rates
from fpl_andres.backtesting.scoring import supporting_breakdown

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
DEFENDER = 2
PRIOR_NINETIES = 10.0

NEUTRAL = RouteAdjustment(
    attacking=1.0,
    clean_sheet=1.0,
    conceding=1.0,
    saves=1.0,
    defensive_contribution=1.0,
)


class _Minutes:
    probability_sixty_minutes = 1.0
    expected_minutes = 90.0


def _rows(
    clean_sheets: list[int],
    bonus: list[int] | None = None,
    *,
    element_id: int = 1,
) -> list[ElementRow]:
    awards = bonus if bonus is not None else [0] * len(clean_sheets)
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
            total_points=3,
            price_tenths=45,
            selected=1000,
            kickoff_time=KICKOFF + timedelta(days=7 * index),
            clean_sheets=sheet,
            saves=0,
            bonus=award,
            goals_conceded=0,
        )
        for index, (sheet, award) in enumerate(zip(clean_sheets, awards, strict=True), start=1)
    ]


def _breakdown(own: list[ElementRow], league_rows: list[ElementRow]):
    positions = {row.element_id: DEFENDER for row in [*own, *league_rows]}
    league = league_rates([*own, *league_rows], positions)
    return supporting_breakdown(
        own,
        DEFENDER,
        _Minutes(),  # type: ignore[arg-type]
        league,
        PRIOR_NINETIES,
        NEUTRAL,
    )


class CleanSheetShrinkageTest(unittest.TestCase):
    def test_a_thin_perfect_record_is_pulled_toward_the_league(self) -> None:
        # Three matches, three clean sheets. Unshrunk that is a 100% rate and
        # the full four points; the league keeps one in four.
        league_rows = _rows([0] * 30 + [1] * 10, element_id=2)
        thin = _breakdown(_rows([1, 1, 1]), league_rows)

        assert thin.clean_sheet < 4.0
        assert thin.clean_sheet < 3.0

    def test_a_thick_record_keeps_most_of_its_own_rate(self) -> None:
        # Thirty matches of the same rate is evidence, and shrinkage should
        # barely touch it. Otherwise the prior is doing the modelling.
        league_rows = _rows([0] * 30 + [1] * 10, element_id=2)
        thin = _breakdown(_rows([1, 1, 1]), league_rows)
        thick = _breakdown(_rows([1] * 30), league_rows)

        assert thick.clean_sheet > thin.clean_sheet

    def test_a_thin_barren_record_is_lifted_toward_the_league(self) -> None:
        # Shrinkage has to work in both directions, or it is a penalty on new
        # players rather than a prior.
        league_rows = _rows([1] * 30 + [0] * 10, element_id=2)
        thin = _breakdown(_rows([0, 0]), league_rows)

        assert thin.clean_sheet > 0.0


class BonusShrinkageTest(unittest.TestCase):
    def test_one_early_haul_does_not_become_a_bonus_a_match(self) -> None:
        # Three appearances, one of them a three-bonus. Unshrunk that projects
        # 1.0 bonus a match indefinitely.
        league_rows = _rows([0] * 40, [0] * 40, element_id=2)
        thin = _breakdown(_rows([0, 0, 0], [3, 0, 0]), league_rows)

        assert thin.bonus < 1.0

    def test_a_sustained_bonus_record_survives_the_prior(self) -> None:
        league_rows = _rows([0] * 40, [0] * 40, element_id=2)
        thin = _breakdown(_rows([0, 0, 0], [3, 0, 0]), league_rows)
        thick = _breakdown(_rows([0] * 30, [1] * 30), league_rows)

        assert thick.bonus > thin.bonus

    def test_a_player_with_no_bonus_is_not_projected_at_zero(self) -> None:
        # The league awards bonus in every match to somebody, so a player with
        # a short barren record is not a player who will never get one.
        league_rows = _rows([0] * 40, [2] * 40, element_id=2)
        thin = _breakdown(_rows([0, 0], [0, 0]), league_rows)

        assert thin.bonus > 0.0
