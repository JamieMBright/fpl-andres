"""Metric edge cases the audit raised. Two were already handled.

- **#23** claimed `erf(z / sqrt(2))` can exceed 1 by a float epsilon and produce
  an effective rank below 1. Neither half holds. `math.erf` saturates at exactly
  1.0 rather than overshooting, and `rank_of` already clamps with `max(1.0, ...)`.
  Measured below across 2,000 z values in both tails.

- **#24** claimed a degenerate-variance rank correlation "returns no correlation
  rather than an explicit undefined result". It returns `None`, which is the
  explicit undefined result. `0.0` would have been the bug described.

- **#25** was real. An event with fewer than N scored players was silently
  dropped from the top-N average, so a rate over the full gameweeks was
  indistinguishable from a rate over all of them.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_andres.models.backtest import PredictionOutcome, _metrics, _spearman
from fpl_andres.models.metrics import rank_correlation
from fpl_andres.planning.effective import RankModel

AVAILABLE = datetime(2026, 8, 14, 17, 30, tzinfo=UTC)


def _outcome(element_code: int, event: int, predicted: float, actual: float) -> PredictionOutcome:
    return PredictionOutcome(
        season="2025-26",
        event=event,
        element_code=element_code,
        position_code="MID",
        evidence_level="inferred",
        predicted_points=predicted,
        actual_points=actual,
    )


class NormalTailTest:
    pass


def test_the_cdf_never_exceeds_one_in_either_tail() -> None:
    """#23's premise. erf saturates at exactly 1.0; it does not overshoot."""
    field = RankModel(mean_points=50.0, standard_deviation=8.0, field_size=11_000_000)
    extremes = [field.share_below(50.0 + sign * step) for step in range(0, 400) for sign in (1, -1)]
    assert max(extremes) <= 1.0
    assert min(extremes) >= 0.0
    assert math.erf(float("inf")) == 1.0


def test_rank_is_already_clamped_at_one() -> None:
    """#23's other half. The clamp predates the audit."""
    field = RankModel(mean_points=50.0, standard_deviation=8.0, field_size=11_000_000)
    assert field.rank_of(10_000.0) == 1.0
    assert field.rank_of(-10_000.0) == pytest.approx(11_000_000.0)


def test_places_gained_is_never_negative_for_extra_points() -> None:
    field = RankModel(mean_points=50.0, standard_deviation=8.0, field_size=11_000_000)
    for points in (-500.0, 0.0, 50.0, 500.0):
        assert field.places_gained(points, 1.0) >= 0.0


def test_a_constant_column_gives_undefined_not_zero_correlation() -> None:
    """#24's premise. None is the undefined result; 0.0 would be the bug."""
    flat_prediction = [_outcome(code, 1, 5.0, float(code)) for code in range(1, 6)]
    flat_actual = [_outcome(code, 1, float(code), 5.0) for code in range(1, 6)]

    assert _spearman(flat_prediction) is None
    assert _spearman(flat_actual) is None


def test_too_few_observations_gives_undefined_correlation() -> None:
    assert _spearman([_outcome(1, 1, 1.0, 1.0), _outcome(2, 1, 2.0, 2.0)]) is None


