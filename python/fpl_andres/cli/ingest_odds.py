"""Fetch bookmaker odds and publish the goals distribution they imply.

Runs on a GitHub runner, never on the owner's machine: every price host fails at
the TLS handshake behind that network's gambling-category filter, while the same
hosts answer normally from CI. That is a property of the desk, not of the feed,
so this CLI simply assumes it can reach the internet and reports honestly when
it cannot.

What it publishes is not odds. It is, per fixture, both sides' expected goals
and the clean-sheet probability that follows, because those are the quantities
the scoring model already speaks. The prices themselves are an input, kept only
as provenance. Nothing here emits or implies a betting recommendation.

Usage:

    python -m fpl_andres.cli.ingest_odds --season 2026-27
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from fpl_andres.adapters.football_data import (
    FixtureOdds,
    OddsBatch,
    OddsContractError,
    fixtures_url,
    parse_odds_csv,
    season_url,
)
from fpl_andres.adapters.the_odds_api import (
    by_kickoff,
    fetch_event_odds,
    list_events,
    read_fixture_odds,
)
from fpl_andres.jsonio import read_json_file
from fpl_andres.models.fixture_odds import club_views, load_fixture_odds
from fpl_andres.models.goal_expectation import GoalExpectation, fit_goal_expectation
from fpl_andres.models.odds import OddsUnavailable
from fpl_andres.timeouts import ODDS_FEED

DEFAULT_OUTPUT = Path("apps/web/src/data/fixture-odds.json")

#: Past seasons live in the corpus, not the site bundle.
DEFAULT_BACKFILL_DIR = Path("data/odds")

#: The seasons the backtest runs on. Odds have to cover the same ground or the
#: comparison against the history model has nothing to stand on.
BACKTEST_SEASONS = ("2022-23", "2023-24", "2024-25", "2025-26")

TEAM_FALLBACK_MARKETS = ("h2h", "totals")
TEAM_FALLBACK_FIXTURES = 10
TEAM_FALLBACK_WINDOW_DAYS = 6
TEAM_FALLBACK_WEEKLY_BUDGET = len(TEAM_FALLBACK_MARKETS) * TEAM_FALLBACK_FIXTURES

#: A completed Premier League season. Fewer means a club fell out of the
#: crosswalk and took all 38 of its fixtures with it.
EXPECTED_CLUBS = 20

#: Bumped when the published shape changes, so a stale artifact is detectable.
ODDS_SCHEMA_VERSION = 1

#: football-data.co.uk club names against FPL short codes, which is the key
#: every other artifact in this repository joins on. A name that is not here is
#: reported and its fixture refused, because a silently dropped fixture is a
#: fixture priced as if it had no market -- the one failure mode that would be
#: invisible downstream.
TEAM_CODES: dict[str, str] = {
    "Arsenal": "ARS",
    "Aston Villa": "AVL",
    "Bournemouth": "BOU",
    "Brentford": "BRE",
    "Brighton": "BHA",
    "Brighton and Hove Albion": "BHA",
    "Burnley": "BUR",
    "Chelsea": "CHE",
    "Coventry": "COV",
    "Coventry City": "COV",
    "Crystal Palace": "CRY",
    "Everton": "EVE",
    "Fulham": "FUL",
    "Hull": "HUL",
    "Hull City": "HUL",
    "Ipswich": "IPS",
    "Leeds": "LEE",
    "Leeds United": "LEE",
    "Leicester": "LEI",
    "Liverpool": "LIV",
    "Luton": "LUT",
    "Man City": "MCI",
    "Manchester City": "MCI",
    "Man United": "MUN",
    "Manchester United": "MUN",
    "Middlesbrough": "MID",
    "Newcastle": "NEW",
    "Newcastle United": "NEW",
    "Norwich": "NOR",
    "Nott'm Forest": "NFO",
    "Nottingham Forest": "NFO",
    "Sheffield United": "SHU",
    "Southampton": "SOU",
    "Stoke": "STK",
    "Sunderland": "SUN",
    "Swansea": "SWA",
    "Tottenham": "TOT",
    "Tottenham Hotspur": "TOT",
    "Watford": "WAT",
    "West Brom": "WBA",
    "West Ham": "WHU",
    "Wolves": "WOL",
    "Wolverhampton Wanderers": "WOL",
}

FixtureKey = tuple[str, str, datetime]


def _iso_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _entry_key(row: Mapping[str, object]) -> FixtureKey | None:
    home = row.get("home")
    away = row.get("away")
    kickoff = _iso_time(row.get("kickoff"))
    if not isinstance(home, str) or not isinstance(away, str) or kickoff is None:
        return None
    return home, away, kickoff


def _event_key(event: Mapping[str, Any]) -> FixtureKey | None:
    home = event.get("home_team")
    away = event.get("away_team")
    kickoff = _iso_time(event.get("commence_time"))
    if not isinstance(home, str) or not isinstance(away, str) or kickoff is None:
        return None
    home_code = TEAM_CODES.get(home)
    away_code = TEAM_CODES.get(away)
    if home_code is None or away_code is None:
        return None
    return home_code, away_code, kickoff


def _uncovered_team_events(
    events: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, object]],
) -> list[Mapping[str, Any]]:
    """Uncovered fixtures in the nearest six-day match window, capped at ten."""
    ordered = by_kickoff(events)
    dated = [(event, _event_key(event)) for event in ordered]
    readable = [(event, key) for event, key in dated if key is not None]
    if not readable:
        return []
    first = readable[0][1]
    assert first is not None
    ceiling = first[2] + timedelta(days=TEAM_FALLBACK_WINDOW_DAYS)
    covered = {key for row in existing if (key := _entry_key(row)) is not None}
    return [
        event
        for event, key in readable
        if key is not None and key[2] <= ceiling and key not in covered
    ][:TEAM_FALLBACK_FIXTURES]


def _merge_fixture_entries(
    previous: Sequence[Mapping[str, object]],
    fresh: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    refreshed = {key for row in fresh if (key := _entry_key(row)) is not None}
    retained = [dict(row) for row in previous if _entry_key(row) not in refreshed]
    return [*retained, *(dict(row) for row in fresh)]


class OddsIngestError(RuntimeError):
    """Raised when the feed cannot be reached or read."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest-odds")
    parser.add_argument(
        "--season",
        required=True,
        help="Season in YYYY-YY form, e.g. 2026-27. Used for the played-match file.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Where to write the artifact.",
    )
    parser.add_argument(
        "--skip-fixtures",
        action="store_true",
        help="Read only matches already played. Used when the fixture file is empty out of season.",
    )
    parser.add_argument(
        "--backfill-seasons",
        nargs="*",
        default=[],
        metavar="SEASON",
        help=(
            "Past seasons to fetch as well, e.g. 2022-23 2023-24. Each is written "
            "to its own file under --backfill-dir, not into the site bundle."
        ),
    )
    parser.add_argument(
        "--backfill-dir",
        default=str(DEFAULT_BACKFILL_DIR),
        help="Where per-season history lands.",
    )
    return parser


