"""Fetch player markets and write them where the projection can read them.

Runs on a GitHub runner, never on the owner's machine: every price host fails
at the TLS handshake behind that network's gambling-category filter. The
workflow that calls this holds the key as a repository secret.

Usage:

    python -m fpl_andres.cli.ingest_player_odds --season 2026-27
    python -m fpl_andres.cli.ingest_player_odds --season 2026-27 --budget 20

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
    by_kickoff,
    describe_event,
    fetch_event_odds,
    list_events,
    read_event,
)
from fpl_andres.models.player_odds import PlayerMatchOdds
from fpl_andres.timeouts import ODDS_FEED

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"

#: The free tier is 500 requests a month, shared with the weekly survey. What
#: one fixture costs against that is not known here and was never measured --
#: the host charges per market per region -- so the cap is written in requests
#: rather than fixtures. Whatever a fixture turns out to cost, a run cannot
#: spend more than this, and the run reports what it did spend so the number
#: below can be set from evidence instead of hope.
#:
#: Thirteen scheduled runs a month at this budget is 396, and the survey takes
#: another 48. `tests/test_api_budgets.py` holds that sum under the allowance.
DEFAULT_BUDGET = 30


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest-player-odds")
    parser.add_argument("--season", required=True, help="e.g. 2026-27")
    parser.add_argument(
        "--output",
        default="apps/web/src/data/player-odds.json",
        help="Where the site bundle reads it from.",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_BUDGET,
        help=(
            "Stop once this many requests have been spent, against a free tier "
            "of 500 a month. Fixtures are priced soonest first, so a small "
            f"budget still buys the ones being played. Default {DEFAULT_BUDGET}."
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
    key = os.environ.get("THE_ODDS_API_KEY", "").strip()
    if not key:
        print("THE_ODDS_API_KEY is not set; nothing to fetch", flush=True)
        return 1

    with httpx.Client(timeout=ODDS_FEED, follow_redirects=True) as client:
        # Listing is free, so this is the cheap read of what the key has left
        # before a single credit is spent.
        events, opening = list_events(client, key)
        print(f"{len(events)} Premier League fixtures priced \u2014 {opening}")

        rows: list[PlayerMatchOdds] = []
        offered = 0
        spent = 0
        closing = opening
        for event in by_kickoff(events):
            event_id = event.get("id")
            if not isinstance(event_id, str):
                continue
            if closing.remaining is not None and closing.remaining <= 0:
                print("  stopping: the key has no requests left this month")
                break
            if spent >= args.budget:
                print(f"  stopping: this run's budget of {args.budget} requests is spent")
                break
            payload, closing = fetch_event_odds(client, key, event_id)
            # A host that reports no cost still charged something, so a fixture
            # counts for one rather than nothing. Otherwise a missing header
            # turns the budget off and the run prices the whole division.
            spent += closing.cost or 1
            read = read_event(payload)
            if read:
                offered += 1
            print(
                f"  {payload.get('home_team')} v {payload.get('away_team')}: "
                f"{len(read)} players quoted \u2014 {describe_event(payload)}"
            )
            rows.extend(read)

        # The documented budget of one request per fixture was never measured.
        # This is the measurement, and the schedule should be sized off it.
        measured = (
            closing.used - opening.used
            if closing.used is not None and opening.used is not None
            else None
        )
        print(f"\nspent {measured if measured is not None else spent} requests; {closing}")

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
        f"\n{offered} fixtures quoted a player market, {len(priced)} priced rows, "
        f"{len(named)} matched to an FPL element, {len(unmatched)} names unmatched"
    )
    for name in unmatched[:20]:
        print(f"  unmatched: {name}")

    if not named and not args.allow_empty:
        if rows:
            # Quoted but unjoinable: the crosswalk is the fault and it should
            # be fixed, so this is still a failure.
            print("\nplayers were quoted but none joined an FPL element; refusing to write")
            return 1
        # Nothing quoted at all. Before a season the books price the result and
        # open player markets only days out, so an empty answer here is the
        # market's state rather than a fault, and failing red on it would train
        # the owner to ignore this workflow by the time it matters.
        print(
            "\nno player markets are open on these fixtures yet. The books are pricing "
            "the results; anytime scorer, assists, cards and shots on target usually "
            "appear closer to kick-off. Nothing written, nothing wrong."
        )
        return 0

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
