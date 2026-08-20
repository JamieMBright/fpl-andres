"""Calibration by projected band.

Pooled error is dominated by the hundreds of players projected near zero. A
captain is chosen from the top band alone, so "how wrong is this model" has to
be answerable per band or it does not answer the question anybody asks of it.
"""

from __future__ import annotations

from fpl_andres.backtesting.score import MethodScore, _band_index
from fpl_andres.models.backtest import CALIBRATION_BAND_EDGES


def _feed(method: MethodScore, pairs: list[tuple[float, float]]) -> None:
    for predicted, actual in pairs:
        totals = method.band_totals.setdefault(_band_index(predicted), [0.0, 0.0, 0.0])
        totals[0] += 1.0
        totals[1] += predicted
        totals[2] += actual


def test_each_band_reports_what_that_band_actually_scored() -> None:
    method = MethodScore(label="model")
    _feed(
        method,
        [
            (0.5, 0.0),
            (1.5, 2.0),
            (5.0, 4.0),
            (5.0, 6.0),
            (9.0, 3.0),
        ],
    )

    bands = {band.label: band for band in method.calibration()}

    assert bands["0-2"].count == 2
    assert bands["0-2"].mean_predicted == 1.0
    assert bands["0-2"].mean_actual == 1.0
    assert bands["4-6"].count == 2
    assert bands["4-6"].mean_actual == 5.0
    # The top band promised nine and returned three. Pooled with the rest the
    # mean error is unremarkable; alone it is the whole story of a captain pick.
    assert bands["8+"].count == 1
    assert bands["8+"].bias == 6.0


def test_an_empty_band_is_omitted_rather_than_published_as_a_perfect_one() -> None:
    method = MethodScore(label="model")
    _feed(method, [(1.0, 1.0)])

    labels = [band.label for band in method.calibration()]

    assert labels == ["0-2"]


def test_the_top_band_is_open_ended() -> None:
    method = MethodScore(label="model")
    _feed(method, [(40.0, 12.0)])

    (band,) = method.calibration()

    assert band.upper is None
    assert band.lower == CALIBRATION_BAND_EDGES[-1]
    assert band.count == 1


def test_every_projection_lands_in_exactly_one_band() -> None:
    edges = [0.0, *CALIBRATION_BAND_EDGES]
    probes = [-3.0, 0.0, *(edge for edge in edges), *(edge - 0.01 for edge in edges[1:]), 99.0]

    for probe in probes:
        index = _band_index(probe)
        assert 0 <= index <= len(CALIBRATION_BAND_EDGES)

    # A value exactly on an edge belongs to the band above it, so the bands do
    # not overlap and nothing falls between them.
    for edge in CALIBRATION_BAND_EDGES:
        assert _band_index(edge) == _band_index(edge - 0.01) + 1
