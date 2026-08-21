"""Probe historical API-Football odds access without retaining prices."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fpl_andres.adapters.api_football_historical import (
    HistoricalProbe,
    probe_historical_seasons,
)
from fpl_andres.timeouts import ODDS_FEED

DEFAULT_OUTPUT = Path("data/odds/api-football-historical-capability.json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="probe-api-football-historical")
    parser.add_argument(
        "--season",
        action="append",
        type=int,
        dest="seasons",
        default=None,
        help="Completed season start year to probe; repeatable (default: 2022, 2023, 2024).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Sanitized JSON report path.",
    )
    return parser


def _as_json(results: Sequence[HistoricalProbe]) -> dict[str, object]:
    return {
        "probedAt": datetime.now(UTC).isoformat(),
        "provider": "api-football",
        "league": "39",
        "seasons": [
            {
                "season": result.season,
                "status": result.status,
                "fixtureId": result.fixture_id,
                "bookmakers": result.bookmakers,
                "bets": result.bets,
                "playerNamedSelections": result.player_named_selections,
                "responseBytes": result.response_bytes,
                "fetchedAt": result.fetched_at.isoformat(),
                "quotaRemaining": result.quota_remaining,
                "error": result.error,
            }
            for result in results
        ],
    }


def _report(result: HistoricalProbe) -> None:
    detail = result.error or (
        f"fixture {result.fixture_id}, {result.bookmakers} bookmakers, "
        f"{result.bets} bets, {result.player_named_selections} player selections"
    )
    quota = (
        f", {result.quota_remaining} requests left" if result.quota_remaining is not None else ""
    )
    print(f"{result.season}: {result.status} ({detail}{quota})")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    key = os.environ.get("API_FOOTBALL_API_KEY", "")
    if not key:
        print("API_FOOTBALL_API_KEY is not set", flush=True)
        return 1
    fetched_at = datetime.now(UTC)
    seasons = tuple(args.seasons or (2022, 2023, 2024))
    with httpx.Client(timeout=ODDS_FEED, follow_redirects=True) as client:
        results = probe_historical_seasons(client, key, seasons=seasons, fetched_at=fetched_at)
    for result in results:
        _report(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(_as_json(results), indent=2) + "\n", encoding="utf-8")
    print(f"Capability report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
