"""Observed completed-season point boundaries for useful Overall Rank bins.

FPL publishes final points and rank together, but no historical points
percentiles. The manager catalogue is selected for repeat elite finishes, so it
cannot estimate how common a score is. It can still identify the point levels
observed immediately inside and outside a named rank cutoff. Those two rows are
reported as a rough bracket, never interpolated into a false exact rank.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "RANK_CUTOFFS",
    "RankBoundary",
    "RankEstimate",
    "RankObservation",
    "boundaries_from_artifact",
    "classify_points",
    "rank_boundaries",
]

RANK_CUTOFFS = (
    1_000,
    10_000,
    50_000,
    100_000,
    250_000,
    500_000,
    1_000_000,
    2_000_000,
    3_000_000,
)


@dataclass(frozen=True)
class RankObservation:
    points: int
    rank: int


@dataclass(frozen=True)
class RankBoundary:
    rank_cutoff: int
    inside: RankObservation
    outside: RankObservation
    sample_size: int

    @property
    def status(self) -> Literal["bracketed", "tie_at_cutoff"]:
        return "tie_at_cutoff" if self.inside.points == self.outside.points else "bracketed"

    @property
    def rank_gap(self) -> int:
        return self.outside.rank - self.inside.rank

    @property
    def points_gap(self) -> int:
        return self.inside.points - self.outside.points


@dataclass(frozen=True)
class RankEstimate:
    rank_cutoff: int | None
    status: Literal["inside", "around", "outside"]
    boundary: RankBoundary | None


def _season_finishes(rows: Iterable[Mapping[str, object]], *, season: str) -> list[RankObservation]:
    finishes: list[RankObservation] = []
    for row in rows:
        seasons = row.get("seasons")
        if not isinstance(seasons, list):
            continue
        for finish in seasons:
            if not isinstance(finish, Mapping) or finish.get("season") != season:
                continue
            points = finish.get("points")
            rank = finish.get("rank")
            if isinstance(points, int) and isinstance(rank, int) and rank > 0:
                finishes.append(RankObservation(points=points, rank=rank))
    return finishes


def rank_boundaries(
    rows: Iterable[Mapping[str, object]],
    *,
    season: str,
    cutoffs: Sequence[int] = RANK_CUTOFFS,
) -> tuple[RankBoundary, ...]:
    """Nearest measured finish on either side of every requested cutoff."""
    finishes = _season_finishes(rows, season=season)
    boundaries: list[RankBoundary] = []
    for cutoff in cutoffs:
        if cutoff <= 0:
            raise ValueError("rank cutoffs must be positive")
        inside = [finish for finish in finishes if finish.rank <= cutoff]
        outside = [finish for finish in finishes if finish.rank > cutoff]
        if not inside or not outside:
            continue
        boundaries.append(
            RankBoundary(
                rank_cutoff=cutoff,
                inside=max(inside, key=lambda finish: (finish.rank, -finish.points)),
                outside=min(outside, key=lambda finish: (finish.rank, -finish.points)),
                sample_size=len(finishes),
            )
        )
    return tuple(boundaries)


def boundaries_from_artifact(payload: object, *, season: str) -> tuple[RankBoundary, ...]:
    """Read one season's aggregate boundaries without accepting partial rows."""
    if not isinstance(payload, Mapping):
        return ()
    seasons = payload.get("seasons")
    if not isinstance(seasons, list):
        return ()
    selected = next(
        (row for row in seasons if isinstance(row, Mapping) and row.get("season") == season),
        None,
    )
    if selected is None:
        return ()
    rows = selected.get("boundaries")
    if not isinstance(rows, list):
        return ()
    parsed: list[RankBoundary] = []
    for row in rows:
        if not isinstance(row, Mapping):
            return ()
        inside = row.get("inside")
        outside = row.get("outside")
        cutoff = row.get("rankCutoff")
        sample_size = row.get("sampleSize")
        if (
            not isinstance(inside, Mapping)
            or not isinstance(outside, Mapping)
            or not isinstance(cutoff, int)
            or not isinstance(sample_size, int)
        ):
            return ()
        inside_rank = inside.get("rank")
        inside_points = inside.get("points")
        outside_rank = outside.get("rank")
        outside_points = outside.get("points")
        if (
            not isinstance(inside_rank, int)
            or not isinstance(inside_points, int)
            or not isinstance(outside_rank, int)
            or not isinstance(outside_points, int)
        ):
            return ()
        parsed.append(
            RankBoundary(
                rank_cutoff=cutoff,
                inside=RankObservation(points=inside_points, rank=inside_rank),
                outside=RankObservation(points=outside_points, rank=outside_rank),
                sample_size=sample_size,
            )
        )
    return tuple(parsed)


def classify_points(boundaries: Sequence[RankBoundary], *, points: int) -> RankEstimate | None:
    """Classify a score against fixed boundaries without interpolation."""
    if not boundaries:
        return None
    ordered = sorted(boundaries, key=lambda boundary: boundary.rank_cutoff)
    tied = [
        boundary
        for boundary in ordered
        if boundary.status == "tie_at_cutoff" and points == boundary.inside.points
    ]
    if tied:
        boundary = min(tied, key=lambda candidate: candidate.rank_gap)
        return RankEstimate(
            rank_cutoff=boundary.rank_cutoff,
            status="around",
            boundary=boundary,
        )
    for boundary in ordered:
        if points >= boundary.inside.points and points > boundary.outside.points:
            return RankEstimate(
                rank_cutoff=boundary.rank_cutoff,
                status="inside",
                boundary=boundary,
            )
    around = [
        boundary
        for boundary in ordered
        if min(boundary.inside.points, boundary.outside.points)
        <= points
        <= max(boundary.inside.points, boundary.outside.points)
    ]
    if around:
        boundary = min(around, key=lambda candidate: candidate.rank_gap)
        return RankEstimate(
            rank_cutoff=boundary.rank_cutoff,
            status="around",
            boundary=boundary,
        )
    return RankEstimate(rank_cutoff=None, status="outside", boundary=ordered[-1])
