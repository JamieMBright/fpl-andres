"""football-data.co.uk: free multi-bookmaker odds for the English leagues.

Two files matter. `mmz4281/{season}/E0.csv` is the season to date, one row per
played match, carrying the prices each match was played at. `fixtures.csv` is
the same shape for matches not yet played, refreshed a few times a week. The
first is what a backtest needs, the second is what a projection needs, and they
parse identically because they are the same columns.

**Which price columns, and why it decides whether the backtest is honest.**
The feed carries two sets: an early set collected the weekend before, and a
closing set collected just before kickoff, distinguished by a `C` after the
bookmaker. Closing prices are sharper — and unusable, because the FPL deadline
falls 90 minutes before the first kickoff of the gameweek and team news moves
prices in between. Fitting on closing prices would score information no manager
could have had, the same leak the corpus cutoff guards against elsewhere. This
parser therefore reads the early columns and refuses the closing ones.

Averages rather than one book: `AvgH` is the market's view, `B365H` is one
trader's, and a single book carries its own bias into every fixture.

Nothing here fetches. The URL builders and the parser are separate so the
parser can be tested against a fixed string, which is the only way to test a
source that this network refuses to reach.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime

__all__ = [
    "FixtureOdds",
    "OddsBatch",
    "OddsContractError",
    "fixtures_url",
    "parse_odds_csv",
    "season_url",
]

SEASON_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")

_ROOT = "https://www.football-data.co.uk"

#: Premier League. The feed keys divisions this way and E1 is the Championship.
PREMIER_LEAGUE = "E0"

#: Market-average columns, in preference order. The `Avg` set is every book the
#: feed samples; `B365` is the fallback for older seasons that predate it.
_MATCH_ODDS_COLUMNS = (("AvgH", "AvgD", "AvgA"), ("B365H", "B365D", "B365A"))
_OVER_UNDER_COLUMNS = (("Avg>2.5", "Avg<2.5"), ("B365>2.5", "B365<2.5"))

_REQUIRED = ("Date", "HomeTeam", "AwayTeam")


class OddsContractError(ValueError):
    """Raised when the feed is not the shape this parser was written against."""


@dataclass(frozen=True)
class FixtureOdds:
    """One match, with the two markets needed to recover a goals distribution."""

    division: str
    kickoff: datetime | None
    home_team: str
    away_team: str
    home_odds: float
    draw_odds: float
    away_odds: float
    over_odds: float
    under_odds: float
    #: Which column family supplied the prices, so a reader can see whether a
    #: row came from the market average or from a single book.
    price_source: str


@dataclass(frozen=True)
class OddsBatch:
    rows: tuple[FixtureOdds, ...]
    #: Rows the feed carried but this parser would not read, with the reason.
    skipped: tuple[tuple[str, str], ...]
    #: Every division the file carried, so "no Premier League fixtures yet" can
    #: be told apart from "the columns changed and everything was refused".
    divisions: tuple[str, ...]
    #: Rows matching the requested division, before any were refused.
    matched: int
    content_hash: str
    upstream_reference: str
    fetched_at: datetime


def season_url(season: str, division: str = PREMIER_LEAGUE) -> str:
    """`2026-27` becomes `mmz4281/2627/E0.csv`, which is how the feed names it."""
    match = SEASON_PATTERN.fullmatch(season)
    if match is None:
        raise OddsContractError("season must use the YYYY-YY format, e.g. 2026-27")
    start, end = match.groups()
    if not division.isalnum():
        raise OddsContractError(f"division must be alphanumeric, got {division!r}")
    return f"{_ROOT}/mmz4281/{start[2:]}{end}/{division}.csv"


def fixtures_url() -> str:
    """Matches not yet played, across every league the feed covers."""
    return f"{_ROOT}/fixtures.csv"


def _price(row: dict[str, str], column: str) -> float | None:
    raw = (row.get(column) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    # A quoted price at or below evens-on-everything is a blank cell that got a
    # zero rather than a market, and it would make the de-vig raise anyway.
    return value if value > 1.0 else None


def _kickoff(row: dict[str, str]) -> datetime | None:
    date = (row.get("Date") or "").strip()
    time = (row.get("Time") or "").strip() or "00:00"
    for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M"):
        try:
            return datetime.strptime(f"{date} {time}", pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_odds_csv(
    content: str,
    *,
    upstream_reference: str,
    fetched_at: datetime,
    division: str | None = PREMIER_LEAGUE,
) -> OddsBatch:
    """Read the feed into rows this repository can price, and say what it dropped.

    A row missing either market is skipped with a reason rather than filled in.
    Half a book cannot be de-vigged, and a fixture with no price is a fixture
    with no evidence, which is a different thing from a fixture priced level.
    """
    if fetched_at.tzinfo is None:
        raise OddsContractError("fetched_at must be timezone-aware UTC")

    # Some of these files are served with a byte-order mark, which lands inside
    # the first header name and makes `Div` unreadable. Trailing spaces appear
    # in others. Both silently emptied whole seasons before this.
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    reader.fieldnames = [name.strip().lstrip("\ufeff") for name in reader.fieldnames or []]
    header = reader.fieldnames
    missing = [column for column in _REQUIRED if column not in header]
    if missing:
        raise OddsContractError(
            f"{upstream_reference} is missing {', '.join(missing)}; the feed shape changed"
        )

    # A per-season file is one division by its URL. Only the combined fixture
    # list needs the column, so its absence is not a reason to read nothing.
    has_division_column = "Div" in header

    rows: list[FixtureOdds] = []
    skipped: list[tuple[str, str]] = []
    divisions: set[str] = set()
    matched = 0

    for row in reader:
        home = (row.get("HomeTeam") or "").strip()
        away = (row.get("AwayTeam") or "").strip()
        if not home or not away:
            continue

        label = f"{home} v {away}"
        found = (row.get("Div") or "").strip()
        if found:
            divisions.add(found)
        if division is not None and has_division_column and found and found != division:
            continue
        matched += 1

        match_odds: tuple[float, float, float] | None = None
        over_under: tuple[float, float] | None = None
        source = ""
        for family, (home_col, draw_col, away_col) in zip(
            ("average", "bet365"), _MATCH_ODDS_COLUMNS, strict=True
        ):
            home_price = _price(row, home_col)
            draw_price = _price(row, draw_col)
            away_price = _price(row, away_col)
            if home_price is not None and draw_price is not None and away_price is not None:
                match_odds = (home_price, draw_price, away_price)
                source = family
                break

        for over_col, under_col in _OVER_UNDER_COLUMNS:
            over_price = _price(row, over_col)
            under_price = _price(row, under_col)
            if over_price is not None and under_price is not None:
                over_under = (over_price, under_price)
                break

        if match_odds is None:
            skipped.append((label, "no complete 1X2 market"))
            continue
        if over_under is None:
            skipped.append((label, "no complete over/under 2.5 market"))
            continue

        rows.append(
            FixtureOdds(
                division=found or (division or ""),
                kickoff=_kickoff(row),
                home_team=home,
                away_team=away,
                home_odds=match_odds[0],
                draw_odds=match_odds[1],
                away_odds=match_odds[2],
                over_odds=over_under[0],
                under_odds=over_under[1],
                price_source=source,
            )
        )

    return OddsBatch(
        rows=tuple(rows),
        skipped=tuple(skipped),
        divisions=tuple(sorted(code for code in divisions if code)),
        matched=matched,
        content_hash="sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
        upstream_reference=upstream_reference,
        fetched_at=fetched_at,
    )
