"""Two decisions the plan makes about shape rather than about players.

The reserve keeper, and how far ahead a transfer is allowed to look. Both were
reported by a reader looking at a published plan and asking why it did not
resemble anything a good manager does.
"""

from __future__ import annotations

import pytest

from fpl_andres.planning.opening import (
    OpeningSettings,
    bench_weights,
    choose_opening_squad,
)
from fpl_andres.planning.season_plan import COMMIT_EVENTS, WINDOW_EVENTS
from fpl_andres.simulation.squad import Candidate, SquadRules

GOALKEEPER = 1

_POINTS: dict[int, float] = {}


def _player(element_id: int, position: int, price: int = 50) -> Candidate:
    return Candidate(
        element_id=element_id,
        element_code=element_id,
        position=position,
        team_id=1,
        price_tenths=price,
    )


def _priced(element_id: int, position: int, *, price: int, points: float) -> Candidate:
    """A candidate whose points are recorded for the caller's lookup table."""
    _POINTS[element_id] = points
    return Candidate(
        element_id=element_id,
        element_code=element_id,
        position=position,
        # Spread across clubs so the three-per-club rule never binds.
        team_id=element_id,
        price_tenths=price,
    )


class TestTheReserveKeeper:
    def test_he_is_worth_the_chance_his_starter_blanks(self) -> None:
        # Not zero. Rotating two cheap keepers to take the softer fixture is a
        # strategy, and a Bench Boost needs him to score, so this function may
        # not rule either out by assumption.
        starters = [_player(1, GOALKEEPER), _player(2, 2), _player(3, 3)]
        bench = [_player(10, GOALKEEPER), _player(11, 3)]
        appear = {1: 0.75, 2: 0.9, 3: 0.9}

        assert bench_weights(starters, bench, appear)[0] == pytest.approx(0.25)

    def test_an_outfield_substitute_still_earns_his_place(self) -> None:
        starters = [_player(1, GOALKEEPER), _player(2, 2), _player(3, 3)]
        bench = [_player(11, 3), _player(12, 3)]
        appear = {1: 0.74, 2: 0.5, 3: 0.5}

        weights = bench_weights(starters, bench, appear)

        assert weights[0] > 0.0


class TestTheTransferHorizon:
    def test_the_window_reaches_past_a_five_fixture_run(self) -> None:
        # The shape transfers exist to exploit is a run of soft fixtures
        # followed by hard ones. A window of five sees the run and not the
        # cliff, so the planner buys in and is still there when it turns.
        assert WINDOW_EVENTS >= 7

    def test_the_commit_stride_is_smaller_than_the_window(self) -> None:
        """Overlap is the whole reason this is not independent solves."""
        assert COMMIT_EVENTS < WINDOW_EVENTS

    def test_most_of_the_window_is_lookahead(self) -> None:
        # Committing nearly the whole window would make the overlap decorative.
        assert WINDOW_EVENTS - COMMIT_EVENTS >= COMMIT_EVENTS


class TestBuyingAPremiumBySellingElsewhere:
    """The move a single swap can never make.

    A premium you cannot afford on its own is paid for by downgrading someone
    else. Considered one at a time the downgrade loses points and is rejected,
    so the upgrade it funds is never reached. This is the shape of every real
    "bring in Haaland" decision, and of a Wildcard rebuild.
    """

    def _rules(self) -> SquadRules:
        return SquadRules(
            budget_tenths=230,
            club_limit=3,
            position_counts={1: 1, 2: 1, 3: 1, 4: 1},
        )

    def _settings(self) -> OpeningSettings:
        return OpeningSettings(
            rules=self._rules(),
            lineup_size=4,
            minimum_by_position={1: 1, 2: 1, 3: 1, 4: 1},
            maximum_by_position={1: 1, 2: 1, 3: 1, 4: 1},
            bench_weight=0.0,
            playable_start_rate=0.0,
        )

    def _pool(self) -> list[Candidate]:
        # One keeper and one defender, so the only decisions are midfield and
        # forward. The seed is the cheapest legal squad, and from there a single
        # upgrade in one place spends the money the other place needs.
        return [
            _priced(1, 1, price=40, points=4.0),
            _priced(2, 2, price=40, points=4.0),
            _priced(3, 3, price=30, points=1.0),
            _priced(4, 3, price=90, points=11.5),
            _priced(5, 3, price=75, points=9.0),
            _priced(6, 4, price=30, points=1.0),
            _priced(7, 4, price=90, points=11.5),
            _priced(8, 4, price=75, points=9.0),
        ]

    def test_it_downgrades_one_place_to_afford_a_premium_in_another(self) -> None:
        # The climb spends up on the single best upgrade it can see -- the £9.0m
        # midfielder at 11.5 -- and then every remaining single move is either
        # unaffordable or worse, so it stops at 20.5. Two mid-priced players
        # together score 26 and cost exactly the budget, and no sequence of one
        # swap at a time reaches them: the first half of the move always looks
        # like a loss.
        pool = self._pool()
        points = {player.element_id: _POINTS[player.element_id] for player in pool}
        start_rate = {player.element_id: 1.0 for player in pool}

        plan = choose_opening_squad(pool, points, start_rate, self._settings())
        chosen = {player.element_id for player in plan.squad}

        assert chosen == {1, 2, 5, 8}
        assert plan.spent_tenths == 230
        assert plan.expected_points == pytest.approx(26.0)

    def test_it_still_respects_the_budget(self) -> None:
        pool = self._pool()
        points = {player.element_id: _POINTS[player.element_id] for player in pool}
        start_rate = {player.element_id: 1.0 for player in pool}

        plan = choose_opening_squad(pool, points, start_rate, self._settings())

        assert plan.spent_tenths <= 230
