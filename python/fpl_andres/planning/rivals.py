"""Read a mini-league's rival squads to measure ownership inside it.

Global ownership is the wrong denominator when the target is a specific league.
A player owned by four percent of the world and by half of your league is a
template pick in the only table that matters to you.

Rival picks are only legal to read after a deadline has passed, which the FPL
API enforces by returning 404 for an unstarted event. That constraint is
respected rather than worked around: this reads a completed gameweek.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fpl_andres.adapters.fpl import FplClient, FplPicksUnavailable
from fpl_andres.planning.ownership import EffectiveOwnership, effective_ownership

__all__ = ["LeagueSnapshot", "RivalSquad", "differentials", "read_league"]


@dataclass(frozen=True)
class RivalSquad:
    entry_id: int
    entry_name: str
    player_name: str
    rank: int | None
    total_points: int | None
    picks: tuple[int, ...]
    captain: int | None
    vice_captain: int | None


@dataclass(frozen=True)
class LeagueSnapshot:
    league_id: int
    league_name: str
    event: int
    squads: tuple[RivalSquad, ...]
    unavailable: tuple[int, ...]
    source_hashes: tuple[str, ...]

    def ownership(self) -> dict[int, EffectiveOwnership]:
        return effective_ownership(
            [list(squad.picks) for squad in self.squads],
            [squad.captain for squad in self.squads],
        )


async def read_league(
    client: FplClient,
    league_id: int,
    *,
    event: int,
    limit: int = 50,
) -> LeagueSnapshot:
    """Fetch standings and every rival's picks for one completed gameweek.

    Entries whose picks are unavailable are named in ``unavailable`` rather than
    silently dropped: an ownership figure computed over an unknown subset of the
    league would be worse than no figure at all.
    """
    if limit < 1:
        raise ValueError("limit must be at least one entry")

    standings = await client.fetch_standings(league_id)
    payload = standings.payload
    league = payload.get("league") or {}
    results = ((payload.get("standings") or {}).get("results") or [])[:limit]

    hashes = [standings.snapshot.content_hash]
    squads: list[RivalSquad] = []
    unavailable: list[int] = []

    for entry in results:
        entry_id = int(entry["entry"])
        try:
            picks = await client.fetch_entry_picks(entry_id, event=event)
        except FplPicksUnavailable:
            unavailable.append(entry_id)
            continue

        hashes.append(picks.snapshot.content_hash)
        squads.append(_squad_from(entry, entry_id, picks.payload))

    return LeagueSnapshot(
        league_id=league_id,
        league_name=str(league.get("name") or f"League {league_id}"),
        event=event,
        squads=tuple(squads),
        unavailable=tuple(unavailable),
        source_hashes=tuple(sorted(set(hashes))),
    )


def _squad_from(entry: Mapping[str, Any], entry_id: int, payload: Mapping[str, Any]) -> RivalSquad:
    elements: list[int] = []
    captain: int | None = None
    vice_captain: int | None = None
    for pick in payload.get("picks") or []:
        element_id = int(pick["element"])
        elements.append(element_id)
        if pick.get("is_captain"):
            captain = element_id
        if pick.get("is_vice_captain"):
            vice_captain = element_id

    return RivalSquad(
        entry_id=entry_id,
        entry_name=str(entry.get("entry_name") or ""),
        player_name=str(entry.get("player_name") or ""),
        rank=_optional_int(entry.get("rank")),
        total_points=_optional_int(entry.get("total")),
        picks=tuple(elements),
        captain=captain,
        vice_captain=vice_captain,
    )


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def differentials(
    snapshot: LeagueSnapshot,
    mine: Sequence[int],
    projected: Mapping[int, float],
    *,
    minimum_points: float = 0.0,
) -> list[tuple[int, float, float]]:
    """Players worth owning that the league mostly does not, best first.

    Returns element id, effective ownership, and the points you would gain on
    the average rival by holding them.
    """
    ownership = snapshot.ownership()
    held = set(mine)
    rows = [
        (
            element_id,
            ownership[element_id].effective if element_id in ownership else 0.0,
            (1.0 - (ownership[element_id].effective if element_id in ownership else 0.0)) * points,
        )
        for element_id, points in projected.items()
        if element_id not in held and points >= minimum_points
    ]
    return sorted(rows, key=lambda row: -row[2])