def _fetch(url: str, client: httpx.Client, *, required: bool = True) -> str | None:
    """Fetch a feed file. A 404 on an optional file means "not yet", not "broken".

    football-data.co.uk creates a season's played-match file only once matches
    have been played in it, so between seasons the current season 404s while
    the fixture list is already priced. Treating that as a failure stopped the
    job in exactly the weeks a manager is choosing an opening squad.
    """
    try:
        response = client.get(url, timeout=ODDS_FEED)
    except httpx.HTTPError as error:
        raise OddsIngestError(
            f"{url} could not be reached: {error}. This CLI cannot run behind a "
            "gambling-category content filter; run it on a GitHub runner."
        ) from error
    if response.status_code == 404 and not required:
        print(f"{url} is not published yet; carrying on without it")
        return None
    if response.status_code != 200:
        raise OddsIngestError(f"{url} answered {response.status_code}, not 200")
    return response.text


def _priced(row: FixtureOdds) -> GoalExpectation:
    return fit_goal_expectation(
        (row.home_odds, row.draw_odds, row.away_odds),
        (row.over_odds, row.under_odds),
    )


class UnknownClubError(OddsIngestError):
    """Raised when the feed names a club this crosswalk does not carry."""


def _entry(row: FixtureOdds, fit: GoalExpectation, *, keep_markets: bool) -> dict[str, object]:
    home = TEAM_CODES.get(row.home_team)
    away = TEAM_CODES.get(row.away_team)
    if home is None or away is None:
        missing = row.home_team if home is None else row.away_team
        raise UnknownClubError(f"no FPL code for {missing!r}; add it to TEAM_CODES")
    entry: dict[str, object] = {
        "kickoff": None if row.kickoff is None else row.kickoff.isoformat(),
        "home": home,
        "away": away,
        "homeExpectedGoals": round(fit.home, 4),
        "awayExpectedGoals": round(fit.away, 4),
        "homeCleanSheet": round(fit.home_clean_sheet, 4),
        "awayCleanSheet": round(fit.away_clean_sheet, 4),
        # Positive means the market prices more draws than independent Poisson
        # produces. Published so a reader can see the correction not applied.
        "drawResidual": round(fit.draw_residual, 4),
        "priceSource": row.price_source,
    }
    if keep_markets:
        # Every quoted price in the row, not only the two this model reads. A
        # price is only collectable while it is quoted, so anything not kept
        # today cannot be recovered later. Corpus files only: the site needs
        # the derived numbers, not a hundred prices per fixture.
        entry["markets"] = {name: round(price, 3) for name, price in sorted(row.markets.items())}
    return entry


