"""Short purchase hold for players whose FPL club assignment just changed."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from fpl_andres.jsonio import read_json_file

__all__ = ["recent_transfer_holds"]


def recent_transfer_holds(path: Path) -> dict[int, int]:
    if not path.exists():
        return {}
    artifact = read_json_file(path)
    players = artifact.get("players")
    if not isinstance(players, list):
        raise ValueError(f"season inputs publish no players list: {path}")
    holds: dict[int, int] = {}
    for player in players:
        if not isinstance(player, Mapping) or not isinstance(player.get("code"), int):
            continue
        change = player.get("recentClubChange")
        if not isinstance(change, Mapping):
            continue
        avoid_until = change.get("avoidUntilEvent")
        if isinstance(avoid_until, int):
            holds[int(player["code"])] = avoid_until
    return holds


def _blocked_recent_transfer_codes(path: Path, event: int) -> set[int]:
    return {
        code for code, avoid_until in recent_transfer_holds(path).items() if event <= avoid_until
    }
