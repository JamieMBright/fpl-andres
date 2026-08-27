"""Score a frozen xStart field against one immutable settled gameweek."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

__all__ = ["evaluate_xstart"]

_LOG_EPSILON = 1e-6


def _round(value: float) -> float:
    return round(value, 6)


def _metrics(rows: list[tuple[int, str, float, int]]) -> dict[str, int | float]:
    count = len(rows)
    if count == 0:
        raise ValueError("xStart scoring requires at least one joined player")
    brier = sum((forecast - actual) ** 2 for _, _, forecast, actual in rows) / count
    log_loss = (
        -sum(
            actual * math.log(min(1 - _LOG_EPSILON, max(_LOG_EPSILON, forecast)))
            + (1 - actual) * math.log(min(1 - _LOG_EPSILON, max(_LOG_EPSILON, 1 - forecast)))
            for _, _, forecast, actual in rows
        )
        / count
    )
    return {
        "count": count,
        "brier": _round(brier),
        "logLoss": _round(log_loss),
        "meanForecast": _round(sum(row[2] for row in rows) / count),
        "actualStartRate": _round(sum(row[3] for row in rows) / count),
    }


def _reliability(rows: list[tuple[int, str, float, int]]) -> list[dict[str, Any]]:
    bands: list[dict[str, Any]] = []
    for index in range(10):
        lower = index / 10
        upper = (index + 1) / 10
        selected = [
            row for row in rows if lower <= row[2] < upper or (index == 9 and row[2] == upper)
        ]
        if not selected:
            continue
        bands.append(
            {
                "label": f"{lower:.1f}-{upper:.1f}",
                "lower": lower,
                "upper": upper,
                **_metrics(selected),
            }
        )
    return bands


def evaluate_xstart(
    inputs: Mapping[str, Any],
    live_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if live_snapshot.get("event") != 1 or live_snapshot.get("roundComplete") is not True:
        raise ValueError("xStart evaluation requires a settled gameweek 1 snapshot")
    players = inputs.get("players")
    elements = live_snapshot.get("elements")
    if not isinstance(players, list) or not isinstance(elements, list):
        raise ValueError("xStart evaluation requires player and live element rows")
    starts = {
        int(row["id"]): int(stats.get("starts", 0))
        for row in elements
        if isinstance(row, Mapping)
        and isinstance(row.get("id"), int)
        and isinstance((stats := row.get("stats")), Mapping)
        and isinstance(stats.get("starts", 0), int | float)
    }
    rows: list[tuple[int, str, float, int]] = []
    for player in players:
        if not isinstance(player, Mapping):
            continue
        element_id = player.get("id")
        club = player.get("club")
        forecast = player.get("startRate")
        if (
            not isinstance(element_id, int)
            or not isinstance(club, str)
            or not isinstance(forecast, int | float)
            or element_id not in starts
        ):
            continue
        probability = float(forecast)
        if not 0.0 <= probability <= 1.0:
            raise ValueError(f"element {element_id} has an invalid xStart probability")
        rows.append((element_id, club, probability, starts[element_id]))
    if not rows:
        raise ValueError("no frozen xStart players joined the settled snapshot")

    clubs: list[dict[str, Any]] = []
    total_hits = 0
    total_actual = 0
    for club in sorted({row[1] for row in rows}):
        club_rows = [row for row in rows if row[1] == club]
        if len(club_rows) < 11:
            raise ValueError(
                f"club {club} has only {len(club_rows)} xStart candidates; "
                "top-11 scoring requires eleven"
            )
        selected = sorted(club_rows, key=lambda row: (-row[2], row[0]))[:11]
        actual_starters = sum(row[3] for row in club_rows)
        hits = sum(row[3] for row in selected)
        selected_ids = {row[0] for row in selected}
        total_hits += hits
        total_actual += actual_starters
        clubs.append(
            {
                "club": club,
                **_metrics(club_rows),
                "topElevenHits": hits,
                "actualStarters": actual_starters,
                "topElevenRecall": _round(hits / actual_starters) if actual_starters else None,
                "selected": [
                    {
                        "elementId": element_id,
                        "probability": _round(probability),
                        "started": bool(started),
                    }
                    for element_id, _club, probability, started in selected
                ],
                "missedStarters": [
                    {"elementId": element_id, "probability": _round(probability)}
                    for element_id, _club, probability, started in club_rows
                    if started and element_id not in selected_ids
                ],
            }
        )

    return {
        "field": "probabilitySixtyMinutesAsShipped",
        "population": _metrics(rows),
        "topEleven": {
            "hits": total_hits,
            "actualStarters": total_actual,
            "recall": _round(total_hits / total_actual) if total_actual else None,
        },
        "reliability": _reliability(rows),
        "clubs": clubs,
    }
