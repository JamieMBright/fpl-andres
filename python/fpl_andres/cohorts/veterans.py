"""Verified manager cohorts.

FPL wipes standings at a season rollover, so the set of past top finishers
cannot be reconstructed from the API alone. Community-maintained lists of former
champions and veterans do exist, but they are unverified claims on a third-party
site.

This module treats such a list as nothing more than a list of candidate entry
ids. Every claim about a manager is then re-derived from FPL's own
``entry/{id}/history/`` response, so the cohort rests on the official record and
never on the source that suggested the id. A candidate whose history does not
support the claim simply fails to qualify.

Only the entry id and its rank history are retained. Manager names are public
but are not what the cohort is for, so they are not stored.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CohortCriteria",
    "ManagerRecord",
    "SeasonFinish",
    "extract_entry_ids",
    "parse_history",
    "qualifies",
]

_SEASON_NAME = re.compile(r"^\d{4}/\d{2}$")
# Entry ids appear as bare numbers or inside an FPL URL.
_ENTRY_URL = re.compile(r"(?:/entry/|team/)(\d{1,10})\b")


class CohortError(ValueError):
    """Raised when a history payload cannot support a cohort decision."""


@dataclass(frozen=True)
class SeasonFinish:
    season_name: str
    total_points: int
    rank: int


@dataclass(frozen=True)
class ManagerRecord:
    """A manager's verified season-by-season record."""

    entry_id: int
    finishes: tuple[SeasonFinish, ...]

    @property
    def seasons_played(self) -> int:
        return len(self.finishes)

    @property
    def best_rank(self) -> int | None:
        return min((finish.rank for finish in self.finishes), default=None)

    def elite_seasons(self, threshold: int) -> int:
        return sum(1 for finish in self.finishes if finish.rank <= threshold)

    def recent(self, seasons: int) -> tuple[SeasonFinish, ...]:
        return self.finishes[-seasons:] if seasons > 0 else ()


@dataclass(frozen=True)
class CohortCriteria:
    """Membership rules. Supplied by the caller, never inferred.

    Sustained performance is a stronger skill filter than a single spike: one
    top-100 finish out of eleven million carries real luck, whereas repeated
    elite finishes do not.
    """

    elite_rank_threshold: int
    minimum_elite_seasons: int
    minimum_seasons_played: int

    def __post_init__(self) -> None:
        if self.elite_rank_threshold <= 0:
            raise ValueError("elite rank threshold must be positive")
        if self.minimum_elite_seasons <= 0:
            raise ValueError("minimum elite seasons must be positive")
        if self.minimum_seasons_played < self.minimum_elite_seasons:
            raise ValueError("seasons played cannot be fewer than elite seasons")


def parse_history(entry_id: int, payload: Mapping[str, Any]) -> ManagerRecord:
    """Read the verified record out of an ``entry/{id}/history/`` response."""
    past = payload.get("past")
    if not isinstance(past, list):
        raise CohortError(f"entry {entry_id} history has no past seasons array")

    finishes: list[SeasonFinish] = []
    for index, season in enumerate(past):
        if not isinstance(season, dict):
            raise CohortError(f"entry {entry_id} past[{index}] is not an object")
        name = season.get("season_name")
        rank = season.get("rank")
        points = season.get("total_points")
        if not isinstance(name, str) or not _SEASON_NAME.fullmatch(name):
            raise CohortError(f"entry {entry_id} past[{index}] has no usable season name")
        if not isinstance(rank, int) or rank <= 0:
            # A null rank means the season was not completed; skip rather than
            # invent a placement.
            continue
        if not isinstance(points, int):
            continue
        finishes.append(SeasonFinish(season_name=name, total_points=points, rank=rank))

    return ManagerRecord(entry_id=entry_id, finishes=tuple(finishes))


def qualifies(record: ManagerRecord, criteria: CohortCriteria) -> bool:
    """True when the official record supports cohort membership."""
    if record.seasons_played < criteria.minimum_seasons_played:
        return False
    return record.elite_seasons(criteria.elite_rank_threshold) >= criteria.minimum_elite_seasons


def extract_entry_ids(text: str, *, limit: int = 500) -> tuple[int, ...]:
    """Pull candidate entry ids out of a pasted list.

    Accepts FPL URLs or bare ids one per line. Order is preserved and
    duplicates dropped, because the list is only ever a set of candidates to
    verify against the official API.
    """
    found: list[int] = []
    seen: set[int] = set()

    for match in _ENTRY_URL.finditer(text):
        _remember(int(match.group(1)), found, seen)

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            _remember(int(stripped), found, seen)

    return tuple(found[:limit])


def _remember(entry_id: int, found: list[int], seen: set[int]) -> None:
    if entry_id > 0 and entry_id not in seen:
        seen.add(entry_id)
        found.append(entry_id)


def rank_cohort(
    records: Sequence[ManagerRecord], criteria: CohortCriteria
) -> tuple[ManagerRecord, ...]:
    """Qualifying managers, most consistently elite first."""
    qualifying = [record for record in records if qualifies(record, criteria)]
    return tuple(
        sorted(
            qualifying,
            key=lambda record: (
                -record.elite_seasons(criteria.elite_rank_threshold),
                record.best_rank if record.best_rank is not None else 10**9,
            ),
        )
    )
