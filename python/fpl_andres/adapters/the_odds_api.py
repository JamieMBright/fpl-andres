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

import math
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from fpl_andres.adapters.football_data import FixtureOdds
from fpl_andres.models.goal_expectation import total_goals_mean
from fpl_andres.models.odds import OddsUnavailable, devig_shin
from fpl_andres.models.player_odds import PlayerMatchOdds

__all__ = [
    "MARKET_FIELDS",
    "PLAYER_MARKETS",
    "Quota",
    "by_kickoff",
    "classify_event",
    "describe_event",
    "fetch_event_odds",
    "list_events",
    "read_event",
    "read_fixture_odds",
]

BASE = "https://api.the-odds-api.com/v4/sports/soccer_epl"

#: Every live player market that constrains a scoring route or availability.
#: First/last scorer overlap anytime scorer and are retained as corroboration,
#: not added as extra goals. An unpaired SOT line is likewise retained without
#: inventing a historical BPS baseline. The host bills per returned market per
#: region, so a market no book has opened is free.
PLAYER_MARKETS: tuple[str, ...] = (
    "player_goal_scorer_anytime",
    "player_first_goal_scorer",
    "player_last_goal_scorer",
    "player_assists",
    "player_to_receive_card",
    "player_to_receive_red_card",
    "player_shots",
    "player_shots_on_target",
)

#: Which field on `PlayerMatchOdds` each market fills.
MARKET_FIELDS: Mapping[str, str] = {
    "player_goal_scorer_anytime": "anytime_goal",
    "player_first_goal_scorer": "first_goal",
    "player_last_goal_scorer": "last_goal",
    "player_assists": "anytime_assist",
    "player_to_receive_card": "any_card",
    "player_to_receive_red_card": "red_card",
    "player_shots": "shots",
    "player_shots_on_target": "shots_on_target",
}

_COUNT_MARKETS = frozenset(("player_shots", "player_shots_on_target"))
_NON_PLAYER_OUTCOMES = frozenset(
    {
        "no",
        "no goal scorer",
        "no goalscorer",
        "no scorer",
        "over",
        "own goal",
        "under",
        "yes",
    }
)


@dataclass(frozen=True)
class Quota:
    """What the host says a request cost, and what is left.

    The budget written into this repository -- one request per fixture, 500 a
    month, so about 390 spent on the schedule -- was an assumption nobody could
    check, because the host cannot be reached from the owner's network at all.
    It is also the kind of assumption that fails quietly: an exhausted key
    returns an error, not an empty market, and a run that reads the two apart
    is a run that can say which happened. Every response carries the counters,
    so the answer is free to take and there is no reason to keep guessing.
    """

    cost: int | None
    used: int | None
    remaining: int | None

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> Quota:
        return cls(
            cost=_counter(headers.get("x-requests-last")),
            used=_counter(headers.get("x-requests-used")),
            remaining=_counter(headers.get("x-requests-remaining")),
        )

    def __str__(self) -> str:
        if self.used is None and self.remaining is None:
            return "quota not reported"
        cost = "?" if self.cost is None else str(self.cost)
        used = "?" if self.used is None else str(self.used)
        remaining = "?" if self.remaining is None else str(self.remaining)
        return f"cost {cost}, used {used}, {remaining} left"


EventMarketStatus = Literal[
    "no-bookmaker",
    "no-markets",
    "requested-markets-absent",
    "requested-markets-empty",
    "returned",
]


@dataclass(frozen=True)
class EventMarketSummary:
    status: EventMarketStatus
    books: int
    outcomes: int
    requested_markets: tuple[str, ...]
    offered_markets: tuple[str, ...]
    missing_markets: tuple[str, ...]


def _counter(value: str | None) -> int | None:
    try:
        return int(float(value)) if value is not None else None
    except ValueError:
        return None


def list_events(client: httpx.Client, api_key: str) -> tuple[list[Mapping[str, Any]], Quota]:
    """Every Premier League match the book is currently pricing.

    Listing is free, which makes it the cheap way to read the quota counters
    without spending anything to learn them.
    """
    response = client.get(f"{BASE}/events", params={"apiKey": api_key})
    response.raise_for_status()
    payload = response.json()
    events = [event for event in payload if isinstance(event, Mapping)]
    return events, Quota.from_headers(response.headers)


