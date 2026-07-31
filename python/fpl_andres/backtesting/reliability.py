"""How dependable a player's return is, not just how large.

Two players can share an expected score and be completely different holdings. A
defender who clears the defensive-contribution threshold most weeks banks two
points he will almost certainly get. A defender on the same expectation who
relies on clean sheets is holding a lottery ticket: bigger when it lands, and
absent most weeks.

Expected points cannot tell those apart, so the shape of the distribution is
measured separately and kept alongside the mean rather than folded into it.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from fpl_andres.backtesting.corpus import ElementRow

__all__ = ["PointsShape", "describe_shape"]

# A "return" in common usage is an attacking return or better. Two points is a
# bare appearance, so the bar sits above it.
_RETURN_THRESHOLD = 5
_BLANK_CEILING = 2
_MINIMUM_APPEARANCES = 4


@dataclass(frozen=True)
class PointsShape:
    """The distribution of one player's realised returns per appearance."""

    appearances: int
    floor: float
    median: float
    ceiling: float
    return_rate: float
    blank_rate: float
    volatility: float

    @property
    def is_measured(self) -> bool:
        return self.appearances >= _MINIMUM_APPEARANCES


def _percentile(ordered: Sequence[int], share: float) -> float:
    """Nearest-rank percentile. Exact interpolation would imply precision the
    sample size does not support."""
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return float(ordered[index])


def describe_shape(rows: Sequence[ElementRow]) -> PointsShape:
    """Summarise realised returns across the appearances in ``rows``.

    Gameweeks the player did not feature in are excluded: this describes what
    happens when he plays. Whether he plays is the minutes model's job, and
    mixing the two would hide both.
    """
    scores = sorted(row.total_points for row in rows if row.minutes > 0)
    if not scores:
        return PointsShape(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    returns = sum(1 for score in scores if score >= _RETURN_THRESHOLD)
    blanks = sum(1 for score in scores if score <= _BLANK_CEILING)
    return PointsShape(
        appearances=len(scores),
        floor=_percentile(scores, 0.2),
        median=_percentile(scores, 0.5),
        ceiling=_percentile(scores, 0.9),
        return_rate=returns / len(scores),
        blank_rate=blanks / len(scores),
        volatility=statistics.pstdev(scores) if len(scores) > 1 else 0.0,
    )