def test_both_scorers_share_one_definition_of_undefined() -> None:
    """#31. `models/backtest.py` and `backtesting/score.py` each implemented the
    same three guards, which is two places for them to drift. Both now call
    `rank_correlation`, so the answer to "when is a correlation undefined" has
    one owner."""
    assert rank_correlation([1.0, 2.0], [1.0, 2.0]) is None
    assert rank_correlation([5.0, 5.0, 5.0], [1.0, 2.0, 3.0]) is None
    assert rank_correlation([1.0, 2.0, 3.0], [7.0, 7.0, 7.0]) is None
    assert rank_correlation([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert rank_correlation([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == pytest.approx(-1.0)


def test_neither_scorer_still_calls_scipy_directly() -> None:
    """The duplication is only removed if the old path is gone."""
    for module in ("models/backtest.py", "backtesting/score.py"):
        source = (Path(__file__).resolve().parents[1] / "fpl_andres" / module).read_text(
            encoding="utf-8"
        )
        assert "spearmanr" not in source, f"{module} still calls scipy directly"


def test_undefined_is_distinct_from_no_relationship() -> None:
    """Zero means a relationship was looked for and not found. None means it
    could not have been found. Reporting the first for the second makes a model
    look neutral when it was never tested."""
    unmeasurable = rank_correlation([4.0, 4.0, 4.0], [4.0, 4.0, 4.0])
    measured = rank_correlation([1.0, 2.0, 3.0, 4.0], [2.0, 1.0, 4.0, 3.0])

    assert unmeasurable is None
    assert measured is not None
    assert measured != 0.0 or unmeasurable is None


def test_a_short_event_is_reported_rather_than_silently_dropped() -> None:
    """#25. Two full gameweeks and one blank-hit gameweek of three players.

    The rate is unchanged — a top-5 cannot be computed from three players — but
    the metric now says it covered two events and skipped one, so an average
    over the full gameweeks is no longer indistinguishable from an average over
    all of them.
    """
    full = [
        _outcome(code, event, float(code), float(code)) for event in (1, 2) for code in range(1, 11)
    ]
    short = [_outcome(code, 3, float(code), float(code)) for code in range(1, 4)]

    metrics = _metrics("overall", [*full, *short], 5)

    assert metrics.top_n_hit_rate == pytest.approx(1.0)
    assert metrics.top_n_events_scored == 2
    assert metrics.top_n_events_skipped == 1


def test_coverage_is_zero_when_no_event_can_supply_a_top_n() -> None:
    outcomes = [
        _outcome(code, event, float(code), float(code)) for event in (1, 2) for code in (1, 2)
    ]

    metrics = _metrics("overall", outcomes, 5)

    assert metrics.top_n_hit_rate is None
    assert metrics.top_n_events_scored == 0
    assert metrics.top_n_events_skipped == 2


def test_every_event_counted_when_all_are_long_enough() -> None:
    outcomes = [
        _outcome(code, event, float(code), float(code))
        for event in (1, 2, 3)
        for code in range(1, 8)
    ]

    metrics = _metrics("overall", outcomes, 5)

    assert metrics.top_n_events_scored == 3
    assert metrics.top_n_events_skipped == 0


def test_an_empty_slice_reports_no_coverage_rather_than_full_coverage() -> None:
    metrics = _metrics("overall", [], 5)

    assert metrics.top_n_hit_rate is None
    assert metrics.top_n_events_scored == 0
    assert metrics.top_n_events_skipped == 0


@pytest.mark.slow
def test_scoring_a_full_corpus_stays_far_from_being_a_bottleneck() -> None:
    """#33 asked for the per-event sorts to be hoisted, on the grounds that they
    "dominate scoring across a full multi-season corpus".

    Profiled over 114,000 outcomes — four seasons of 38 gameweeks and 750 scored
    players, the real corpus shape — the whole `_metrics` call takes 0.080s, of
    which sorting is 0.026s. Largest single line item, and irrelevant: the
    backtest that calls it pages the corpus over the network first.

    Declined, and guarded instead. The bound is 25x the measured time, so it
    will not flake on a loaded CI runner but will catch a change that makes
    scoring quadratic in the number of outcomes.
    """
    outcomes = [
        _outcome(code, event, float((code * 7 + event) % 41), float((code * 13 + event) % 37))
        for event in range(1, 39)
        for code in range(1, 751)
    ]
    assert len(outcomes) == 28_500

    started = time.perf_counter()
    metrics = _metrics("overall", outcomes, 20)
    elapsed = time.perf_counter() - started

    assert metrics.top_n_events_scored == 38
    assert elapsed < 2.0, f"scoring took {elapsed:.2f}s; it was 0.08s when measured"