def _read(
    batch: OddsBatch, *, keep_markets: bool
) -> tuple[list[dict[str, object]], list[tuple[str, str]]]:
    entries: list[dict[str, object]] = []
    refused = list(batch.skipped)
    for row in batch.rows:
        try:
            entries.append(_entry(row, _priced(row), keep_markets=keep_markets))
        except (OddsUnavailable, UnknownClubError, ValueError) as error:
            refused.append((f"{row.home_team} v {row.away_team}", str(error)))
    return entries, refused


def _collect(
    urls: Sequence[tuple[str, bool]],
    client: httpx.Client,
    fetched_at: datetime,
    *,
    keep_markets: bool = False,
) -> tuple[list[dict[str, object]], list[tuple[str, str]], list[dict[str, str]], int]:
    entries: list[dict[str, object]] = []
    refused: list[tuple[str, str]] = []
    provenance: list[dict[str, str]] = []
    matched = 0

    for url, required in urls:
        content = _fetch(url, client, required=required)
        if content is None:
            continue
        try:
            batch = parse_odds_csv(content, upstream_reference=url, fetched_at=fetched_at)
        except OddsContractError as error:
            raise OddsIngestError(str(error)) from error
        read, skipped = _read(batch, keep_markets=keep_markets)
        matched += batch.matched
        print(
            f"{url}: {batch.matched} Premier League rows of divisions "
            f"{', '.join(batch.divisions) or 'none'}; {len(read)} priced"
        )
        entries.extend(read)
        refused.extend(skipped)
        provenance.append({"url": url, "contentHash": batch.content_hash})

    return entries, refused, provenance, matched


def _existing_live(path: Path) -> tuple[list[dict[str, object]], list[dict[str, str]], str]:
    if not path.exists():
        return [], [], ""
    artifact = read_json_file(path)
    fixtures = artifact.get("fixtures")
    provenance = artifact.get("provenance")
    return (
        [dict(row) for row in fixtures if isinstance(row, Mapping)]
        if isinstance(fixtures, list)
        else [],
        [dict(row) for row in provenance if isinstance(row, Mapping)]
        if isinstance(provenance, list)
        else [],
        str(artifact.get("source") or ""),
    )


def _collect_the_odds_api(
    client: httpx.Client,
    api_key: str,
    existing: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[tuple[str, str]], list[dict[str, str]]]:
    events, opening = list_events(client, api_key)
    selected = _uncovered_team_events(events, existing)
    print(
        f"The Odds API: {len(events)} fixtures listed, {len(selected)} "
        f"uncovered in the current round; {opening}"
    )
    entries: list[dict[str, object]] = []
    refused: list[tuple[str, str]] = []
    provenance: list[dict[str, str]] = []
    closing = opening
    for event in selected:
        event_id = event.get("id")
        if not isinstance(event_id, str):
            continue
        if closing.remaining is not None and closing.remaining <= 0:
            refused.append((event_id, "the key has no requests left this month"))
            break
        payload, closing = fetch_event_odds(
            client,
            api_key,
            event_id,
            markets=TEAM_FALLBACK_MARKETS,
        )
        row = read_fixture_odds(payload)
        label = f"{payload.get('home_team')} v {payload.get('away_team')}"
        if row is None:
            refused.append((label, "no complete 1X2 and over/under 2.5 markets"))
            continue
        try:
            entries.append(_entry(row, _priced(row), keep_markets=False))
        except (OddsUnavailable, UnknownClubError, ValueError) as error:
            refused.append((label, str(error)))
            continue
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        provenance.append(
            {
                "url": f"https://api.the-odds-api.com/v4/sports/soccer_epl/events/{event_id}/odds",
                "contentHash": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
            }
        )
        print(f"  {label}: team markets priced; {closing}")
    return entries, refused, provenance


