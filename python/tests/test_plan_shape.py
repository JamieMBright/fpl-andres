"""Two decisions the plan makes about shape rather than about players.

The reserve keeper, and how far ahead a transfer is allowed to look. Both were
reported by a reader looking at a published plan and asking why it did not
resemble anything a good manager does.
"""

from __future__ import annotations

from fpl_andres.planning.opening import bench_weights
from fpl_andres.planning.season_plan import COMMIT_EVENTS, WINDOW_EVENTS
from fpl_andres.simulation.squad import Candidate

GOALKEEPER = 1


def _player(element_id: int, position: int, price: int = 50) -> Candidate:
    return Candidate(
        element_id=element_id,
        element_code=element_id,
        position=position,
        team_id=1,
        price_tenths=price,
    )


class TestTheReserveKeeper:
    def test_he_is_worth_nothing_on_the_bench(self) -> None:
        # He covers one player, not eleven, and a manager whose keeper is ruled
        # out transfers him. Pricing him at the chance his starter blanks bought
        # a premium reserve and left the money out of the eleven.
        starters = [_player(1, GOALKEEPER), _player(2, 2), _player(3, 3)]
        bench = [_player(10, GOALKEEPER), _player(11, 3)]
        appear = {1: 0.74, 2: 0.9, 3: 0.9}

        weights = bench_weights(starters, bench, appear)

        assert weights[0] == 0.0

    def test_an_outfield_substitute_still_earns_his_place(self) -> None:
        # The auto-sub genuinely fires for outfield blanks, and that weight is
        # measured rather than assumed. Only the keeper is being changed.
        starters = [_player(1, GOALKEEPER), _player(2, 2), _player(3, 3)]
        bench = [_player(11, 3), _player(12, 3)]
        appear = {1: 0.74, 2: 0.5, 3: 0.5}

        weights = bench_weights(starters, bench, appear)

        assert weights[0] > 0.0

    def test_a_blank_prone_starting_keeper_does_not_buy_a_better_reserve(
        self,
    ) -> None:
        # The old weight was 1 - P(starter appears), so a keeper who missed
        # games last season made his own deputy look valuable. Nothing about the
        # starter should move the reserve's worth now.
        bench = [_player(10, GOALKEEPER)]
        steady = bench_weights([_player(1, GOALKEEPER)], bench, {1: 0.99})
        rotated = bench_weights([_player(1, GOALKEEPER)], bench, {1: 0.40})

        assert steady == rotated == [0.0]


class TestTheTransferHorizon:
    def test_the_window_reaches_past_a_five_fixture_run(self) -> None:
        # The shape transfers exist to exploit is a run of soft fixtures
        # followed by hard ones. A window of five sees the run and not the
        # cliff, so the planner buys in and is still there when it turns.
        assert WINDOW_EVENTS >= 8

    def test_the_commit_stride_is_smaller_than_the_window(self) -> None:
        """Overlap is the whole reason this is not independent solves."""
        assert COMMIT_EVENTS < WINDOW_EVENTS

    def test_most_of_the_window_is_lookahead(self) -> None:
        # Committing nearly the whole window would make the overlap decorative.
        assert WINDOW_EVENTS - COMMIT_EVENTS >= COMMIT_EVENTS