def fetch_event_odds(
    client: httpx.Client,
    api_key: str,
    event_id: str,
    markets: Sequence[str] = PLAYER_MARKETS,
) -> tuple[Mapping[str, Any], Quota]:
    """One event's player markets, across every book in the United Kingdom.

    One region rather than two. The host bills per market per region, so adding
    Europe doubles the price of a run against a free tier of five hundred a
    month. What it buys is a slightly steadier median across more books, and
    the books that price a Premier League player deepest are the UK ones.
    """
    response = client.get(
        f"{BASE}/events/{event_id}/odds",
        params={
            "apiKey": api_key,
            "regions": "uk",
            "oddsFormat": "decimal",
            "markets": ",".join(markets),
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise ValueError("event odds payload was not an object")
    return payload, Quota.from_headers(response.headers)


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


def _poisson_mean_from_over(point: float, probability: float) -> float:
    """Expected count whose Poisson tail matches an over-line probability."""
    if point < 0.0:
        raise ValueError("count-market point cannot be negative")
    if not 0.0 <= probability < 1.0:
        raise ValueError("over probability must be in [0, 1)")
    if probability == 0.0:
        return 0.0
    threshold = math.floor(point) + 1

    def over(mean: float) -> float:
        term = math.exp(-mean)
        cumulative = term
        for count in range(1, threshold):
            term *= mean / count
            cumulative += term
        return 1.0 - cumulative

    low = 0.0
    high = max(1.0, point + 1.0)
    while over(high) < probability:
        high *= 2.0
        if high > 100.0:
            raise ValueError("count-market probability implies an implausible mean")
    for _ in range(80):
        middle = (low + high) / 2.0
        if over(middle) < probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def by_kickoff(events: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Soonest first, so a limited budget is spent where markets are open.

    Books price the result months out and open player props days out, so the
    order the host happens to list fixtures in decides whether a capped run
    finds anything at all. Sorting is the difference between spending the
    month's credits on ten fixtures nobody has quoted yet and spending them on
    the ones being played this week. Anything without a readable kickoff sorts
    last rather than being dropped: an unparseable date is a reason to look, not
    a reason to skip.
    """
    far = datetime.max.replace(tzinfo=UTC)
    return sorted(events, key=lambda event: _kickoff(event.get("commence_time")) or far)


def classify_event(payload: Mapping[str, Any]) -> EventMarketSummary:
    """Structured account of what a provider returned for one fixture."""
    books = [book for book in payload.get("bookmakers", []) if isinstance(book, Mapping)]
    offered: set[str] = set()
    outcomes = 0
    requested_outcomes = 0
    requested = frozenset(PLAYER_MARKETS)
    for book in books:
        for market in book.get("markets", []):
            if not isinstance(market, Mapping):
                continue
            key = market.get("key")
            rows = [item for item in market.get("outcomes", []) if isinstance(item, Mapping)]
            if isinstance(key, str):
                offered.add(key)
                if key in requested:
                    requested_outcomes += len(rows)
            outcomes += len(rows)
    requested_offered = offered & requested
    if not books:
        status: EventMarketStatus = "no-bookmaker"
    elif not offered:
        status = "no-markets"
    elif not requested_offered:
        status = "requested-markets-absent"
    elif requested_outcomes == 0:
        status = "requested-markets-empty"
    else:
        status = "returned"
    return EventMarketSummary(
        status=status,
        books=len(books),
        outcomes=outcomes,
        requested_markets=tuple(PLAYER_MARKETS),
        offered_markets=tuple(sorted(offered)),
        missing_markets=tuple(sorted(requested - offered)),
    )


def describe_event(payload: Mapping[str, Any]) -> str:
    """What the book actually returned for this fixture.

    "0 players quoted" has three completely different causes -- no bookmaker
    answered, the bookmakers answered with markets nobody asked for, or the
    markets arrived empty -- and the ingest could not tell them apart. Guessing
    between them from here is impossible: every price host fails at the TLS
    handshake on the owner's network, so the only place the question can be
    answered is the run itself. This puts the answer in the log.
    """
    summary = classify_event(payload)
    if summary.status == "no-bookmaker":
        return "no bookmaker priced it"
    if summary.status == "no-markets":
        return f"{summary.books} books, no markets"
    detail = (
        f"{summary.books} books, {summary.outcomes} outcomes, "
        f"markets {list(summary.offered_markets)}"
    )
    return (
        detail
        if not summary.missing_markets
        else f"{detail}, absent {list(summary.missing_markets)}"
    )


def _match_prices(outcomes: object, home: str, away: str) -> dict[str, float]:
    if not isinstance(outcomes, list):
        return {}
    wanted = {home: "home", "Draw": "draw", away: "away"}
    values: dict[str, float] = {}
    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            continue
        name = outcome.get("name")
        price = outcome.get("price")
        field = wanted.get(name) if isinstance(name, str) else None
        if field and isinstance(price, (int, float)) and price > 1.0:
            values[field] = float(price)
    return values


def _total_prices(outcomes: object) -> dict[float, dict[str, float]]:
    if not isinstance(outcomes, list):
        return {}
    values: dict[float, dict[str, float]] = defaultdict(dict)
    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            continue
        name = outcome.get("name")
        point = outcome.get("point")
        price = outcome.get("price")
        side = str(name).lower() if name in ("Over", "Under") else None
        if (
            side
            and isinstance(point, (int, float))
            and isinstance(price, (int, float))
            and price > 1.0
        ):
            values[float(point)][side] = float(price)
    return dict(values)


def _normalise_three(
    values: tuple[float, float, float],
) -> tuple[float, float, float]:
    total = sum(values)
    return values[0] / total, values[1] / total, values[2] / total


def _book_team_markets(
    book: Mapping[str, Any], home: str, away: str
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, dict[float, dict[str, float]]],
    set[str],
]:
    back: dict[str, float] = {}
    lay: dict[str, float] = {}
    totals: dict[str, dict[float, dict[str, float]]] = {}
    observed: set[str] = set()
    for market in book.get("markets", []):
        if not isinstance(market, Mapping):
            continue
        key = market.get("key")
        if key not in {"h2h", "h2h_lay", "totals", "alternate_totals"}:
            continue
        assert isinstance(key, str)
        observed.add(key)
        if key == "h2h":
            back.update(_match_prices(market.get("outcomes"), home, away))
        elif key == "h2h_lay":
            lay.update(_match_prices(market.get("outcomes"), home, away))
        else:
            totals[key] = _total_prices(market.get("outcomes"))
    return back, lay, totals, observed


def _paired_lay_view(
    back: Mapping[str, float], lay: Mapping[str, float]
) -> tuple[float, float, float] | None:
    fields = ("home", "draw", "away")
    if not all(field in back and field in lay for field in fields):
        return None
    if any(back[field] > lay[field] for field in fields):
        return None
    return _normalise_three(
        (
            (1.0 / back["home"] + 1.0 / lay["home"]) / 2.0,
            (1.0 / back["draw"] + 1.0 / lay["draw"]) / 2.0,
            (1.0 / back["away"] + 1.0 / lay["away"]) / 2.0,
        )
    )


def _collect_total_means(
    totals: Mapping[str, Mapping[float, Mapping[str, float]]],
    prices: dict[str, list[float]],
    total_means_by_line: dict[float, list[float]],
) -> set[str]:
    valid_keys: set[str] = set()
    for market_key, lines in totals.items():
        for line, sides in lines.items():
            if line == 2.5 and market_key == "totals":
                for side in ("over", "under"):
                    if side in sides:
                        prices[side].append(sides[side])
            if line <= 0.0 or line != int(line) + 0.5:
                continue
            over = sides.get("over")
            under = sides.get("under")
            if over is None or under is None:
                continue
            try:
                over_probability, _ = devig_shin((over, under))
                total_means_by_line[line].append(total_goals_mean(over_probability, line))
            except OddsUnavailable:
                continue
            valid_keys.add(market_key)
    return valid_keys


def _match_probability_consensus(
    medians: Mapping[str, float],
    paired_lay_views: Sequence[tuple[float, float, float]],
) -> tuple[float, float, float] | None:
    if not paired_lay_views:
        return None
    try:
        back_probabilities = devig_shin((medians["home"], medians["draw"], medians["away"]))
    except OddsUnavailable:
        return None
    lay_consensus = _normalise_three(
        (
            statistics.median(view[0] for view in paired_lay_views),
            statistics.median(view[1] for view in paired_lay_views),
            statistics.median(view[2] for view in paired_lay_views),
        )
    )
    return _normalise_three(
        (
            (back_probabilities[0] + lay_consensus[0]) / 2.0,
            (back_probabilities[1] + lay_consensus[1]) / 2.0,
            (back_probabilities[2] + lay_consensus[2]) / 2.0,
        )
    )


def _alternate_total_consensus(
    valid_total_keys: set[str], total_means_by_line: Mapping[float, Sequence[float]]
) -> float | None:
    if "alternate_totals" not in valid_total_keys:
        return None
    line_consensus = [statistics.median(means) for means in total_means_by_line.values() if means]
    return statistics.median(line_consensus) if line_consensus else None


def read_fixture_odds(payload: Mapping[str, Any]) -> FixtureOdds | None:
    """A complete team-market consensus for one fixture."""
    home = payload.get("home_team")
    away = payload.get("away_team")
    if not isinstance(home, str) or not isinstance(away, str):
        raise ValueError("event payload named no teams")

    prices: dict[str, list[float]] = defaultdict(list)
    observed: set[str] = set()
    paired_lay_views: list[tuple[float, float, float]] = []
    total_means_by_line: dict[float, list[float]] = defaultdict(list)
    valid_total_keys: set[str] = set()
    for book in payload.get("bookmakers", []):
        if not isinstance(book, Mapping):
            continue
        back, lay, totals, book_observed = _book_team_markets(book, home, away)
        observed.update(book_observed)
        for field, price in back.items():
            prices[field].append(price)
        lay_view = _paired_lay_view(back, lay)
        if lay_view is not None:
            paired_lay_views.append(lay_view)
        valid_total_keys.update(_collect_total_means(totals, prices, total_means_by_line))

    required = ("home", "draw", "away", "over", "under")
    if any(not prices[field] for field in required):
        return None
    medians = {field: statistics.median(prices[field]) for field in required}
    match_probabilities = _match_probability_consensus(medians, paired_lay_views)
    used = {"h2h", "totals"}
    if match_probabilities is not None:
        used.add("h2h_lay")
    alternate_total_mean = _alternate_total_consensus(valid_total_keys, total_means_by_line)
    if alternate_total_mean is not None:
        used.add("alternate_totals")
    return FixtureOdds(
        division="E0",
        kickoff=_kickoff(payload.get("commence_time")),
        home_team=home,
        away_team=away,
        home_odds=medians["home"],
        draw_odds=medians["draw"],
        away_odds=medians["away"],
        over_odds=medians["over"],
        under_odds=medians["under"],
        price_source=(
            "the-odds-api-market-consensus" if used - {"h2h", "totals"} else "the-odds-api-median"
        ),
        markets={f"the-odds-api:{field}": medians[field] for field in required},
        match_probabilities=match_probabilities,
        total_goals_mean=alternate_total_mean,
        observed_market_keys=tuple(sorted(observed)),
        used_market_keys=tuple(sorted(used)),
    )


def _count_market_values(outcomes: object) -> dict[str, float]:
    if not isinstance(outcomes, list):
        return {}
    by_player_line: dict[str, dict[float, dict[str, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            continue
        player = outcome.get("description")
        side = outcome.get("name")
        price = outcome.get("price")
        point = outcome.get("point")
        if not isinstance(player, str) or not isinstance(side, str):
            continue
        if not isinstance(price, (int, float)) or float(price) <= 1.0:
            continue
        if not isinstance(point, (int, float)) or side.lower() not in {"over", "under"}:
            continue
        by_player_line[player][float(point)][side.lower()] = float(price)

    values: dict[str, float] = {}
    for player, lines in by_player_line.items():
        estimates = [
            _poisson_mean_from_over(point, probability)
            for point, sides in lines.items()
            if (probability := _over_probability(sides)) is not None
        ]
        if estimates:
            values[player] = statistics.median(estimates)
    return values


def _over_probability(sides: Mapping[str, float]) -> float | None:
    over_price = sides.get("over")
    if over_price is None:
        return None
    prices = [over_price]
    under_price = sides.get("under")
    if under_price is not None:
        prices.append(under_price)
    return _devigged(prices)


def _anytime_market_values(outcomes: object) -> dict[str, float]:
    if not isinstance(outcomes, list):
        return {}
    by_player: dict[str, list[float]] = defaultdict(list)
    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            continue
        name = outcome.get("description") or outcome.get("name")
        price = outcome.get("price")
        if not isinstance(name, str) or name.strip().casefold() in _NON_PLAYER_OUTCOMES:
            continue
        if isinstance(price, (int, float)) and price > 1:
            by_player[name].append(float(price))
    return {
        name: probability
        for name, prices in by_player.items()
        if (probability := _devigged(prices)) is not None
    }


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
            market_values = (
                _count_market_values(market.get("outcomes"))
                if key in _COUNT_MARKETS
                else _anytime_market_values(market.get("outcomes"))
            )
            for name, value in market_values.items():
                quotes[name][key].append(value)
                if isinstance(book_key, str):
                    books[name].add(book_key)

    rows: list[PlayerMatchOdds] = []
    for name, by_market in sorted(quotes.items()):
        fields: dict[str, float] = {}
        for key, quote_values in by_market.items():
            field = MARKET_FIELDS.get(key)
            if field is None or not quote_values:
                continue
            fields[field] = round(statistics.median(quote_values), 6)
        rows.append(
            PlayerMatchOdds(
                element_id=None,
                quoted_name=name,
                home_team=home,
                away_team=away,
                kickoff=kickoff,
                books=len(books[name]),
                anytime_goal=fields.get("anytime_goal"),
                first_goal=fields.get("first_goal"),
                last_goal=fields.get("last_goal"),
                anytime_assist=fields.get("anytime_assist"),
                any_card=fields.get("any_card"),
                red_card=fields.get("red_card"),
                shots=fields.get("shots"),
                shots_on_target=fields.get("shots_on_target"),
            )
        )
    return rows