def _artifact(
    season: str,
    fetched_at: datetime,
    entries: list[dict[str, object]],
    refused: list[tuple[str, str]],
    provenance: list[dict[str, str]],
    *,
    source: str = "football-data.co.uk",
) -> dict[str, object]:
    return {
        "schemaVersion": ODDS_SCHEMA_VERSION,
        "generatedAt": fetched_at.isoformat(),
        "season": season,
        "source": source,
        # Early prices, not closing: the FPL deadline falls before kickoff and
        # closing prices carry team news no manager could have acted on.
        "priceTiming": "pre-match",
        "evidenceLevel": "observed",
        "provenance": provenance,
        "fixtures": entries,
        "refused": [{"fixture": name, "reason": why} for name, why in refused],
    }


def _write(path: Path, artifact: dict[str, object]) -> int:
    """Write, then read straight back through the loader the model uses.

    A file that cannot be joined onto clubs is worse than no file: it looks
    like evidence.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    views = club_views(load_fixture_odds(path))
    if not views:
        raise OddsIngestError(f"{path} joined onto no clubs; refusing to call it good")
    return len(views)


def _publish_live(
    args: argparse.Namespace,
    client: httpx.Client,
    fetched_at: datetime,
) -> None:
    live: list[tuple[str, bool]] = [(season_url(args.season), False)]
    if not args.skip_fixtures:
        live.append((fixtures_url(), True))
    entries, refused, provenance, matched = _collect(live, client, fetched_at)
    output = Path(args.output)
    if entries:
        clubs = _write(
            output,
            _artifact(args.season, fetched_at, entries, refused, provenance),
        )
        print(
            f"wrote {len(entries)} priced fixtures across {clubs} clubs to "
            f"{output}, refused {len(refused)}"
        )
        return

    previous, previous_provenance, previous_source = _existing_live(output)
    api_key = os.environ.get("THE_ODDS_API_KEY", "").strip()
    fallback: list[dict[str, object]] = []
    fallback_refused: list[tuple[str, str]] = []
    fallback_provenance: list[dict[str, str]] = []
    if api_key:
        fallback, fallback_refused, fallback_provenance = _collect_the_odds_api(
            client,
            api_key,
            previous,
        )
    if fallback:
        merged = _merge_fixture_entries(previous, fallback)
        sources = {source for source in previous_source.split(" + ") if source}
        sources.add("the-odds-api")
        artifact = _artifact(
            args.season,
            fetched_at,
            merged,
            [*refused, *fallback_refused],
            [*previous_provenance, *fallback_provenance],
            source=" + ".join(sorted(sources)),
        )
        clubs = _write(output, artifact)
        print(
            f"wrote {len(merged)} retained fixtures across {clubs} clubs to "
            f"{output}, added {len(fallback)} from The Odds API"
        )
        return

    if matched == 0:
        detail = (
            f"; retained {len(previous)} existing fixtures"
            if previous
            else "; no fallback key or uncovered team market"
        )
        print(f"no new Premier League fixture is priced for {args.season}{detail}")
        return

    for name, why in refused[:10]:
        print(f"  refused {name}: {why}")
    raise OddsIngestError(
        f"{matched} Premier League rows were found and none carried both a "
        "1X2 and an over/under market. The column names have probably "
        "changed; the refusals above say which."
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    fetched_at = datetime.now(UTC)

    with httpx.Client(follow_redirects=True) as client:
        _publish_live(args, client, fetched_at)

        # History lands outside the site bundle. Four seasons is about fifteen
        # hundred fixtures, which belongs in the corpus rather than in every
        # visitor's download.
        for season in args.backfill_seasons:
            past, past_refused, past_provenance, _past_matched = _collect(
                [(season_url(season), True)], client, fetched_at, keep_markets=True
            )
            if not past:
                for name, why in past_refused[:10]:
                    print(f"  refused {name}: {why}")
                raise OddsIngestError(f"{season} carried no priced fixture at all")
            if past_refused:
                # A whole club going missing is 38 fixtures and reads as a small
                # shortfall, so name the reasons rather than only counting them.
                for name, why in past_refused[:5]:
                    print(f"  refused {name}: {why}")
            path = Path(args.backfill_dir) / f"{season}.json"
            count = _write(
                path,
                _artifact(season, fetched_at, past, past_refused, past_provenance),
            )
            # A completed Premier League season is twenty clubs. Nineteen means
            # a club fell out of the crosswalk and took all 38 of its fixtures
            # with it, which is a hole a backtest would never announce.
            if count != EXPECTED_CLUBS:
                raise OddsIngestError(
                    f"{season} joined onto {count} clubs, not {EXPECTED_CLUBS}. "
                    "A club is missing from TEAM_CODES; the refusals above name it."
                )
            print(
                f"wrote {len(past)} priced fixtures across {count} clubs to "
                f"{path}, refused {len(past_refused)}"
            )

    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
