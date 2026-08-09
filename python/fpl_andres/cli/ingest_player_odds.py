"""Fetch player markets and write them where the projection can read them.

Runs on a GitHub runner, never on the owner's machine: every price host fails
at the TLS handshake behind that network's gambling-category filter. The
workflow that calls this holds the key as a repository secret.

Usage:

    python -m fpl_andres.cli.ingest_player_odds --season 2026-27
    python -m fpl_andres.cli.ingest_player_odds --season 2026-27 --max-events 4

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fpl_andres.adapters.player_crosswalk import crosswalk
from fpl_andres.adapters.the_odds_api import (
    PLAYER_MARKETS,
    fetch_event_odds,
    list_events,
    read_event,
)
from fpl_andres.models.player_odds import PlayerMatchOdds
from fpl_andres.timeouts import ODDS_FEED

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"

#: The free tier is 500 requests a month and each event costs one, so a run
#: that priced every fixture every day would exhaust it in a fortnight.
DEFAULT_MAX_EVENTS = 10


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest-player-odds")
    parser.add_argument("--season", required=True, help="e.g. 2026-27")
    parser.add_argument(
        "--output",
        default="apps/web/src/data/player-odds.json",
        help="Where the site bundle reads it from.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=DEFAULT_MAX_EVENTS,
        help=(
            "Stop after this many fixtures. Each one costs a request against a "
            f"free tier of 500 a month. Default {DEFAULT_MAX_EVENTS}."
        ),
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help=(
            "Write an empty artifact instead of failing when no fixture is "
            "priced. Correct between seasons; wrong during one."
        ),
    )
    return parser


def _serialise(row: PlayerMatchOdds) -> dict[str, object]:
    payload = asdict(row)
    kickoff = payload.pop("kickoff")
    payload["kickoff"] = kickoff.isoformat() if kickoff is not None else None
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        print("ODDS_API_KEY is not set; nothing to fetch", flush=True)
        return 1

    with httpx.Client(timeout=ODDS_FEED, follow_redirects=True) as client:
        events = list_events(client, key)
        print(f"{len(events)} Premier League fixtures priced")

        rows: list[PlayerMatchOdds] = []
        for event in events[: args.max_events]:
            event_id = event.get("id")
            if not isinstance(event_id, str):
                continue
            payload = fetch_event_odds(client, key, event_id)
            read = read_event(payload)
            print(
                f"  {payload.get('home_team')} v {payload.get('away_team')}: "
                f"{len(read)} players quoted"
            )
            rows.extend(read)

        bootstrap = client.get(BOOTSTRAP, headers={"Accept": "application/json"})
        bootstrap.raise_for_status()
        static = bootstrap.json()

    clubs = {
        team["id"]: team["short_name"]
        for team in static.get("teams", [])
        if isinstance(team, dict) and "id" in team and "short_name" in team
    }
    matched, unmatched = crosswalk(rows, static.get("elements", []), clubs)

    priced = [row for row in matched if row.priced]
    named = [row for row in priced if row.element_id is not None]
    print(
        f"\n{len(priced)} priced rows, {len(named)} matched to an FPL element, "
        f"{len(unmatched)} names unmatched"
    )
    for name in unmatched[:20]:
        print(f"  unmatched: {name}")

    if not named and not args.allow_empty:
        print("\nno player was both priced and matched; refusing to write")
        return 1

    artifact = {
        "season": args.season,
        "fetchedAt": datetime.now(UTC).isoformat(),
        "source": "the-odds-api",
        "markets": list(PLAYER_MARKETS),
        "unmatched": list(unmatched),
        "players": [_serialise(row) for row in priced],
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"Written to {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
