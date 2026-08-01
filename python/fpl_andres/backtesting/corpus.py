"""Read a season out of the history corpus.

PostgREST caps a response, so every read pages explicitly. A season is a few
tens of thousands of rows, which is small enough to hold in memory and walk
repeatedly, and doing so keeps the cutoff logic in one place rather than
spread across dozens of queries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fpl_andres.backtesting.fixtures import Fixture, TeamStrength
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
    "defensive_contribution,yellow_cards,red_cards,own_goals,penalties_saved,"
    "penalties_missed,total_points,value,selected,transfers_in,transfers_out,"
    "was_home,opponent_team,kickoff_time"
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
    clean_sheets: int = 0
    saves: int = 0
    bonus: int = 0
    goals_conceded: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    own_goals: int = 0
    penalties_saved: int = 0
    penalties_missed: int = 0
    # Raw CBIT/CBIRT count, not the awarded points; absent before 2025/26.
    defensive_contribution: int | None = None
    transfers_in: int | None = None
    transfers_out: int | None = None


@dataclass
class SeasonCorpus:
    """Every observation for one season, indexed for walk-forward reads."""

    season: str
    rows_by_gameweek: dict[int, list[ElementRow]] = field(default_factory=dict)
    position_by_element: dict[int, int] = field(default_factory=dict)
    team_by_element: dict[int, int] = field(default_factory=dict)
    name_by_element: dict[int, str] = field(default_factory=dict)
    # Given and family name, which foreign sources publish and web_name is not.
    full_name_by_element: dict[int, str] = field(default_factory=dict)
    # FPL reassigns element_id every season; code is the stable identity.
    code_by_element: dict[int, int] = field(default_factory=dict)
    price_by_element: dict[int, int] = field(default_factory=dict)
    # Club ids are reassigned each season too; the club code is not.
    code_by_team: dict[int, int] = field(default_factory=dict)
    short_name_by_team: dict[int, str] = field(default_factory=dict)
    name_by_team: dict[int, str] = field(default_factory=dict)
    fixtures_by_event: dict[int, list[Fixture]] = field(default_factory=dict)
    strength_cache: dict[int, dict[int, TeamStrength]] = field(default_factory=dict)

    def fixtures_before(self, gameweek: int) -> list[Fixture]:
        """Played fixtures from strictly earlier gameweeks."""
        earlier: list[Fixture] = []
        for event in sorted(self.fixtures_by_event):
            if event >= gameweek:
                break
            earlier.extend(self.fixtures_by_event[event])
        return earlier

    def fixtures_for(self, team_id: int, gameweek: int) -> list[Fixture]:
        """A team's fixtures in one gameweek: two in a double, none in a blank.

        The schedule is known before the deadline, so reading it forward is not
        a leak. Only the scores are withheld.
        """
        return [
            fixture
            for fixture in self.fixtures_by_event.get(gameweek, ())
            if team_id in (fixture.team_h, fixture.team_a)
        ]

    @property
    def gameweeks(self) -> tuple[int, ...]:
        return tuple(sorted(self.rows_by_gameweek))

    @property
    def missing_gameweeks(self) -> tuple[int, ...]:
        """Gameweeks absent from an otherwise contiguous run.

        A gap changes every aggregate the corpus produces - bias, error, season
        totals - and does it silently, because nothing downstream counts the
        weeks it was given. Reported rather than raised: an in-progress season
        is legitimately short, and only a hole in the middle is a fault.
        """
        played = self.gameweeks
        if len(played) < 2:
            return ()
        return tuple(
            event
            for event in range(played[0], played[-1] + 1)
            if event not in self.rows_by_gameweek
        )

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

    def rows_by_element_code(self) -> dict[int, list[ElementRow]]:
        """Every row keyed by the identity that survives a season rollover.

        ``element_id`` is reassigned each season; ``element_code`` is not, so it
        is the only way to recognise the same footballer a year later.
        """
        indexed: dict[int, list[ElementRow]] = {}
        for gameweek in sorted(self.rows_by_gameweek):
            for row in self.rows_by_gameweek[gameweek]:
                indexed.setdefault(row.element_code, []).append(row)
        return indexed

    @property
    def last_event(self) -> int:
        return max(self.rows_by_gameweek, default=0)


def load_season(client: SupabaseRestClient, season: str) -> SeasonCorpus:
    """Page a whole season of observations into memory."""
    elements = _page(
        client,
        "elements",
        columns="element_id,code,element_type,team_id,web_name,first_name,second_name,start_cost",
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
        corpus.full_name_by_element[element_id] = (
            f"{element['first_name']} {element['second_name']}".strip()
        )
        corpus.code_by_element[element_id] = int(element["code"])
        start_cost = _optional_int(element.get("start_cost"))
        if start_cost is not None:
            corpus.price_by_element[element_id] = start_cost

    for team in _page(
        client,
        "teams",
        columns="team_id,code,short_name,name",
        filters={"season": f"eq.{season}"},
        order="team_id",
    ):
        team_id = int(team["team_id"])
        corpus.code_by_team[team_id] = int(team["code"])
        corpus.short_name_by_team[team_id] = str(team["short_name"])
        corpus.name_by_team[team_id] = str(team["name"])
    stats = _page(
        client,
        "element_gameweek_stats",
        columns=_STAT_COLUMNS,
        filters={"season": f"eq.{season}"},
        order="gameweek,element_id,fixture_id",
    )
    if not stats:
        raise CorpusLoadError(f"corpus holds no gameweek rows for {season}")

    for fixture in _page(
        client,
        "fixtures",
        columns=("fixture_id,event,kickoff_time,team_h,team_a,team_h_score,team_a_score,finished"),
        filters={"season": f"eq.{season}"},
        order="event,fixture_id",
    ):
        event = _optional_int(fixture.get("event"))
        if event is None:
            continue
        corpus.fixtures_by_event.setdefault(event, []).append(
            Fixture(
                fixture_id=int(fixture["fixture_id"]),
                event=event,
                team_h=int(fixture["team_h"]),
                team_a=int(fixture["team_a"]),
                kickoff_time=_optional_kickoff(fixture.get("kickoff_time")),
                team_h_score=_optional_int(fixture.get("team_h_score")),
                team_a_score=_optional_int(fixture.get("team_a_score")),
                finished=bool(fixture.get("finished")),
            )
        )

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
                clean_sheets=int(row.get("clean_sheets") or 0),
                saves=int(row.get("saves") or 0),
                bonus=int(row.get("bonus") or 0),
                goals_conceded=int(row.get("goals_conceded") or 0),
                yellow_cards=int(row.get("yellow_cards") or 0),
                red_cards=int(row.get("red_cards") or 0),
                own_goals=int(row.get("own_goals") or 0),
                penalties_saved=int(row.get("penalties_saved") or 0),
                penalties_missed=int(row.get("penalties_missed") or 0),
                defensive_contribution=_optional_int(row.get("defensive_contribution")),
                transfers_in=_optional_int(row.get("transfers_in")),
                transfers_out=_optional_int(row.get("transfers_out")),
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


def _optional_kickoff(value: Any) -> datetime | None:
    return None if not value else datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def summarise(corpus: SeasonCorpus) -> str:
    return (
        f"{corpus.season}: {corpus.total_rows:,} rows across "
        f"{len(corpus.gameweeks)} gameweeks, {len(corpus.position_by_element):,} elements"
    )
