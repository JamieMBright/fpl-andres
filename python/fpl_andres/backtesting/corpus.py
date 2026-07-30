"""Read a season out of the history corpus.

PostgREST caps a response, so every read pages explicitly. A season is a few
tens of thousands of rows, which is small enough to hold in memory and walk
repeatedly, and doing so keeps the cutoff logic in one place rather than
spread across dozens of queries.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fpl_andres.persistence.supabase import SupabaseRestClient

__all__ = [
    "CorpusLoadError",
    "ElementRow",
    "SeasonCorpus",
    "load_season",
]

_PAGE_SIZE = 1000
_STAT_COLUMNS = (
    "season,gameweek,element_id,element_code,fixture_id,minutes,starts,"
    "goals_scored,assists,clean_sheets,goals_conceded,saves,bonus,bps,"
    "expected_goals,expected_assists,expected_goals_conceded,"
    "defensive_contribution,total_points,value,selected,was_home,opponent_team,"
    "kickoff_time"
)


class CorpusLoadError(RuntimeError):
    """Raised when the corpus cannot supply a usable season."""


@dataclass(frozen=True)
class ElementRow:
    """One player's observed return in one fixture."""

    gameweek: int
    element_id: int
    element_code: int
    fixture_id: int
    minutes: int
    started: bool
    goals: int
    assists: int
    expected_goals: float | None
    expected_assists: float | None
    total_points: int
    price_tenths: int | None
    selected: int | None
    kickoff_time: datetime


@dataclass
class SeasonCorpus:
    """Every observation for one season, indexed for walk-forward reads."""

    season: str
    rows_by_gameweek: dict[int, list[ElementRow]] = field(default_factory=dict)
    position_by_element: dict[int, int] = field(default_factory=dict)
    team_by_element: dict[int, int] = field(default_factory=dict)
    name_by_element: dict[int, str] = field(default_factory=dict)

    @property
    def gameweeks(self) -> tuple[int, ...]:
        return tuple(sorted(self.rows_by_gameweek))

    @property
    def total_rows(self) -> int:
        return sum(len(rows) for rows in self.rows_by_gameweek.values())

    def before(self, gameweek: int) -> list[ElementRow]:
        """Every row from strictly earlier gameweeks.

        The only supported way to read history during a backtest: it makes the
        cutoff structural rather than something each caller must remember.
        """
        history: list[ElementRow] = []
        for event in sorted(self.rows_by_gameweek):
            if event >= gameweek:
                break
            history.extend(self.rows_by_gameweek[event])
        return history

    def actual_points(self, gameweek: int) -> dict[int, int]:
        """Realised points per element, summed across a double gameweek."""
        totals: dict[int, int] = {}
        for row in self.rows_by_gameweek.get(gameweek, ()):
            totals[row.element_id] = totals.get(row.element_id, 0) + row.total_points
        return totals


def load_season(client: SupabaseRestClient, season: str) -> SeasonCorpus:
    """Page a whole season of observations into memory."""
    elements = _page(
        client,
        "elements",
        columns="element_id,element_type,team_id,web_name",
        filters={"season": f"eq.{season}"},
        order="element_id",
    )
    if not elements:
        raise CorpusLoadError(f"corpus holds no elements for {season}")

    corpus = SeasonCorpus(season=season)
    for element in elements:
        element_id = int(element["element_id"])
        corpus.position_by_element[element_id] = int(element["element_type"])
        corpus.team_by_element[element_id] = int(element["team_id"])
        corpus.name_by_element[element_id] = str(element["web_name"])

    stats = _page(
        client,
        "element_gameweek_stats",
        columns=_STAT_COLUMNS,
        filters={"season": f"eq.{season}"},
        order="gameweek,element_id,fixture_id",
    )
    if not stats:
        raise CorpusLoadError(f"corpus holds no gameweek rows for {season}")

    for row in stats:
        gameweek = int(row["gameweek"])
        corpus.rows_by_gameweek.setdefault(gameweek, []).append(
            ElementRow(
                gameweek=gameweek,
                element_id=int(row["element_id"]),
                element_code=int(row["element_code"]),
                fixture_id=int(row["fixture_id"]),
                minutes=int(row["minutes"]),
                # `starts` is absent before 2022/23; minutes is the fallback signal.
                started=bool(row["starts"]) if row.get("starts") is not None else False,
                goals=int(row["goals_scored"]),
                assists=int(row["assists"]),
                expected_goals=_optional_float(row.get("expected_goals")),
                expected_assists=_optional_float(row.get("expected_assists")),
                total_points=int(row["total_points"]),
                price_tenths=_optional_int(row.get("value")),
                selected=_optional_int(row.get("selected")),
                kickoff_time=_kickoff(row.get("kickoff_time"), gameweek),
            )
        )

    return corpus


def _kickoff(raw: Any, gameweek: int) -> datetime:
    """Parse a kickoff, falling back to a synthetic ordering when absent.

    Only the ordering matters to the models; a missing kickoff must not drop the
    row, because the gameweek itself already establishes the sequence.
    """
    if raw:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return parsed.astimezone(UTC)
    return datetime(2000, 1, 1, tzinfo=UTC) + timedelta(days=7 * gameweek)


def _page(
    client: SupabaseRestClient,
    table: str,
    *,
    columns: str,
    filters: dict[str, str],
    order: str,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = client.select(
            table,
            columns=columns,
            filters={**filters, "offset": str(offset)},
            order=order,
            limit=_PAGE_SIZE,
        )
        collected.extend(page)
        if len(page) < _PAGE_SIZE:
            return collected
        offset += _PAGE_SIZE


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def summarise(corpus: SeasonCorpus) -> str:
    return (
        f"{corpus.season}: {corpus.total_rows:,} rows across "
        f"{len(corpus.gameweeks)} gameweeks, {len(corpus.position_by_element):,} elements"
    )


def require_gameweeks(corpus: SeasonCorpus, minimum: int) -> Sequence[int]:
    gameweeks = corpus.gameweeks
    if len(gameweeks) < minimum:
        raise CorpusLoadError(
            f"{corpus.season} holds {len(gameweeks)} gameweeks, need at least {minimum}"
        )
    return gameweeks
