"""Candidate sources for player-level markets, and a probe for each.

football-data.co.uk prices matches. FPL scores players, and most of what it
scores -- a goal, an assist, a save, a tackle, a card -- is priced somewhere as
a player prop. This module does not model any of that. It answers the question
that has to come first: which providers exist, which can this project actually
reach, and what exactly does each one return?

Every probe is read-only, hits a documented endpoint, and asks for the smallest
response that still reveals the field names. Credentials are read from the
environment and never logged; a source with no credential configured reports
that plainly rather than failing the run, because "not signed up yet" and
"signed up and broken" are different answers and only one of them is a bug.

Reachability is a property of the desk, not the feed: every price host fails at
the TLS handshake behind the owner's gambling-category filter while answering
normally from a GitHub runner. The survey is therefore written to run in CI.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

__all__ = [
    "PROP_SOURCES",
    "ProbeResult",
    "PropSource",
    "field_paths",
    "probe_source",
    "source_by_key",
    "survey",
]


#: The FPL scoring events a player market could inform. Kept as an explicit
#: list so a source's coverage is reported against the same yardstick every
#: time, rather than against whatever that source happens to sell.
SCORING_EVENTS: tuple[str, ...] = (
    "goal",
    "assist",
    "clean_sheet",
    "save",
    "penalty_save",
    "goals_conceded",
    "yellow_card",
    "red_card",
    "own_goal",
    "penalty_miss",
    "defensive_contribution",
    "bonus",
)


@dataclass(frozen=True)
class ProbeResult:
    """What one source returned when asked the smallest revealing question."""

    key: str
    #: "ok", "no_credential", "unreachable", "refused", "unreadable".
    status: str
    #: Human-readable detail. Never contains a credential.
    note: str
    #: Every field path the response carried, sorted. This is the catalogue.
    fields: tuple[str, ...] = ()
    #: Market identifiers the source named, where it names them.
    markets: tuple[str, ...] = ()
    #: HTTP status, when a request was actually made.
    http_status: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class PropSource:
    """A candidate provider, and how to ask it what it has."""

    key: str
    name: str
    homepage: str
    #: Environment variables that must be set before this can be probed. Empty
    #: means the source is open.
    credential_env: tuple[str, ...]
    #: What the source is expected to price, in this project's vocabulary.
    covers: tuple[str, ...]
    #: Licence or terms note. Read before depending on any of these.
    terms: str
    probe: Callable[[httpx.Client, Mapping[str, str]], ProbeResult] = field(
        repr=False,
    )
    #: False for a rate source or the scoring target. Both are useful and
    #: neither is somebody with money on the outcome, which is the whole reason
    #: a market is worth having.
    market: bool = True


def field_paths(payload: Any, prefix: str = "") -> set[str]:
    """Every dotted path in a decoded JSON document.

    Lists collapse to `[]` so a hundred fixtures describe one shape rather than
    a hundred near-identical ones. The point is the schema, not the volume.
    """
    if isinstance(payload, Mapping):
        paths: set[str] = set()
        for key, value in payload.items():
            here = f"{prefix}.{key}" if prefix else str(key)
            paths.add(here)
            paths |= field_paths(value, here)
        return paths
    if isinstance(payload, Sequence) and not isinstance(payload, str | bytes):
        paths = set()
        for item in payload:
            paths |= field_paths(item, f"{prefix}[]")
        return paths
    return set()


def _missing(source: PropSource, env: Mapping[str, str]) -> ProbeResult | None:
    absent = [name for name in source.credential_env if not env.get(name)]
    if not absent:
        return None
    return ProbeResult(
        key=source.key,
        status="no_credential",
        note=f"set {', '.join(absent)} to probe this source",
    )


def _get(
    client: httpx.Client,
    url: str,
    *,
    params: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    return client.get(url, params=dict(params or {}), headers=dict(headers or {}))


#: What each host calls the counters it returns on every response. Free tiers
#: are small enough that a survey and an ingest sharing one key can exhaust the
#: allowance between them, and none of these hosts warns before they do -- the
#: request that crosses the line simply fails. Reading the counters back is the
#: only way to know where a run stands, so every probe reports them.
_QUOTA_HEADERS: Mapping[str, tuple[str, str]] = {
    # The Odds API bills per market per region, so a request costs far more
    # than one and `x-requests-last` is the only place the true price appears.
    "x-requests-remaining": ("x-requests-remaining", "x-requests-last"),
    # API-Football counts whole requests against a daily allowance.
    "x-ratelimit-requests-remaining": ("x-ratelimit-requests-remaining", ""),
}


def _quota(response: httpx.Response) -> str:
    """What this request cost the day's or month's allowance, as the host said."""
    for remaining_key, (_, cost_key) in _QUOTA_HEADERS.items():
        remaining = response.headers.get(remaining_key)
        if remaining is None:
            continue
        cost = response.headers.get(cost_key) if cost_key else None
        return f"cost {cost}, {remaining} left" if cost else f"{remaining} left"
    return "quota not reported"


def _from_json(
    source: PropSource,
    response: httpx.Response,
    *,
    markets: Iterable[str] = (),
) -> ProbeResult:
    if response.status_code >= 400:
        return ProbeResult(
            key=source.key,
            status="refused",
            note=f"HTTP {response.status_code}",
            http_status=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError:
        return ProbeResult(
            key=source.key,
            status="unreadable",
            note="response was not JSON",
            http_status=response.status_code,
        )
    return ProbeResult(
        key=source.key,
        status="ok",
        note=f"{len(response.content)} bytes",
        fields=tuple(sorted(field_paths(payload))),
        markets=tuple(sorted(set(markets))),
        http_status=response.status_code,
    )


# --------------------------------------------------------------------------
# Probes. One per source, each the smallest request that reveals field names.
# --------------------------------------------------------------------------


#: The Odds API names player markets explicitly, so ask for the ones that map
#: onto an FPL scoring event and let the response say which it honours.
_THE_ODDS_API_MARKETS = (
    "player_goal_scorer_anytime",
    "player_first_goal_scorer",
    "player_last_goal_scorer",
    "player_to_receive_card",
    "player_to_receive_red_card",
    "player_shots_on_target",
    "player_shots",
    "player_assists",
    "alternate_totals",
    "totals",
    "h2h",
)

#: The live provider returns and bills this beside a requested `h2h` market.
_THE_ODDS_API_IMPLICIT_MARKETS = ("h2h_lay",)


def _probe_the_odds_api(
    client: httpx.Client,
    env: Mapping[str, str],
) -> ProbeResult:
    key = env["THE_ODDS_API_KEY"]
    events = _get(
        client,
        "https://api.the-odds-api.com/v4/sports/soccer_epl/events",
        params={"apiKey": key},
    )
    if events.status_code >= 400:
        return ProbeResult(
            key="the-odds-api",
            status="refused",
            note=f"HTTP {events.status_code} listing events",
            http_status=events.status_code,
        )
    listing = events.json()
    if not isinstance(listing, list) or not listing:
        return ProbeResult(
            key="the-odds-api",
            status="ok",
            note="no Premier League events priced right now",
            fields=tuple(sorted(field_paths(listing))),
            http_status=events.status_code,
        )
    # The soonest fixture, not whichever the host listed first. Books price the
    # result months out and open player props days out, so probing an arbitrary
    # fixture answers "are props open in December" and reports an empty
    # catalogue for a source that has one.
    soonest = min(
        (row for row in listing if isinstance(row, Mapping)),
        key=lambda row: str(row.get("commence_time") or "9999"),
        default=None,
    )
    event_id = soonest.get("id") if soonest is not None else None
    if soonest is None or not isinstance(event_id, str):
        return ProbeResult(
            key="the-odds-api",
            status="unreadable",
            note="event listing carried no id",
            fields=tuple(sorted(field_paths(listing))),
            http_status=events.status_code,
        )
    odds = _get(
        client,
        f"https://api.the-odds-api.com/v4/sports/soccer_epl/events/{event_id}/odds",
        params={
            "apiKey": key,
            # One region, not two. The host bills per market per region, so the
            # eleven markets below cost eleven units in the UK and twenty-two
            # across the UK and Europe -- against a free tier of five hundred a
            # month that this survey shares with the weekly ingest. UK books are
            # the ones that price a Premier League player deepest anyway.
            "regions": "uk",
            "oddsFormat": "decimal",
            "markets": ",".join(_THE_ODDS_API_MARKETS),
        },
    )
    result = _from_json(_SOURCE_INDEX["the-odds-api"], odds)
    if not result.ok:
        return result
    payload = odds.json()
    named: set[str] = set()
    houses: set[str] = set()
    outcomes = 0
    for book in payload.get("bookmakers", []) if isinstance(payload, Mapping) else []:
        if not isinstance(book, Mapping):
            continue
        if isinstance(book.get("key"), str):
            houses.add(book["key"])
        for market in book.get("markets", []):
            if not isinstance(market, Mapping):
                continue
            if isinstance(market.get("key"), str):
                named.add(market["key"])
            outcomes += sum(1 for item in market.get("outcomes", []) if isinstance(item, Mapping))
    # Everything a reader needs to tell a shut market from a wrong request:
    # which fixture was asked about, who answered, how much they said, what
    # was asked for that did not come back, and what the question cost.
    absent = sorted(set(_THE_ODDS_API_MARKETS) - named)
    note = (
        f"{soonest.get('home_team')} v {soonest.get('away_team')} on "
        f"{soonest.get('commence_time')}; {len(houses)} books, {outcomes} outcomes; "
        f"asked for {len(_THE_ODDS_API_MARKETS)} markets, {len(absent)} absent"
    )
    if absent:
        note += f" ({', '.join(absent)})"
    note += f"; {_quota(odds)}"
    return ProbeResult(
        key=result.key,
        status=result.status,
        note=note,
        fields=result.fields,
        markets=tuple(sorted(named)),
        http_status=result.http_status,
    )


#: What a player-level bet is called, in whichever words a provider chose.
#: Matched case-insensitively against the bet name, because every aggregator
#: names the same market differently and this file should not pretend to know
#: which spelling it will meet.
_PLAYER_BET_WORDS: tuple[str, ...] = (
    "scorer",
    "assist",
    "save",
    "penalty",
    "booked",
    "card",
    "sent off",
    "shots",
    "tackle",
)

#: The Premier League, and how far ahead to look for a fixture to price.
_API_FOOTBALL_LEAGUE = "39"


def _api_football_season(at: datetime | None = None) -> str:
    """API-Football keys an English campaign by its starting calendar year."""
    current = at if at is not None else datetime.now(UTC)
    return str(current.year if current.month >= 7 else current.year - 1)


def _is_player_bet(name: str) -> bool:
    lowered = name.lower()
    return any(word in lowered for word in _PLAYER_BET_WORDS)


def _api_football_refusal(response: httpx.Response) -> str | None:
    """What this host refused, when it refused with a 200.

    An unsubscribed endpoint, a spent daily allowance and a rejected key all
    come back as success with the reason in `errors`. Read only `response` and
    every one of them reads as a league with no fixtures on.
    """
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, Mapping):
        return None
    errors = payload.get("errors")
    # The field is `[]` on success and an object keyed by cause on failure.
    if not isinstance(errors, Mapping) or not errors:
        return None
    return "; ".join(f"{key}: {value}" for key, value in sorted(errors.items()))


def _probe_api_football(
    client: httpx.Client,
    env: Mapping[str, str],
) -> ProbeResult:
    # The bet list is the catalogue itself: every market this provider knows,
    # by id and name, which is exactly what "what can I get" means here.
    key = env["API_FOOTBALL_API_KEY"]
    headers = {"x-apisports-key": key}
    response = _get(client, "https://v3.football.api-sports.io/odds/bets", headers=headers)
    result = _from_json(_SOURCE_INDEX["api-football"], response)
    if not result.ok:
        return result
    refused = _api_football_refusal(response)
    if refused is not None:
        return ProbeResult(
            key=result.key,
            status="refused",
            note=refused,
            http_status=response.status_code,
        )
    payload = response.json()
    named = {
        str(item.get("name"))
        for item in (payload.get("response", []) if isinstance(payload, Mapping) else [])
        if isinstance(item, Mapping) and item.get("name")
    }
    # A catalogue of bet types is not an offer. Knowing this provider has heard
    # of "Anytime Goal Scorer" says nothing about whether a Premier League
    # fixture carries one, or whether its selections name footballers rather
    # than sides -- and that is the whole question a player-market source has
    # to answer. Two more requests against a hundred a day settles it.
    offered = _api_football_fixture_bets(client, headers)
    return ProbeResult(
        key=result.key,
        status=result.status,
        note=f"{result.note}; {len(named)} bet types listed; {offered}; {_quota(response)}",
        fields=result.fields,
        markets=tuple(sorted(named)),
        http_status=result.http_status,
    )


def _api_football_fixture_bets(client: httpx.Client, headers: Mapping[str, str]) -> str:
    """What the next Premier League fixture is actually priced for, by whom.

    Reports the player-level bets by name with how many selections each
    carries and one of them verbatim, because "does the selection name a
    footballer" cannot be answered from a bet name and is the only thing that
    decides whether this source can be crosswalked onto FPL element ids.
    """
    season = _get(
        client,
        "https://v3.football.api-sports.io/fixtures",
        params={
            "league": _API_FOOTBALL_LEAGUE,
            "season": _api_football_season(),
            "next": "1",
        },
        headers=headers,
    )
    if season.status_code >= 400:
        return f"no fixture to price: HTTP {season.status_code}"
    refused = _api_football_refusal(season)
    if refused is not None:
        return f"fixtures refused: {refused}"
    listing = season.json()
    rows = listing.get("response", []) if isinstance(listing, Mapping) else []
    first = rows[0] if rows and isinstance(rows[0], Mapping) else None
    fixture = first.get("fixture") if isinstance(first, Mapping) else None
    fixture_id = fixture.get("id") if isinstance(fixture, Mapping) else None
    if fixture_id is None:
        return "no Premier League fixture scheduled"
    odds = _get(
        client,
        "https://v3.football.api-sports.io/odds",
        params={"fixture": str(fixture_id)},
        headers=headers,
    )
    if odds.status_code >= 400:
        return f"fixture {fixture_id} priced nowhere: HTTP {odds.status_code}"
    refused = _api_football_refusal(odds)
    if refused is not None:
        return f"fixture {fixture_id} odds refused: {refused}"
    priced = odds.json()
    entries = priced.get("response", []) if isinstance(priced, Mapping) else []
    books: set[str] = set()
    player_bets: dict[str, tuple[int, str]] = {}
    total = 0
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        for book in entry.get("bookmakers", []):
            if not isinstance(book, Mapping):
                continue
            if isinstance(book.get("name"), str):
                books.add(book["name"])
            for bet in book.get("bets", []):
                if not isinstance(bet, Mapping) or not isinstance(bet.get("name"), str):
                    continue
                total += 1
                values = [item for item in bet.get("values", []) if isinstance(item, Mapping)]
                if not _is_player_bet(bet["name"]) or not values:
                    continue
                sample = str(values[0].get("value"))
                player_bets[bet["name"]] = (len(values), sample)
    if not entries:
        return f"fixture {fixture_id} is scheduled but priced by nobody yet"
    detail = f"fixture {fixture_id}: {len(books)} books, {total} bets"
    if not player_bets:
        return f"{detail}, none of them player-level"
    listed = ", ".join(
        f"{name} ({count} selections, e.g. {sample})"
        for name, (count, sample) in sorted(player_bets.items())
    )
    return f"{detail}, {len(player_bets)} player-level: {listed}"


def _probe_betfair(
    client: httpx.Client,
    env: Mapping[str, str],
) -> ProbeResult:
    # The exchange is the only source here whose prices are a genuine
    # two-sided market rather than a book's offer, which makes its implied
    # probabilities the cleanest of the lot -- when it lists the market.
    response = client.post(
        "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/",
        headers={
            "X-Application": env["BETFAIR_APP_KEY"],
            "X-Authentication": env["BETFAIR_SESSION_TOKEN"],
            "Content-Type": "application/json",
        },
        json={
            "filter": {"eventTypeIds": ["1"], "competitionIds": ["10932509"]},
            "marketProjection": ["MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"],
            "maxResults": "50",
        },
    )
    result = _from_json(_SOURCE_INDEX["betfair-exchange"], response)
    if not result.ok:
        return result
    payload = response.json()
    named = {
        str(item.get("marketName"))
        for item in (payload if isinstance(payload, list) else [])
        if isinstance(item, Mapping) and item.get("marketName")
    }
    return ProbeResult(
        key=result.key,
        status=result.status,
        note=f"{result.note}; {len(named)} market names",
        fields=result.fields,
        markets=tuple(sorted(named)),
        http_status=result.http_status,
    )


def _probe_football_data(
    client: httpx.Client,
    _env: Mapping[str, str],
) -> ProbeResult:
    # Already ingested, and listed here so the comparison has a baseline. Its
    # columns are the thing player props would be measured against.
    response = _get(client, "https://www.football-data.co.uk/mmz4281/2526/E0.csv")
    if response.status_code >= 400:
        return ProbeResult(
            key="football-data",
            status="refused",
            note=f"HTTP {response.status_code}",
            http_status=response.status_code,
        )
    text = response.content.decode("utf-8-sig", errors="replace")
    header = text.splitlines()[0].split(",") if text else []
    return ProbeResult(
        key="football-data",
        status="ok",
        note=f"{len(header)} columns, match level only",
        fields=tuple(sorted(name for name in header if name)),
        http_status=response.status_code,
    )


def _probe_understat(
    client: httpx.Client,
    _env: Mapping[str, str],
) -> ProbeResult:
    # Not a market. It is the free player-level rate source this project
    # already crosswalks, and the honest control for anything a book quotes:
    # if a prop disagrees with a season of shot data, one of them is wrong.
    response = _get(client, "https://understat.com/league/EPL")
    if response.status_code >= 400:
        return ProbeResult(
            key="understat",
            status="refused",
            note=f"HTTP {response.status_code}",
            http_status=response.status_code,
        )
    body = response.text
    # The page ships its data as JSON assigned to a handful of named vars.
    names = tuple(
        sorted(
            {chunk.split("=")[0].strip() for chunk in body.split("var ")[1:] if "=" in chunk},
        ),
    )
    return ProbeResult(
        key="understat",
        status="ok",
        note=f"{len(body)} bytes; embedded datasets: {', '.join(names) or 'none found'}",
        fields=names,
        http_status=response.status_code,
    )


def _probe_fpl_elements(
    client: httpx.Client,
    _env: Mapping[str, str],
) -> ProbeResult:
    # The scoring authority. Its element fields are the target any prop has to
    # predict, so the catalogue is incomplete without them.
    response = _get(
        client,
        "https://fantasy.premierleague.com/api/bootstrap-static/",
    )
    if response.status_code >= 400:
        return ProbeResult(
            key="fpl-bootstrap",
            status="refused",
            note=f"HTTP {response.status_code}",
            http_status=response.status_code,
        )
    payload = response.json()
    elements = payload.get("elements", []) if isinstance(payload, Mapping) else []
    first = elements[0] if elements else {}
    return ProbeResult(
        key="fpl-bootstrap",
        status="ok",
        note=f"{len(elements)} elements",
        fields=tuple(sorted(field_paths(first))),
        http_status=response.status_code,
    )


PROP_SOURCES: tuple[PropSource, ...] = (
    PropSource(
        key="the-odds-api",
        name="The Odds API",
        homepage="https://the-odds-api.com",
        credential_env=("THE_ODDS_API_KEY",),
        covers=("goal", "assist", "yellow_card", "red_card"),
        terms="Free tier, 500 requests a month. Attribution required.",
        probe=_probe_the_odds_api,
    ),
    PropSource(
        key="api-football",
        name="API-Football",
        homepage="https://www.api-football.com",
        credential_env=("API_FOOTBALL_API_KEY",),
        # The catalogue also lists player tackles, but that is not direct
        # DefCon coverage. FPL's threshold includes clearances, blocks and
        # interceptions for defenders, and recoveries outside defence. A
        # tackles line is partial experimental evidence until calibrated.
        #
        # Saves are different and were missing: the taxonomy names
        # `Goalkeeper Saves`, `Saves Total` and a home/away over-under, and FPL
        # pays a goalkeeper a point per three of them. No other source here
        # prices that route at all.
        covers=(
            "goal",
            "assist",
            "save",
            "yellow_card",
            "red_card",
            "clean_sheet",
        ),
        terms="Free tier, 100 requests a day.",
        probe=_probe_api_football,
    ),
    PropSource(
        key="betfair-exchange",
        name="Betfair Exchange",
        homepage="https://developer.betfair.com",
        credential_env=("BETFAIR_APP_KEY", "BETFAIR_SESSION_TOKEN"),
        covers=("goal", "assist", "clean_sheet", "yellow_card", "red_card"),
        terms="Delayed application key is free. Session token expires; refresh in CI.",
        probe=_probe_betfair,
    ),
    PropSource(
        key="football-data",
        name="football-data.co.uk",
        homepage="https://www.football-data.co.uk",
        credential_env=(),
        covers=("clean_sheet", "goals_conceded"),
        terms="Free. Match level only; no player markets at all.",
        probe=_probe_football_data,
    ),
    PropSource(
        key="understat",
        name="Understat",
        homepage="https://understat.com",
        credential_env=(),
        covers=("goal", "assist"),
        terms="Free, unofficial. A rate source, not a market.",
        probe=_probe_understat,
        market=False,
    ),
    PropSource(
        key="fpl-bootstrap",
        name="FPL bootstrap-static",
        homepage="https://fantasy.premierleague.com",
        credential_env=(),
        covers=SCORING_EVENTS,
        terms="Free, official. The scoring authority and the prediction target.",
        probe=_probe_fpl_elements,
        market=False,
    ),
)

_SOURCE_INDEX: dict[str, PropSource] = {source.key: source for source in PROP_SOURCES}


def source_by_key(key: str) -> PropSource:
    """The source with this key, or a KeyError naming what is available."""
    try:
        return _SOURCE_INDEX[key]
    except KeyError:
        known = ", ".join(sorted(_SOURCE_INDEX))
        raise KeyError(f"unknown source {key!r}; known sources are {known}") from None


def probe_source(
    source: PropSource,
    client: httpx.Client,
    env: Mapping[str, str] | None = None,
) -> ProbeResult:
    """Ask one source what it has, without ever failing the run."""
    environment = os.environ if env is None else env
    absent = _missing(source, environment)
    if absent is not None:
        return absent
    try:
        return source.probe(client, environment)
    except httpx.HTTPError as error:
        # A blocked host and a broken parser look identical in a traceback, and
        # only one of them means the survey found something out.
        return ProbeResult(
            key=source.key,
            status="unreachable",
            note=f"{type(error).__name__}: {error}",
        )


def survey(
    client: httpx.Client,
    sources: Sequence[PropSource] = PROP_SOURCES,
    env: Mapping[str, str] | None = None,
) -> tuple[ProbeResult, ...]:
    """Probe every source in turn. One failure never stops the rest."""
    return tuple(probe_source(source, client, env) for source in sources)
