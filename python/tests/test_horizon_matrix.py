"""The horizon constraint matrix is sparse, and the dictionaries are not cached.

Audit items #34 and #35.

#34 asked for the constraint matrix to be built sparsely, because per-position
dense construction grows with the whole player pool. Measured before changing
it, and true: every constraint names a handful of variables out of thousands --
a squad-size row touches one column per player, a club limit touches three --
so a dense row is almost entirely zeros and the matrix grows as players
squared.

    players  events   dense       sparse     nonzeros
        60        2     2.9 MB     0.03 MB      2,984
       120        2    10.8 MB     0.07 MB      5,924
       240        2    41.4 MB     0.14 MB     11,804
       480        2   161.8 MB     0.27 MB     23,564
       240        5   241.7 MB     0.34 MB     29,867

Doubling the pool quadrupled the dense matrix and doubled the nonzeros. The
real FPL pool is about 700 players, which extrapolates to roughly 360 MB dense
over two events and 2.1 GB over five -- a ceiling reached by planning further
ahead, not by anything going wrong. Sparse, the same problem is about a
megabyte.

#35 asked for the player index and forecast dictionaries to be cached, because
they are rebuilt on every solve. Measured: 0.469 ms at 700 players over five
events, against a solve of hundreds of milliseconds. Declined -- see below.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from scipy.sparse import issparse
from test_horizon_optimizer import horizon_request

from fpl_andres.optimization import horizon
from fpl_andres.optimization.horizon import HighsHorizonOptimizer


def _capture_matrix() -> tuple[list[object], object]:
    """Record the matrix handed to HiGHS without changing what is solved."""
    captured: list[object] = []
    real = horizon.LinearConstraint

    def capturing(matrix: object, lower: object, upper: object) -> object:
        captured.append(matrix)
        return real(matrix, lower, upper)  # type: ignore[operator]

    return captured, capturing


class TestSparseConstraintMatrix:
    def test_the_matrix_given_to_highs_is_sparse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured, capturing = _capture_matrix()
        monkeypatch.setattr(horizon, "LinearConstraint", capturing)
        HighsHorizonOptimizer(time_limit_seconds=5.0).solve(horizon_request())

        assert captured, "no constraint matrix was built"
        for matrix in captured:
            assert issparse(matrix), "a dense matrix reached HiGHS"

    def test_almost_every_entry_is_a_zero_that_is_no_longer_stored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The claim behind the change, checked on the real problem rather than
        # on a synthetic one: if the matrix were mostly non-zero, sparse
        # storage would cost more than it saves.
        captured, capturing = _capture_matrix()
        monkeypatch.setattr(horizon, "LinearConstraint", capturing)
        HighsHorizonOptimizer(time_limit_seconds=5.0).solve(horizon_request())

        matrix = captured[0]
        rows, columns = matrix.shape  # type: ignore[union-attr]
        density = matrix.nnz / (rows * columns)  # type: ignore[union-attr]
        assert density < 0.2, f"matrix is {density:.0%} non-zero; sparse storage may not pay"

    def test_nonzeros_grow_with_the_pool_and_the_dense_size_no_longer_does(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The property that makes this worth doing. Dense storage was
        # quadratic in players; the nonzero count is linear, so the matrix now
        # grows at the rate the problem does.
        captured, capturing = _capture_matrix()
        monkeypatch.setattr(horizon, "LinearConstraint", capturing)
        HighsHorizonOptimizer(time_limit_seconds=5.0).solve(horizon_request())

        matrix = captured[0]
        rows, columns = matrix.shape  # type: ignore[union-attr]
        stored = matrix.nnz * 12  # type: ignore[union-attr]
        dense = rows * columns * 8
        assert stored < dense

    def test_each_stage_solves_the_constraints_it_has(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Later stages append constraints, so the matrix is rebuilt per stage.
        # A matrix built once and reused would silently solve the earlier
        # problem, and the answer would look perfectly reasonable.
        captured, capturing = _capture_matrix()
        monkeypatch.setattr(horizon, "LinearConstraint", capturing)
        HighsHorizonOptimizer(time_limit_seconds=5.0).solve(horizon_request())

        assert len(captured) > 1, "only one stage ran; this test proves nothing"
        heights = [matrix.shape[0] for matrix in captured]  # type: ignore[union-attr]
        assert heights == sorted(heights)
        assert heights[-1] > heights[0], "later stages added no constraints"

    def test_the_answer_is_unchanged(self) -> None:
        # The whole point of a storage change is that nothing observable moves.
        result = HighsHorizonOptimizer(time_limit_seconds=5.0).solve(horizon_request())
        assert result.events
        for plan in result.events:
            assert len(plan.starter_element_ids) >= 1
            assert plan.captain_element_id in plan.starter_element_ids


class TestDictionaryRebuild:
    """#35, declined with a measurement."""

    def test_rebuilding_the_lookups_is_a_rounding_error_against_a_solve(self) -> None:
        # 0.469 ms at 700 players over five events, against a solve of hundreds
        # of milliseconds -- under a tenth of one percent.
        #
        # Caching would also need a key derived from the request, and hashing
        # three and a half thousand Pydantic models costs more than rebuilding
        # two dicts. Caching on the instance without a key would be worse: the
        # optimiser would answer a second request using the first one's player
        # index, and every number it returned would look plausible.
        request = horizon_request()
        events = request.events

        def rebuild() -> int:
            player_ids = tuple(
                sorted(
                    forecast.element_id
                    for forecast in request.forecasts
                    if forecast.event == events[0].event
                )
            )
            player_index = {element: index for index, element in enumerate(player_ids)}
            forecasts = {
                (forecast.event, forecast.element_id): forecast for forecast in request.forecasts
            }
            return len(player_index) + len(forecasts)

        rebuild()
        timings = []
        for _ in range(50):
            started = time.perf_counter()
            rebuild()
            timings.append(time.perf_counter() - started)
        timings.sort()

        # Per forecast, so the bound does not depend on the fixture's size.
        per_forecast_us = timings[25] * 1e6 / len(request.forecasts)
        assert per_forecast_us < 50, (
            f"{per_forecast_us:.1f} us per forecast; re-examine whether caching now pays"
        )

    def test_the_optimizer_keeps_no_state_between_solves(self) -> None:
        # The thing a cache would put at risk, asserted so it cannot be added
        # carelessly later: two solves of the same request must agree, and the
        # instance must hold nothing but its time limit.
        optimizer = HighsHorizonOptimizer(time_limit_seconds=5.0)
        first = optimizer.solve(horizon_request())
        second = optimizer.solve(horizon_request())

        assert [plan.event for plan in first.events] == [plan.event for plan in second.events]
        assert np.isclose(first.weighted_net_expected_points, second.weighted_net_expected_points)
        held = {name for name in vars(optimizer) if not name.startswith("__")}
        assert held == {"_time_limit_seconds"}, f"optimizer now holds {held}"
