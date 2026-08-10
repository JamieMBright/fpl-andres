"""Translate a completed-season points total into an empirical Overall Rank band.

FPL publishes a manager's final points and rank together, but no historical
points distribution. The swept manager catalogue is therefore the only local
source that can answer what a score was worth in a particular season.

The catalogue is selection-biased toward managers with repeated high finishes,
so this returns the range covered by the nearest measured finishes rather than
pretending one neighbouring row defines an exact rank. Scores outside the
observed range are unavailable, not extrapolated.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

__all__ = ["OverallRankBand", "rank_band"]

MINIMUM_SAMPLE = 20


@dataclass(frozen=True)
class OverallRankBand:
    points: int
    rank_from: int
    rank_to: int
    lower_points: int
    upper_points: int
    sample_size: int


def rank_band(
    rows: Iterable[Mapping[str, object]],
    *,
    season: str,
    points: int,
    minimum_sample: int = MINIMUM_SAMPLE,
) -> OverallRankBand | None:
    """Range covered by the nearest measured finishes in the same season."""
    finishes: list[tuple[int, int]] = []
    for row in rows:
        seasons = row.get("seasons")
        if not isinstance(seasons, list):
            continue
        for finish in seasons:
            if not isinstance(finish, Mapping) or finish.get("season") != season:
                continue
            scored = finish.get("points")
            rank = finish.get("rank")
            if isinstance(scored, int) and isinstance(rank, int) and rank > 0:
                finishes.append((scored, rank))

    if minimum_sample < 2:
        raise ValueError("minimum_sample must be at least two")
    if len(finishes) < minimum_sample:
        return None
    observed_points = [scored for scored, _ in finishes]
    if points < min(observed_points) or points > max(observed_points):
        return None
    nearest = sorted(
        finishes,
        key=lambda finish: (abs(finish[0] - points), -finish[0], finish[1]),
    )[:minimum_sample]
    scores = [scored for scored, _ in nearest]
    ranks = [rank for _, rank in nearest]
    return OverallRankBand(
        points=points,
        rank_from=min(ranks),
        rank_to=max(ranks),
        lower_points=min(scores),
        upper_points=max(scores),
        sample_size=len(ranks),
    )
