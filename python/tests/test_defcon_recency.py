"""Defensive contribution is a claim about a system, not about a player.

A defender's action count is mostly a property of the arrangement around him:
how high the line sits, who screens in front of him, whether the manager has
changed, who was signed in August. All of those turn over between seasons and
some of them turn over inside one.

So last season is evidence rather than a vote. It sets the target this season's
matches are shrunk toward, worth a handful of nineties, and a settled record of
the current arrangement outvotes a whole campaign played under a different one.
Before a ball is kicked he is priced on last season; a month in he is priced on
this one.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.rates import LeagueRates, league_rates
from fpl_andres.backtesting.scoring import defensive_contribution_points

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
DEFENDER = 2
#: The published bar for a defender. Ten actions is one defensive contribution.
BAR = 10
PRIOR_NINETIES = 10.0


def _rows(actions: list[int], *, element_id: int = 1) -> list[ElementRow]:
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
            defensive_contribution=count,
        )
        for index, count in enumerate(actions, start=1)
    ]


def _league(*groups: list[ElementRow]):
    rows = [row for group in groups for row in group]
    return league_rates(rows, {row.element_id: DEFENDER for row in rows})


def _points(
    this_season: list[ElementRow],
    last_season: list[ElementRow] | None = None,
    league: LeagueRates | None = None,
) -> float:
    carried = last_season or []
    rates = (
        league
        if league is not None
        else _league(this_season, carried, _rows([0] * 20, element_id=9))
    )
    return defensive_contribution_points(
        this_season,
        DEFENDER,
        1.0,
        rates,
        PRIOR_NINETIES,
        1.0,
        carried,
    )


class LastSeasonIsAPriorNotAVote(unittest.TestCase):
    def test_a_player_with_no_record_this_season_is_priced_on_last_season(self) -> None:
        # Nothing yet from this season, so the projector hands last season in as
        # the record itself. Nothing to carry separately.
        strong = _points(_rows([BAR + 2] * 30))
        weak = _points(_rows([0] * 30))

        assert strong > weak

    def test_a_strong_last_season_lifts_a_thin_start(self) -> None:
        opening = _rows([BAR + 2])
        alone = _points(opening)
        carried = _points(opening, _rows([BAR + 2] * 30, element_id=2))

        assert carried > alone

    def test_a_weak_last_season_holds_a_lucky_start_down(self) -> None:
        opening = _rows([BAR + 2])
        alone = _points(opening)
        carried = _points(opening, _rows([0] * 30, element_id=2))

        assert carried < alone

    def test_a_gameweek_of_this_season_weighs_more_than_one_of_last(self) -> None:
        # The rule, stated as directly as it can be. One league for all four
        # readings, so moving a hit between the seasons is the only difference.
        league = _league(_rows([0] * 20, element_id=9), _rows([BAR + 2] * 5, element_id=8))
        blank_now = _rows([0] * 10)
        blank_then = _rows([0] * 10, element_id=2)

        baseline = _points(blank_now, blank_then, league)
        one_now = _points(_rows([0] * 10 + [BAR + 2]), blank_then, league)
        one_then = _points(blank_now, _rows([0] * 10 + [BAR + 2], element_id=2), league)

        assert one_now - baseline > one_then - baseline
        assert one_then >= baseline

    def test_a_settled_season_outvotes_the_one_before_it(self) -> None:
        # Ten matches of the new arrangement against thirty of the old.
        league = _league(_rows([0] * 20, element_id=9), _rows([BAR + 2] * 5, element_id=8))
        changed = _points(_rows([BAR + 2] * 10), _rows([0] * 30, element_id=2), league)
        contradicted = _points(_rows([0] * 10), _rows([BAR + 2] * 30, element_id=2), league)

        assert changed > contradicted

    def test_one_gameweek_does_not_overturn_a_whole_season(self) -> None:
        # The other half of the same rule. A single match of the new
        # arrangement is not a system change, and must not read as one.
        settled = _rows([0] * 30, element_id=2)
        after_one = _points(_rows([BAR + 2]), settled)
        after_ten = _points(_rows([BAR + 2] * 10), settled)

        assert after_one < after_ten

    def test_a_thin_last_season_carries_less_weight_than_a_full_one(self) -> None:
        opening = _rows([0])
        two_matches = _points(opening, _rows([BAR + 2] * 2, element_id=2))
        full_season = _points(opening, _rows([BAR + 2] * 30, element_id=2))

        assert two_matches < full_season

    def test_a_keeper_is_paid_nothing_because_the_route_does_not_reach_him(self) -> None:
        rows = _rows([BAR + 2] * 30)
        league = _league(rows)

        assert defensive_contribution_points(rows, 1, 1.0, league, PRIOR_NINETIES, 1.0, rows) == 0.0
