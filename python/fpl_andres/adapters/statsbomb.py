from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from fpl_andres.models.deployment import DeploymentRoleObservation, ObservedRole

_STATSBOMB_POSITION_TO_ROLE: dict[str, ObservedRole] = {
    "Goalkeeper": "goalkeeper",
    "Right Back": "full_back",
    "Left Back": "full_back",
    "Right Wing Back": "wing_back",
    "Left Wing Back": "wing_back",
    "Right Center Back": "centre_back",
    "Left Center Back": "centre_back",
    "Center Back": "centre_back",
    "Right Defensive Midfield": "defensive_midfield",
    "Left Defensive Midfield": "defensive_midfield",
    "Center Defensive Midfield": "defensive_midfield",
    "Defensive Midfield": "defensive_midfield",
    "Right Midfield": "central_midfield",
    "Left Midfield": "central_midfield",
    "Center Midfield": "central_midfield",
    "Right Center Midfield": "central_midfield",
    "Left Center Midfield": "central_midfield",
    "Right Attacking Midfield": "attacking_midfield",
    "Left Attacking Midfield": "attacking_midfield",
    "Center Attacking Midfield": "attacking_midfield",
    "Right Wing": "wide_forward",
    "Left Wing": "wide_forward",
    "Right Center Forward": "striker",
    "Left Center Forward": "striker",
    "Center Forward": "striker",
    "Secondary Striker": "striker",
    "Striker": "striker",
}


class StatsbombAdapterError(ValueError):
    """Raised when a StatsBomb payload does not match the expected shape."""


@dataclass(frozen=True)
class StatsbombRoleRow:
    statsbomb_player_id: int
    observation: DeploymentRoleObservation


def map_statsbomb_position(position_name: str) -> ObservedRole:
    role = _STATSBOMB_POSITION_TO_ROLE.get(position_name)
    if role is None:
        raise StatsbombAdapterError(f"unknown StatsBomb position: {position_name!r}")
    return role


def parse_lineup_role_observations(
    lineup_bytes: bytes,
    *,
    event_id: int,
    kickoff_time: datetime,
    minimum_minutes: int = 60,
) -> tuple[StatsbombRoleRow, ...]:
    if isinstance(event_id, bool) or not 1 <= event_id <= 38:
        raise StatsbombAdapterError("event_id must be between 1 and 38")
    if kickoff_time.tzinfo is None or kickoff_time.utcoffset() != timedelta(0):
        raise StatsbombAdapterError("kickoff_time must be an aware UTC timestamp")
    if isinstance(minimum_minutes, bool) or minimum_minutes < 1:
        raise StatsbombAdapterError("minimum_minutes must be a positive integer")

    try:
        payload = json.loads(lineup_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StatsbombAdapterError("lineup payload is not UTF-8 JSON") from error
    if not isinstance(payload, list):
        raise StatsbombAdapterError("lineup payload must be a list of team lineups")

    rows: list[StatsbombRoleRow] = []
    for team_entry in payload:
        if not isinstance(team_entry, dict):
            raise StatsbombAdapterError("team lineup entry must be an object")
        lineup = team_entry.get("lineup")
        if not isinstance(lineup, list):
            raise StatsbombAdapterError("team lineup missing lineup array")
        for player_entry in lineup:
            row = _row_for_player(
                player_entry,
                event_id=event_id,
                kickoff_time=kickoff_time,
                minimum_minutes=minimum_minutes,
            )
            if row is not None:
                rows.append(row)
    return tuple(rows)


def hash_statsbomb_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _row_for_player(
    player_entry: object,
    *,
    event_id: int,
    kickoff_time: datetime,
    minimum_minutes: int,
) -> StatsbombRoleRow | None:
    if not isinstance(player_entry, dict):
        raise StatsbombAdapterError("player entry must be an object")
    raw_player_id = player_entry.get("player_id")
    if not isinstance(raw_player_id, int) or raw_player_id <= 0:
        raise StatsbombAdapterError("player_id must be a positive integer")

    positions = player_entry.get("positions")
    if not isinstance(positions, list) or not positions:
        return None

    dominant_role: ObservedRole | None = None
    dominant_minutes = 0
    total_minutes = 0
    for entry in positions:
        role, minutes = _role_and_minutes(entry)
        total_minutes += minutes
        if minutes > dominant_minutes:
            dominant_role = role
            dominant_minutes = minutes

    if dominant_role is None:
        return None
    if total_minutes < minimum_minutes:
        return None
    if total_minutes > 130:
        total_minutes = 130

    observation = DeploymentRoleObservation(
        event_id=event_id,
        observed_role=dominant_role,
        minutes_played=total_minutes,
        kickoff_time=kickoff_time,
        role_probability=None,
    )
    return StatsbombRoleRow(
        statsbomb_player_id=raw_player_id,
        observation=observation,
    )


def _role_and_minutes(position_entry: object) -> tuple[ObservedRole, int]:
    if not isinstance(position_entry, dict):
        raise StatsbombAdapterError("position entry must be an object")
    position_name = position_entry.get("position")
    if not isinstance(position_name, str):
        raise StatsbombAdapterError("position entry missing position name")
    role = map_statsbomb_position(position_name)

    from_string = position_entry.get("from")
    to_string = position_entry.get("to")
    if not isinstance(from_string, str):
        raise StatsbombAdapterError("position entry missing from time")
    from_seconds = _parse_ms(from_string)
    # Absent to means the player stayed on until the final whistle.
    to_seconds = _parse_ms(to_string) if isinstance(to_string, str) else 90 * 60
    minutes = max(0, (to_seconds - from_seconds) // 60)
    return role, minutes


def _parse_ms(value: str) -> int:
    try:
        minutes_part, seconds_part = value.split(":")
        return int(minutes_part) * 60 + int(seconds_part)
    except (ValueError, AttributeError) as error:
        raise StatsbombAdapterError(f"invalid mm:ss time value: {value!r}") from error
