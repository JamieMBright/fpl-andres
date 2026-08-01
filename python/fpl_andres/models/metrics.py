from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean

from scipy.stats import spearmanr

# Below this, a rank correlation is noise dressed as a measurement.
MINIMUM_RANKED_OBSERVATIONS = 3


def mean_absolute_error(
    predicted: Sequence[float],
    observed: Sequence[float],
) -> float:
    _require_aligned(predicted, observed)
    return fmean(
        abs(prediction - outcome) for prediction, outcome in zip(predicted, observed, strict=True)
    )


def rank_correlation(predicted: Sequence[float], observed: Sequence[float]) -> float | None:
    """Spearman correlation, or None when the sample cannot support one.

    Three ways it can be undefined rather than zero, and the distinction
    matters: zero means "no relationship was found", None means "no relationship
    could have been found". Reporting the first when you mean the second makes a
    model look neutral when it was never tested.

    Both `models/backtest.py` and `backtesting/score.py` implemented these
    guards separately, which is two places for them to drift apart.
    """
    if len(predicted) < MINIMUM_RANKED_OBSERVATIONS:
        return None
    # A constant column has no ranks to correlate.
    if len(set(predicted)) < 2 or len(set(observed)) < 2:
        return None
    value = float(spearmanr(predicted, observed).statistic)
    return None if value != value else value


def _require_aligned(predicted: Sequence[float], observed: Sequence[float]) -> None:
    if not predicted:
        raise ValueError("metric requires at least one observation")
    if len(predicted) != len(observed):
        raise ValueError("predicted and observed values must have the same length")


__all__ = [
    "MINIMUM_RANKED_OBSERVATIONS",
    "mean_absolute_error",
    "rank_correlation",
]
