"""Read-only capability probe for historical API-Football odds.

This module deliberately does not archive or model prices. A catalogue of bet
types is not evidence that a plan can return historical fixture odds, so the
probe checks a completed-season fixture and reports only sanitized shape data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

import httpx

from fpl_andres.timeguard import require_utc

BASE_URL = "https://v3.football.api-sports.io"
LEAGUE = "39"
PLAYER_MARKET_WORDS = (
    "scorer",
    "assist",
    "save",
    "card",
    "booked",
    "shots",
    "tackle",
)

__all__ = ["HistoricalProbe", "probe_historical_seasons"]


@dataclass(frozen=True)
class HistoricalProbe:
    season: int
    status: str
    fixture_id: str | None
    bookmakers: int
    bets: int
    player_named_selections: int
    response_bytes: int
    fetched_at: datetime
    quota_remaining: int | None
    error: str | None


def _quota_remaining(response: httpx.Response) -> int | None:
    value = response.headers.get("x-ratelimit-requests-remaining")
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _error(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code}" if response.status_code >= 400 else None
    if response.status_code >= 400:
        return f"HTTP {response.status_code}"
    if not isinstance(payload, Mapping):
        return None
    errors = payload.get("errors")
    if not isinstance(errors, Mapping) or not errors:
        return None
    return "; ".join(f"{key}: {value}" for key, value in sorted(errors.items()))


def _response_rows(response: httpx.Response) -> list[Mapping[str, object]]:
    try:
        payload = response.json()
    except ValueError:
        return []
    if not isinstance(payload, Mapping) or not isinstance(payload.get("response"), list):
        return []
    return [row for row in payload["response"] if isinstance(row, Mapping)]


def _fixture_id(row: Mapping[str, object]) -> str | None:
    fixture = row.get("fixture")
    if not isinstance(fixture, Mapping) or fixture.get("id") is None:
        return None
    return str(fixture["id"])


def _is_player_market(name: object) -> bool:
    return isinstance(name, str) and any(word in name.lower() for word in PLAYER_MARKET_WORDS)


def _inspect_odds(rows: Iterable[Mapping[str, object]]) -> tuple[int, int, int]:
    bookmakers = 0
    bets = 0
    player_named_selections = 0
    for entry in rows:
        entry_books = entry.get("bookmakers")
        if not isinstance(entry_books, list):
            continue
        for bookmaker in entry_books:
            if not isinstance(bookmaker, Mapping):
                continue
            bookmakers += 1
            book_bets = bookmaker.get("bets")
            if not isinstance(book_bets, list):
                continue
            for bet in book_bets:
                if not isinstance(bet, Mapping):
                    continue
                bets += 1
                if not _is_player_market(bet.get("name")):
                    continue
                values = bet.get("values")
                if isinstance(values, list):
                    player_named_selections += sum(
                        1 for value in values if isinstance(value, Mapping) and value.get("value")
                    )
    return bookmakers, bets, player_named_selections


def probe_historical_seasons(
    client: httpx.Client,
    api_key: str,
    *,
    seasons: Iterable[int] = (2022, 2023, 2024),
    fetched_at: datetime,
) -> tuple[HistoricalProbe, ...]:
    """Probe whether completed seasons return usable player odds.

    The key is used only as a request header and is never included in the
    result. The timestamp is the probe time, not an assertion about when the
    provider originally published a quote.
    """
    require_utc(fetched_at, "fetched_at")
    headers = {"x-apisports-key": api_key}
    results: list[HistoricalProbe] = []
    for season in seasons:
        fixtures = client.get(
            f"{BASE_URL}/fixtures",
            params={"league": LEAGUE, "season": str(season), "last": "1"},
            headers=headers,
        )
        refusal = _error(fixtures)
        if refusal is not None:
            results.append(
                HistoricalProbe(
                    season,
                    "refused",
                    None,
                    0,
                    0,
                    0,
                    len(fixtures.content),
                    fetched_at,
                    _quota_remaining(fixtures),
                    refusal,
                )
            )
            continue
        fixture_rows = _response_rows(fixtures)
        fixture_id = _fixture_id(fixture_rows[0]) if fixture_rows else None
        if fixture_id is None:
            results.append(
                HistoricalProbe(
                    season,
                    "no-fixture",
                    None,
                    0,
                    0,
                    0,
                    len(fixtures.content),
                    fetched_at,
                    _quota_remaining(fixtures),
                    None,
                )
            )
            continue
        odds = client.get(
            f"{BASE_URL}/odds",
            params={"fixture": fixture_id},
            headers=headers,
        )
        refusal = _error(odds)
        if refusal is not None:
            results.append(
                HistoricalProbe(
                    season,
                    "refused",
                    fixture_id,
                    0,
                    0,
                    0,
                    len(odds.content),
                    fetched_at,
                    _quota_remaining(odds),
                    refusal,
                )
            )
            continue
        bookmakers, bets, player_selections = _inspect_odds(_response_rows(odds))
        results.append(
            HistoricalProbe(
                season,
                "accessible" if player_selections else "no-player-selections",
                fixture_id,
                bookmakers,
                bets,
                player_selections,
                len(odds.content),
                fetched_at,
                _quota_remaining(odds),
                None,
            )
        )
    return tuple(results)
