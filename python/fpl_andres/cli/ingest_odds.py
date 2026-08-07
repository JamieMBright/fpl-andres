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
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fpl_andres.adapters.football_data import (
    FixtureOdds,
    OddsBatch,
    OddsContractError,
    fixtures_url,
    parse_odds_csv,
    season_url,
)
from fpl_andres.models.fixture_odds import club_views, load_fixture_odds
from fpl_andres.models.goal_expectation import GoalExpectation, fit_goal_expectation
from fpl_andres.models.odds import OddsUnavailable
from fpl_andres.timeouts import ODDS_FEED

DEFAULT_OUTPUT = Path("apps/web/src/data/fixture-odds.json")

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
    "Leicester": "LEI",
    "Liverpool": "LIV",
    "Man City": "MCI",
    "Man United": "MUN",
    "Newcastle": "NEW",
    "Norwich": "NOR",
    "Nott'm Forest": "NFO",
    "Sheffield United": "SHU",
    "Southampton": "SOU",
    "Sunderland": "SUN",
    "Tottenham": "TOT",
    "Watford": "WAT",
    "West Brom": "WBA",
    "West Ham": "WHU",
    "Wolves": "WOL",
}


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
    return parser


def _fetch(url: str, client: httpx.Client) -> str:
    try:
        response = client.get(url, timeout=ODDS_FEED)
    except httpx.HTTPError as error:
        raise OddsIngestError(
            f"{url} could not be reached: {error}. This CLI cannot run behind a "
            "gambling-category content filter; run it on a GitHub runner."
        ) from error
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


def _entry(row: FixtureOdds, fit: GoalExpectation) -> dict[str, object]:
    home = TEAM_CODES.get(row.home_team)
    away = TEAM_CODES.get(row.away_team)
    if home is None or away is None:
        missing = row.home_team if home is None else row.away_team
        raise UnknownClubError(f"no FPL code for {missing!r}; add it to TEAM_CODES")
    return {
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


def _read(batch: OddsBatch) -> tuple[list[dict[str, object]], list[tuple[str, str]]]:
    entries: list[dict[str, object]] = []
    refused = list(batch.skipped)
    for row in batch.rows:
        try:
            entries.append(_entry(row, _priced(row)))
        except (OddsUnavailable, UnknownClubError, ValueError) as error:
            refused.append((f"{row.home_team} v {row.away_team}", str(error)))
    return entries, refused


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    fetched_at = datetime.now(UTC)

    sources: list[str] = [season_url(args.season)]
    if not args.skip_fixtures:
        sources.append(fixtures_url())

    entries: list[dict[str, object]] = []
    refused: list[tuple[str, str]] = []
    provenance: list[dict[str, str]] = []

    with httpx.Client(follow_redirects=True) as client:
        for url in sources:
            content = _fetch(url, client)
            try:
                batch = parse_odds_csv(content, upstream_reference=url, fetched_at=fetched_at)
            except OddsContractError as error:
                raise OddsIngestError(str(error)) from error
            read, skipped = _read(batch)
            entries.extend(read)
            refused.extend(skipped)
            provenance.append({"url": url, "contentHash": batch.content_hash})

    if not entries:
        raise OddsIngestError(
            "no fixture carried both a 1X2 and an over/under market; refusing to "
            "publish an artifact with nothing in it"
        )

    artifact = {
        "schemaVersion": ODDS_SCHEMA_VERSION,
        "generatedAt": fetched_at.isoformat(),
        "season": args.season,
        "source": "football-data.co.uk",
        # Early prices, not closing: the FPL deadline falls before kickoff and
        # closing prices carry team news no manager could have acted on.
        "priceTiming": "pre-match",
        "evidenceLevel": "observed",
        "provenance": provenance,
        "fixtures": entries,
        "refused": [{"fixture": name, "reason": why} for name, why in refused],
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    # Read it straight back through the loader the model uses. A file that
    # cannot be joined onto clubs is worse than no file: it looks like evidence.
    views = club_views(load_fixture_odds(output))
    if not views:
        raise OddsIngestError(f"{output} joined onto no clubs; refusing to call it good")

    print(
        f"wrote {len(entries)} priced fixtures across {len(views)} clubs to "
        f"{output}, refused {len(refused)}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
