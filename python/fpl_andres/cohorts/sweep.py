"""Catalogue every FPL manager worth following, from a full sweep of entry ids.

One request per entry to `/entry/{id}/history/`, which returns every completed
season for that manager. That is what makes the sweep worth doing: the Overall
league only ever shows the current season, so a full pass is the only way to
find managers who have finished high *repeatedly* in past years.

The parsing and the qualifying rule live here, away from the network, so they
can be tested without touching FPL. The sweep itself is in the CLI.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

__all__ = [
    "CohortRule",
    "ManagerRecord",
    "SeasonFinish",
    "parse_history",
    "qualifies",
]


@dataclass(frozen=True)
class SeasonFinish:
    season: str
    points: int
    rank: int
    # FPL publishes this to one decimal, and it is the only figure that
    # compares across a field that has grown roughly fivefold.
    percentile: float | None

    @property
    def start_year(self) -> int:
        return int(self.season[:4])


@dataclass(frozen=True)
class ManagerRecord:
    entry_id: int
    seasons: tuple[SeasonFinish, ...]

    def recent(self, *, since_start_year: int) -> tuple[SeasonFinish, ...]:
        return tuple(season for season in self.seasons if season.start_year >= since_start_year)


@dataclass(frozen=True)
class CohortRule:
    """What it takes to be worth following.

    Judged on recent seasons only. A career filter keeps managers whose good
    years ended a decade ago and rejects managers who have transformed: entry 1
    finished worse than 93% of the field in 2015/16 and nineteenth in the world
    in 2023/24.
    """

    since_start_year: int
    rank_ceiling: int = 10_000
    minimum_qualifying_seasons: int = 2

    def __post_init__(self) -> None:
        if self.rank_ceiling <= 0:
            raise ValueError("rank ceiling must be positive")
        if self.minimum_qualifying_seasons <= 0:
            raise ValueError("at least one qualifying season is required")


def parse_history(entry_id: int, payload: Mapping[str, Any]) -> ManagerRecord | None:
    """Read the completed seasons out of an entry history payload.

    Seasons without a rank were never finished, so they are dropped rather than
    given a placeholder that would flatter or damn the manager.
    """
    past = payload.get("past")
    if not isinstance(past, list):
        return None

    seasons: list[SeasonFinish] = []
    for row in past:
        if not isinstance(row, Mapping):
            continue
        season = row.get("season_name")
        rank = row.get("rank")
        points = row.get("total_points")
        if not isinstance(season, str) or len(season) < 4 or not season[:4].isdigit():
            continue
        if not isinstance(rank, int) or rank <= 0:
            continue
        percentage = row.get("rank_percentage")
        seasons.append(
            SeasonFinish(
                season=season,
                points=points if isinstance(points, int) else 0,
                rank=rank,
                percentile=float(percentage) if isinstance(percentage, (int, float)) else None,
            )
        )

    if not seasons:
        return None
    return ManagerRecord(entry_id=entry_id, seasons=tuple(seasons))


def qualifies(record: ManagerRecord, rule: CohortRule) -> bool:
    """Whether a manager clears the bar on recent seasons alone."""
    recent = record.recent(since_start_year=rule.since_start_year)
    good = sum(1 for season in recent if season.rank <= rule.rank_ceiling)
    return good >= rule.minimum_qualifying_seasons


def summarise(records: Sequence[ManagerRecord], rule: CohortRule) -> dict[str, int]:
    """Counts for the run report, so a sweep says what it actually found."""
    qualifying = [record for record in records if qualifies(record, rule)]
    return {
        "withHistory": len(records),
        "qualifying": len(qualifying),
    }


class PersistenceNotMeasurable(ValueError):
    """Raised when a persistence claim would be conditioning on the outcome."""


def repeat_rate(
    records: Sequence[ManagerRecord],
    *,
    rank_ceiling: int,
    unfiltered: bool,
) -> float:
    """Share of managers who clear the ceiling again the season after doing so.

    Refuses on a filtered cohort. The sweep only keeps managers who already
    have two qualifying seasons, so both the elite group and everyone left to
    compare them against are pre-selected for exactly the outcome being
    measured. Run on the swept file it produced a *lift below one* in every
    recent season pair - 0.67, 0.58, 0.55, 0.60 - which is the selection
    showing through, not evidence that good managers get worse.
    """
    if not unfiltered:
        raise PersistenceNotMeasurable(
            "a cohort filtered on past rank cannot measure whether past rank "
            "predicts future rank; sweep every entry, not just qualifiers"
        )

    by_season: dict[str, dict[int, int]] = {}
    for record in records:
        for season in record.seasons:
            by_season.setdefault(season.season, {})[record.entry_id] = season.rank

    repeats = 0
    eligible = 0
    for first, second in pairwise(sorted(by_season)):
        # Adjacent in the sorted list is not the same as adjacent in the
        # calendar: a season nobody in the sample played would otherwise make a
        # multi-year gap look consecutive.
        if _start_year(second) != _start_year(first) + 1:
            continue
        earlier, later = by_season[first], by_season[second]
        for entry_id, rank in earlier.items():
            if rank > rank_ceiling or entry_id not in later:
                continue
            eligible += 1
            if later[entry_id] <= rank_ceiling:
                repeats += 1
    if eligible == 0:
        raise PersistenceNotMeasurable("no manager appears in consecutive seasons")
    return repeats / eligible


def _start_year(season: str) -> int:
    return int(season.split("/", 1)[0])
