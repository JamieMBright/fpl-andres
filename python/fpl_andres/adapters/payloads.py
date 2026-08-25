"""The shapes this repository reads out of the FPL API.

The client returned ``dict[str, Any]`` for every endpoint,
which is honest about the transport and useless as documentation: nothing
recorded which of the roughly two hundred fields FPL sends are the ones this
project actually depends on, and a mistyped key type-checked cleanly and failed
at runtime.

These are ``total=False`` on purpose. A ``TypedDict`` here is not a promise
about what FPL sends -- it cannot be, because FPL publishes no schema and adds
fields without notice. It is a statement about what *we read*. Marking the keys
required would be claiming a guarantee nobody gave us, and would make mypy
enforce it at the wrong end: on our reads rather than on FPL's writes.

The enforcement that matters still lives where it always did -- ``rules.py``
refuses a bootstrap missing a controlling rule, ``bootstrap.py`` validates each
element through Pydantic, ``normalize_entry`` through ``FplEntry``. This layer
sits underneath those and answers a different question: if FPL renames a field,
which lines have to change?

Extra keys are permitted by construction: a ``TypedDict`` describes a subset of
a real dictionary, and every payload here arrives with far more than is listed.
"""

from __future__ import annotations

from typing import Any, TypedDict

# ---------------------------------------------------------------- bootstrap


class BootstrapEvent(TypedDict, total=False):
    """One gameweek, as ``bootstrap-static/`` describes it."""

    id: int
    deadline_time: str
    is_current: bool
    is_next: bool


class BootstrapElementType(TypedDict, total=False):
    """A position, with the squad rules attached to it."""

    id: int
    singular_name_short: str
    squad_select: int
    squad_min_play: int
    squad_max_play: int


class BootstrapChip(TypedDict, total=False):
    id: int
    name: str
    chip_type: str
    start_event: int | None
    stop_event: int | None
    overrides: dict[str, Any]


class BootstrapPayload(TypedDict, total=False):
    """``bootstrap-static/``.

    ``elements`` stays ``list[dict[str, Any]]`` because it is handed whole to
    ``bootstrap.parse_elements``, which validates each entry against a Pydantic
    model chosen by the caller. Two descriptions of the same rows, one checked
    and one not, is worse than one.

    ``game_settings`` and ``game_config`` stay loose for the opposite reason:
    ``rules.py`` walks them field by field and refuses anything missing, and it
    knows far more about their shape than a type could usefully say here.
    """

    total_players: int
    events: list[BootstrapEvent]
    elements: list[dict[str, Any]]
    element_types: list[BootstrapElementType]
    teams: list[dict[str, Any]]
    chips: list[BootstrapChip]
    game_settings: dict[str, Any]
    game_config: dict[str, Any]


# -------------------------------------------------------------------- entry


class EntryPayload(TypedDict, total=False):
    """``entry/{id}/``, as ``normalize_entry`` reads it."""

    id: int
    name: str
    started_event: int
    current_event: int | None
    last_deadline_bank: int
    last_deadline_value: int
    last_deadline_total_transfers: int


class PastSeason(TypedDict, total=False):
    season_name: str
    rank: int
    total_points: int
    rank_percentage: float


class EntryHistoryPayload(TypedDict, total=False):
    """``entry/{id}/history/``. Only ``past`` is read; ``current`` is not."""

    past: list[PastSeason]


# -------------------------------------------------------------------- picks


class EntryHistorySummary(TypedDict, total=False):
    event: int
    bank: int
    value: int
    event_transfers: int
    event_transfers_cost: int


class Pick(TypedDict, total=False):
    element: int
    position: int
    multiplier: int
    is_captain: bool
    is_vice_captain: bool


class PicksPayload(TypedDict, total=False):
    """``entry/{id}/event/{n}/picks/``."""

    active_chip: str | None
    entry_history: EntryHistorySummary
    picks: list[Pick]


# ---------------------------------------------------------------- standings


class StandingsResult(TypedDict, total=False):
    entry: int
    entry_name: str
    player_name: str
    rank: int
    total: int


class League(TypedDict, total=False):
    name: str


class Standings(TypedDict, total=False):
    results: list[StandingsResult]


class StandingsPayload(TypedDict, total=False):
    """``leagues-classic/{id}/standings/``."""

    league: League
    standings: Standings


# ----------------------------------------------------------------- fixtures


class FixturePayload(TypedDict, total=False):
    """One entry of ``fixtures/``."""

    id: int
    event: int | None
    team_h: int
    team_a: int


__all__ = [
    "BootstrapChip",
    "BootstrapElementType",
    "BootstrapEvent",
    "BootstrapPayload",
    "EntryHistoryPayload",
    "EntryHistorySummary",
    "EntryPayload",
    "FixturePayload",
    "League",
    "PastSeason",
    "Pick",
    "PicksPayload",
    "Standings",
    "StandingsPayload",
    "StandingsResult",
]
