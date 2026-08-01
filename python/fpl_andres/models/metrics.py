from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean


def mean_absolute_error(
    predicted: Sequence[float],
    observed: Sequence[float],
) -> float:
    _require_aligned(predicted, observed)
    return fmean(
        abs(prediction - outcome) for prediction, outcome in zip(predicted, observed, strict=True)
    )


def _require_aligned(predicted: Sequence[float], observed: Sequence[float]) -> None:
    if not predicted:
        raise ValueError("metric requires at least one observation")
    if len(predicted) != len(observed):
        raise ValueError("predicted and observed values must have the same length")


__all__ = [
    "mean_absolute_error",
]
