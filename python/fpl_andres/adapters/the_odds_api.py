"""Read The Odds API's player markets into probabilities.

The survey established that this source names its player markets explicitly and
answers on a free key. This turns one of its event payloads into
`PlayerMatchOdds`: de-vigged, averaged across books, and keyed by the name the
book quoted so an unmatched player can be chased rather than silently dropped.

Parsing is separate from fetching on purpose. Every price host fails at the TLS
handshake from the owner's network behind a gambling-category filter, so the
fetch runs on a GitHub runner and only the parser can be tested anywhere.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from fpl_andres.models.odds import OddsUnavailable, devig_shin
from fpl_andres.models.player_odds import PlayerMatchOdds

__all__ = [
    "MARKET_FIELDS",
    "PLAYER_MARKETS",
    "fetch_event_odds",
    "list_events",
    "read_event",
]

BASE = "https://api.the-odds-api.com/v4/sports/soccer_epl"

#: Only markets that map onto an FPL scoring event. Asking for more spends the
#: free tier's request budget on prices nothing here can use.
PLAYER_MARKETS: tuple[str, ...] = (
    "player_goal_scorer_anytime",
    "player_assists",
    "player_to_receive_card",
    "player_shots_on_target",
)

#: Which field on `PlayerMatchOdds` each market fills.
MARKET_FIELDS: Mapping[str, str] = {
    "player_goal_scorer_anytime": "anytime_goal",
    "player_assists": "anytime_assist",
    "player_to_receive_card": "card",
    "player_shots_on_target": "shot_on_target",
}


def list_events(client: httpx.Client, api_key: str) -> list[Mapping[str, Any]]:
    """Every Premier League match the book is currently pricing."""
    response = client.get(f"{BASE}/events", params={"apiKey": api_key})
    response.raise_for_status()
    payload = response.json()
    return [event for event in payload if isinstance(event, Mapping)]


def fetch_event_odds(
    client: httpx.Client,
    api_key: str,
    event_id: str,
    markets: Sequence[str] = PLAYER_MARKETS,
) -> Mapping[str, Any]:
    """One event's player markets, across every book in the UK and EU."""
    response = client.get(
        f"{BASE}/events/{event_id}/odds",
        params={
            "apiKey": api_key,
            "regions": "uk,eu",
            "oddsFormat": "decimal",
            "markets": ",".join(markets),
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise ValueError("event odds payload was not an object")
    return payload


def _kickoff(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _two_way(price: float) -> float:
    """
    One yes/no quote, de-vigged against its own implied no.

    A book prices "anytime scorer" one player at a time and rarely publishes
    the "no". Shin's method needs a complete book, so the missing side is
    reconstructed from the same overround the rest of that book carries -- and
    with only one side quoted the honest reconstruction is the fair no, which
    makes the de-vig a no-op. Rather than pretend otherwise, the implied
    probability is returned and the margin is left in, which biases every
    scoring chance upward by the book's margin on that market.
    """
    if price <= 1:
        raise ValueError(f"decimal odds must exceed 1, got {price}")
    return 1.0 / price


def _devigged(prices: Sequence[float]) -> float | None:
    """A complete two-way book de-vigged, or a lone quote read as implied."""
    if not prices:
        return None
    if len(prices) == 2:
        try:
            return devig_shin(prices)[0]
        except OddsUnavailable:
            # A book quoting no margin, or an arbitrage across a stale line.
            # Neither is worth losing the rest of the fixture over.
            return _two_way(prices[0])
    return _two_way(prices[0])


def read_event(
    payload: Mapping[str, Any],
    *,
    markets: Iterable[str] = PLAYER_MARKETS,
) -> list[PlayerMatchOdds]:
    """
    One event payload as one row per quoted player.

    Books disagree, so each market is the median across the books that priced
    it. A median rather than a mean: one book with a stale line should not drag
    the number, and three books is a small enough sample for one outlier to.
    """
    home = payload.get("home_team")
    away = payload.get("away_team")
    kickoff = _kickoff(payload.get("commence_time"))
    if not isinstance(home, str) or not isinstance(away, str):
        raise ValueError("event payload named no teams")

    wanted = set(markets)
    # name -> market -> [probability from each book]
    quotes: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    books: dict[str, set[str]] = defaultdict(set)

    for book in payload.get("bookmakers", []):
        if not isinstance(book, Mapping):
            continue
        book_key = book.get("key")
        for market in book.get("markets", []):
            if not isinstance(market, Mapping):
                continue
            key = market.get("key")
            if key not in wanted or not isinstance(key, str):
                continue
            # Outcomes for one player arrive as Yes/No pairs where the book
            # publishes both, and as a lone Yes where it does not.
            by_player: dict[str, list[float]] = defaultdict(list)
            for outcome in market.get("outcomes", []):
                if not isinstance(outcome, Mapping):
                    continue
                name = outcome.get("description") or outcome.get("name")
                price = outcome.get("price")
                if not isinstance(name, str) or not isinstance(price, (int, float)):
                    continue
                if price <= 1:
                    continue
                by_player[name].append(float(price))
            for name, prices in by_player.items():
                probability = _devigged(prices)
                if probability is None:
                    continue
                quotes[name][key].append(probability)
                if isinstance(book_key, str):
                    books[name].add(book_key)

    rows: list[PlayerMatchOdds] = []
    for name, by_market in sorted(quotes.items()):
        fields: dict[str, float] = {}
        for key, values in by_market.items():
            field = MARKET_FIELDS.get(key)
            if field is None or not values:
                continue
            fields[field] = round(statistics.median(values), 6)
        rows.append(
            PlayerMatchOdds(
                element_id=None,
                quoted_name=name,
                home_team=home,
                away_team=away,
                kickoff=kickoff,
                books=len(books[name]),
                anytime_goal=fields.get("anytime_goal"),
                anytime_assist=fields.get("anytime_assist"),
                card=fields.get("card"),
                shot_on_target=fields.get("shot_on_target"),
            )
        )
    return rows
