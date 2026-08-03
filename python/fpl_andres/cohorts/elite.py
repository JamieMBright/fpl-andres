"""Rank the swept catalogue down to the five hundred worth following.

## Why rank cannot be used directly

The field grew from about 1.1 million entries in 2006/07 to 13.0 million in
2025/26 — measured from the catalogue, not assumed. A rank of 10,000 in 2007 put
a manager in the top 0.9%; the same number in 2026 puts him in the top 0.08%. Any
score that averages raw ranks across seasons rewards being old, not being good.

Everything here therefore works in percentile: position relative to the field
that season. That is the "relative position is king" rule, and it is the only
part of this module that is not a tuning choice.

The catalogue carries no percentile — FPL publishes one only for recent seasons
and it is null on every row we hold — so it is derived from the largest rank
observed in that season across the whole catalogue. That is a lower bound on the
true entry count, which makes early-season percentiles slightly flattering. The
estimate is published beside the ranking rather than buried, because a reader
should be able to see how the denominator was reached.

## Why recent seasons weigh more

Two reasons, and they are different.

The ordinary one is that form decays: a good 2012 says less about 2026 than a
good 2025 does. That is exponential decay on seasons ago.

The specific one is that the game changed. Defensive contributions arrived in
2025/26 and altered what a good squad looks like. Seasons before it were played
under different scoring, so they are evidence about a different game and are
discounted by a step, not just by age.

## Why longevity has to be earned, not assumed

A weighted mean alone scores two brilliant seasons the same as twenty. Shrinking
the mean toward the population fixes it: a manager with little weight behind him
is pulled to the middle, and only sustained evidence moves him off it. This is
the same shape the rates model uses on a player with few minutes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "DEFAULT_SETTINGS",
    "EliteScore",
    "EliteSettings",
    "ManagerSeason",
    "SweptManager",
    "entries_by_season",
    "rank_elite",
    "season_start_year",
]


@dataclass(frozen=True)
class ManagerSeason:
    season: str
    """Two-digit-suffixed, as FPL publishes it: "2025/26"."""
    points: int
    rank: int


@dataclass(frozen=True)
class SweptManager:
    entry_id: int
    seasons: tuple[ManagerSeason, ...]


@dataclass(frozen=True)
class EliteSettings:
    """Every number here is a choice; none of them is measured."""

    decay_per_season: float = 0.78
    """A season one year older counts this much. 0.78 puts a five-year-old
    season at 0.29 of the newest."""

    pre_rules_change_weight: float = 0.6
    """Extra discount on seasons played before defensive contributions."""

    rules_changed_in: int = 2025
    """Start year of the first season with defensive contributions."""

    shrinkage_weight: float = 2.0
    """Weight of the prior. A manager needs roughly this much seasonal weight
    before his own record outvotes an unknown manager's."""

    prior_percentile: float = 0.5
    """What an unknown manager is: the median of the whole field.

    Not the catalogue's own mean. Everyone here was selected for finishing well,
    so their mean percentile is near 1.0 and shrinking toward it does nothing —
    a single brilliant season would score the same as twenty. Conditioning the
    prior on the selection is the same error `cohort.json` already records about
    measuring persistence on a cohort chosen for persisting."""

    minimum_seasons: int = 3
    """Below this there is not enough of a record to call anyone long-term."""


DEFAULT_SETTINGS = EliteSettings()


def season_start_year(season: str) -> int:
    """ "2025/26" -> 2025. Raises rather than guessing on anything else."""
    head = season.split("/", 1)[0]
    if len(head) != 4 or not head.isdigit():
        raise ValueError(f"{season!r} is not an FPL season label")
    return int(head)


def entries_by_season(managers: Iterable[SweptManager]) -> dict[str, int]:
    """Largest rank seen per season: a lower bound on that season's entries.

    Biased low, and knowingly. The alternative is hardcoding historical entry
    counts that cannot be checked against anything the API still serves.
    """
    largest: dict[str, int] = {}
    for manager in managers:
        for season in manager.seasons:
            if season.rank > largest.get(season.season, 0):
                largest[season.season] = season.rank
    return largest


def _percentile(rank: int, entries: int) -> float:
    """Share of the field finishing below this rank. 1.0 is first."""
    if entries <= 1:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (rank - 1) / (entries - 1)))


def _weight(start_year: int, latest_year: int, settings: EliteSettings) -> float:
    ages = max(0, latest_year - start_year)
    weight = settings.decay_per_season**ages
    if start_year < settings.rules_changed_in:
        weight *= settings.pre_rules_change_weight
    return weight


@dataclass(frozen=True)
class EliteScore:
    entry_id: int
    score: float
    """Shrunk, weighted mean percentile. Higher is better."""
    seasons_counted: int
    total_weight: float
    best_percentile: float
    latest_percentile: float | None
    latest_season: str | None


def rank_elite(
    managers: Sequence[SweptManager],
    *,
    entries: Mapping[str, int] | None = None,
    settings: EliteSettings = DEFAULT_SETTINGS,
    top: int = 500,
) -> tuple[EliteScore, ...]:
    """Score every manager and return the best `top` of them."""
    if not managers:
        return ()
    if top <= 0:
        raise ValueError("a ranking needs a positive size")

    field = dict(entries) if entries is not None else entries_by_season(managers)
    missing = sorted(
        {
            season.season
            for manager in managers
            for season in manager.seasons
            if season.season not in field
        }
    )
    if missing:
        raise ValueError(f"no entry count for seasons {missing}")

    latest_year = max(
        season_start_year(season.season) for manager in managers for season in manager.seasons
    )

    percentiles: dict[int, list[tuple[float, float, str]]] = {}
    for manager in managers:
        rows: list[tuple[float, float, str]] = []
        for season in manager.seasons:
            start = season_start_year(season.season)
            rows.append(
                (
                    _percentile(season.rank, field[season.season]),
                    _weight(start, latest_year, settings),
                    season.season,
                )
            )
        percentiles[manager.entry_id] = rows

    # An unknown manager is the median of the field, not the average member of a
    # catalogue selected for being well above it.
    prior = settings.prior_percentile

    scored: list[EliteScore] = []
    for manager in managers:
        rows = percentiles[manager.entry_id]
        if len(rows) < settings.minimum_seasons:
            continue

        weight_sum = sum(weight for _, weight, _ in rows)
        weighted = sum(p * w for p, w, _ in rows)
        score = (weighted + settings.shrinkage_weight * prior) / (
            weight_sum + settings.shrinkage_weight
        )
        newest = max(rows, key=lambda row: season_start_year(row[2]))

        scored.append(
            EliteScore(
                entry_id=manager.entry_id,
                score=score,
                seasons_counted=len(rows),
                total_weight=weight_sum,
                best_percentile=max(p for p, _, _ in rows),
                latest_percentile=newest[0],
                latest_season=newest[2],
            )
        )

    scored.sort(key=lambda row: (-row.score, row.entry_id))
    return tuple(scored[:top])
