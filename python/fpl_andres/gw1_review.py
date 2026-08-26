"""Reproduce the event projection that was shipped before a deadline."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from fpl_andres.artifacts import GW1_REVIEW_SCHEMA_VERSION

__all__ = ["ReviewBand", "band_for", "build_review_artifact", "frozen_points_at_event"]

ReviewBand = Literal["below", "as_projected", "above", "haul"]

ROUTES = (
    "appearance",
    "attacking",
    "cleanSheet",
    "bonus",
    "saves",
    "conceding",
    "yellowCards",
    "redCards",
    "ownGoals",
    "penaltiesMissed",
    "defensiveContribution",
)


def _number(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key, 0.0)
    return float(value) if isinstance(value, int | float) else 0.0


def _market_value(
    quoted: float,
    baseline: float,
    event_index: int,
    anchor_index: int,
    half_life: float,
) -> float:
    if event_index < anchor_index:
        weight = 0.0
    elif half_life <= 0:
        weight = 1.0 if event_index == anchor_index else 0.0
    else:
        weight = 0.5 ** ((event_index - anchor_index) / half_life)
    return baseline + (quoted - baseline) * weight


def _routes_at_event(
    inputs: Mapping[str, Any],
    player: Mapping[str, Any],
    event_index: int,
) -> dict[str, float]:
    routes = player.get("routes")
    if not isinstance(routes, Mapping):
        return {route: 0.0 for route in ROUTES}
    market = inputs.get("marketCarry")
    if not isinstance(market, Mapping):
        return {route: _number(routes, route) for route in ROUTES}
    carried_players = market.get("players")
    player_id = player.get("id")
    if not isinstance(carried_players, Mapping) or not isinstance(player_id, int):
        return {route: _number(routes, route) for route in ROUTES}
    carry = carried_players.get(str(player_id))
    if not isinstance(carry, list) or len(carry) != 6:
        return {route: _number(routes, route) for route in ROUTES}
    anchor_index = int(carry[0])
    participation = float(carry[2])
    baselines = {
        "attacking": float(carry[3]),
        "yellowCards": float(carry[4]),
        "redCards": float(carry[5]),
    }
    half_life = _number(market, "halfLifeGameweeks")
    result: dict[str, float] = {}
    for route in ROUTES:
        current = _number(routes, route)
        baseline = baselines.get(
            route,
            current / participation if participation > 0 else current,
        )
        result[route] = _market_value(
            current,
            baseline,
            event_index,
            anchor_index,
            half_life,
        )
    return result


def _defcon_points(historical: float, pressure_total: float, fixtures: int) -> float:
    if fixtures <= 0:
        return 0.0
    probability = min(1.0, max(0.0, historical / 2.0))
    if probability in (0.0, 1.0):
        return probability * 2.0 * fixtures
    pressure = pressure_total / fixtures
    adjusted = (probability * pressure) / (1.0 - probability + probability * pressure)
    return adjusted * 2.0 * fixtures


def frozen_points_at_event(
    inputs: Mapping[str, Any],
    player: Mapping[str, Any],
    event_index: int,
) -> float:
    club = player.get("club")
    ladder_by_club = inputs.get("fixtureLadder")
    opponents_by_club = inputs.get("opponents")
    events = inputs.get("events")
    if (
        not isinstance(club, str)
        or not isinstance(ladder_by_club, Mapping)
        or not isinstance(opponents_by_club, Mapping)
        or not isinstance(events, list)
        or not 0 <= event_index < len(events)
    ):
        return 0.0
    ladder = ladder_by_club.get(club)
    opponents = opponents_by_club.get(club)
    if not isinstance(ladder, Mapping) or not isinstance(opponents, list):
        return 0.0

    def rung(name: str) -> float | None:
        values = ladder.get(name)
        if not isinstance(values, list) or event_index >= len(values):
            return None
        value = values[event_index]
        return float(value) if isinstance(value, int | float) else None

    attacking = rung("attacking")
    defensive = rung("defensive")
    saves = rung("saves")
    conceding = rung("conceding")
    defcon = rung("defensiveContribution")
    if (
        attacking is None
        or defensive is None
        or saves is None
        or conceding is None
        or defcon is None
    ):
        return 0.0
    fixtures_at_event = opponents[event_index] if event_index < len(opponents) else []
    fixtures = len(fixtures_at_event) if isinstance(fixtures_at_event, list) else 0
    routes = _routes_at_event(inputs, player, event_index)

    player_id = player.get("id")
    overrides = inputs.get("bonusOverrides")
    event_overrides = (
        overrides.get(str(events[event_index])) if isinstance(overrides, Mapping) else None
    )
    override = (
        event_overrides.get(str(player_id))
        if isinstance(event_overrides, Mapping) and isinstance(player_id, int)
        else None
    )
    bonus = float(override) if isinstance(override, int | float) else routes["bonus"] * fixtures
    return (
        routes["appearance"] * fixtures
        + bonus
        + routes["yellowCards"] * fixtures
        + routes["redCards"] * fixtures
        + routes["ownGoals"] * fixtures
        + routes["penaltiesMissed"] * fixtures
        + routes["attacking"] * attacking
        + routes["cleanSheet"] * defensive
        + routes["saves"] * saves
        + routes["conceding"] * conceding
        + _defcon_points(routes["defensiveContribution"], defcon, fixtures)
    )


def band_for(actual_points: int, frozen_xpts: float) -> ReviewBand:
    if actual_points >= 8 and actual_points >= frozen_xpts * 2:
        return "haul"
    if actual_points > frozen_xpts + 0.5:
        return "above"
    if actual_points < frozen_xpts - 0.5:
        return "below"
    return "as_projected"


def _integer(row: Mapping[str, Any], key: str) -> int:
    value = row.get(key, 0)
    return int(value) if isinstance(value, int | float) else 0


def _actual_line(stats: Mapping[str, Any]) -> dict[str, int]:
    return {
        "starts": _integer(stats, "starts"),
        "minutes": _integer(stats, "minutes"),
        "goals": _integer(stats, "goals_scored"),
        "assists": _integer(stats, "assists"),
        "cleanSheets": _integer(stats, "clean_sheets"),
        "goalsConceded": _integer(stats, "goals_conceded"),
        "ownGoals": _integer(stats, "own_goals"),
        "penaltiesSaved": _integer(stats, "penalties_saved"),
        "penaltiesMissed": _integer(stats, "penalties_missed"),
        "yellowCards": _integer(stats, "yellow_cards"),
        "redCards": _integer(stats, "red_cards"),
        "saves": _integer(stats, "saves"),
        "bonus": _integer(stats, "bonus"),
        "defensiveContribution": _integer(stats, "defensive_contribution"),
    }


def build_review_artifact(
    inputs: Mapping[str, Any],
    live_snapshot: Mapping[str, Any],
    picks_payload: Mapping[str, Any],
    *,
    entry_id: int,
    generated_at: datetime,
    canonical_manifest_revision: str,
    recorded_code_revision: str,
    canonical_model_version: str,
    canonical_deadline: str,
    canonical_frozen_at: str,
    live_source_hash: str,
    picks_source_hash: str,
) -> dict[str, Any]:
    if generated_at.tzinfo is None:
        raise ValueError("review generation time must carry a timezone")
    if live_snapshot.get("event") != 1 or live_snapshot.get("roundComplete") is not True:
        raise ValueError("the review requires a settled gameweek 1 live snapshot")
    input_players = inputs.get("players")
    live_elements = live_snapshot.get("elements")
    picks = picks_payload.get("picks")
    if not isinstance(input_players, list) or not isinstance(live_elements, list):
        raise ValueError("review inputs must publish player and live element rows")
    if not isinstance(picks, list) or len(picks) != 15:
        raise ValueError("the observed team must publish exactly fifteen picks")

    players = {
        int(row["id"]): row
        for row in input_players
        if isinstance(row, Mapping) and isinstance(row.get("id"), int)
    }
    live = {
        int(row["id"]): row.get("stats")
        for row in live_elements
        if isinstance(row, Mapping)
        and isinstance(row.get("id"), int)
        and isinstance(row.get("stats"), Mapping)
    }
    rows: list[dict[str, Any]] = []
    for pick in picks:
        if not isinstance(pick, Mapping):
            raise ValueError("the observed team contains a malformed pick")
        element_id = pick.get("element")
        if not isinstance(element_id, int) or element_id not in players or element_id not in live:
            raise ValueError(f"review evidence is missing element {element_id}")
        player = players[element_id]
        stats = live[element_id]
        assert isinstance(stats, Mapping)
        actual_points = _integer(stats, "total_points")
        multiplier = _integer(pick, "multiplier")
        frozen_xpts = frozen_points_at_event(inputs, player, 0)
        rows.append(
            {
                "elementId": element_id,
                "squadPosition": _integer(pick, "position"),
                "multiplier": multiplier,
                "isCaptain": pick.get("is_captain") is True,
                "isViceCaptain": pick.get("is_vice_captain") is True,
                "identity": {
                    "code": _integer(player, "code"),
                    "name": str(player.get("name", element_id)),
                    "position": str(player.get("position", "UNK")),
                    "club": str(player.get("club", "UNK")),
                    "teamId": _integer(player, "teamId"),
                    "priceTenths": _integer(player, "priceTenths"),
                },
                "actualPoints": actual_points,
                "countedPoints": actual_points * multiplier,
                "frozenXpts": round(frozen_xpts, 6),
                "opponentNeutralXpts": round(_number(player, "basePoints"), 6),
                "delta": round(actual_points - frozen_xpts, 6),
                "band": band_for(actual_points, frozen_xpts),
                "startRateAsShipped": round(_number(player, "startRate"), 6),
                "actual": _actual_line(stats),
            }
        )
    rows.sort(key=lambda row: int(row["squadPosition"]))
    calculated = sum(int(row["countedPoints"]) for row in rows)
    bench_points = sum(int(row["actualPoints"]) for row in rows if int(row["squadPosition"]) > 11)
    history = picks_payload.get("entry_history")
    official = history.get("points") if isinstance(history, Mapping) else None
    if not isinstance(official, int) or calculated != official:
        raise ValueError(
            f"observed team points do not reconcile: calculated {calculated}, published {official}"
        )
    return {
        "schemaVersion": GW1_REVIEW_SCHEMA_VERSION,
        "season": "2026-27",
        "event": 1,
        "generatedAt": generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "canonicalManifestRevision": canonical_manifest_revision,
        "recordedCodeRevision": recorded_code_revision,
        "canonicalModelVersion": canonical_model_version,
        "canonicalDeadline": canonical_deadline,
        "canonicalFrozenAt": canonical_frozen_at,
        "evidence": {
            "frozenInputs": canonical_manifest_revision,
            "liveSourceHash": live_source_hash,
            "liveCapturedAt": live_snapshot.get("capturedAt"),
            "picksSourceHash": picks_source_hash,
            "picksObservedAt": generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "level": "observed",
        },
        "team": {
            "entryId": entry_id,
            "points": official,
            "benchPoints": bench_points,
            "activeChip": picks_payload.get("active_chip"),
        },
        "picks": rows,
    }
