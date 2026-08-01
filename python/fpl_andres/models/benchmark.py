"""Score our projection against somebody else's, on the same players and week.

The strongest validation available is a rival model that is already trusted, and
it may not flatter us. What this cannot do is fetch one. FPL Review's robots.txt
carries `User-agent: ClaudeBot / Disallow: /` and `Content-Signal: ai-train=no`,
which is an explicit refusal, and fplkiwi.com does not resolve. So the rival
column arrives from the owner, who may export their own account's data, and this
module only does the arithmetic.

Both models are scored against the same realised points, so neither can be
flattered by a different population or a different week.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "BenchmarkComparison",
    "BenchmarkUnavailable",
    "ModelScore",
    "compare_projections",
]

# Below this, a rank correlation is not worth reporting.
_MINIMUM_PAIRS = 20


class BenchmarkUnavailable(ValueError):
    """Raised when the two projections cannot be compared honestly."""


@dataclass(frozen=True)
class ModelScore:
    """One model's accuracy over a shared population."""

    label: str
    mean_absolute_error: float
    bias: float
    spearman: float
    top_n_hit_rate: float


@dataclass(frozen=True)
class BenchmarkComparison:
    """Two models over exactly the same players."""

    players: int
    ours: ModelScore
    theirs: ModelScore
    top_n: int

    @property
    def error_gap(self) -> float:
        """Negative means we are closer. Reported in points per player."""
        return self.ours.mean_absolute_error - self.theirs.mean_absolute_error

    @property
    def we_win(self) -> bool:
        return self.error_gap < 0.0


def compare_projections(
    *,
    ours: Mapping[int, float],
    theirs: Mapping[int, float],
    actual: Mapping[int, float],
    top_n: int = 30,
) -> BenchmarkComparison:
    """Compare on the intersection only, so neither model gets a free population."""
    if top_n <= 0:
        raise BenchmarkUnavailable("top_n must be positive")

    shared = sorted(set(ours) & set(theirs) & set(actual))
    if len(shared) < _MINIMUM_PAIRS:
        raise BenchmarkUnavailable(
            f"only {len(shared)} players are in all three sets; "
            f"need at least {_MINIMUM_PAIRS} to compare"
        )

    truth = [actual[code] for code in shared]
    return BenchmarkComparison(
        players=len(shared),
        ours=_score("ours", [ours[code] for code in shared], truth, top_n),
        theirs=_score("theirs", [theirs[code] for code in shared], truth, top_n),
        top_n=top_n,
    )


def _score(
    label: str, predicted: Sequence[float], truth: Sequence[float], top_n: int
) -> ModelScore:
    errors = [p - t for p, t in zip(predicted, truth, strict=True)]
    return ModelScore(
        label=label,
        mean_absolute_error=statistics.mean(abs(error) for error in errors),
        bias=statistics.mean(errors),
        spearman=_spearman(predicted, truth),
        top_n_hit_rate=_top_n_hit_rate(predicted, truth, top_n),
    )


def _rank(values: Sequence[float]) -> list[float]:
    """Average ranks, so ties do not distort the correlation."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        shared_rank = (position + end) / 2.0
        for index in range(position, end + 1):
            ranks[order[index]] = shared_rank
        position = end + 1
    return ranks


def _spearman(predicted: Sequence[float], truth: Sequence[float]) -> float:
    predicted_ranks = _rank(predicted)
    truth_ranks = _rank(truth)
    if len(set(predicted_ranks)) < 2 or len(set(truth_ranks)) < 2:
        raise BenchmarkUnavailable("a projection with no spread cannot be ranked")
    return statistics.correlation(predicted_ranks, truth_ranks)


def _top_n_hit_rate(predicted: Sequence[float], truth: Sequence[float], top_n: int) -> float:
    """Share of the truly best players the model put in its own top N."""
    size = min(top_n, len(predicted))
    best_predicted = sorted(range(len(predicted)), key=lambda i: -predicted[i])[:size]
    best_actual = set(sorted(range(len(truth)), key=lambda i: -truth[i])[:size])
    return len(set(best_predicted) & best_actual) / size
