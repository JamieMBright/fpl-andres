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
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from fpl_andres.adapters.player_crosswalk import crosswalk
from fpl_andres.adapters.the_odds_api import (
    PLAYER_MARKETS,
    Quota,
    by_kickoff,
    describe_event,
    fetch_event_odds,
    list_events,
    read_event,
)
from fpl_andres.jsonio import read_json_file
from fpl_andres.models.player_odds import PlayerMatchOdds
from fpl_andres.timeouts import ODDS_FEED

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"

#: The free tier is 500 requests a month, shared with the weekly survey.
#:
#: Measured 2026-08-10 rather than assumed: a survey request asking for eleven
#: markets across one region, of which the book offered four, was billed four.
#: So the charge is per market actually returned, not per market asked for, and
#: the ingest asks for eight markets and pays only for those returned. A capped
#: run cannot cover ten fully open fixtures, so it visits uncovered fixtures
#: before refreshing retained ones. Several daily runs then cover the gameweek
#: without repeatedly spending the allowance on the same first fixture.
#:
#: Thirty scheduled runs at the eight-credit hard cap cost at most 240, the
#: weekly team fallback about 176 and the survey about 53. The next fixture is
#: requested only when all eight markets could fit, so the cap cannot overshoot.
#: `tests/test_api_budgets.py` holds the shared sum under 500.
DEFAULT_BUDGET = len(PLAYER_MARKETS)
DEFAULT_DEADLINES = Path("apps/web/src/data/deadlines.json")
DEFAULT_WINDOW_DAYS = 7


@dataclass(frozen=True)
class DeadlineProximity:
    due: bool
    event: int
    deadline: datetime
    days: float


def can_request_fixture(*, spent: int, budget: int) -> bool:
    """Whether another fixture fits even if every requested market is open."""
    return spent + len(PLAYER_MARKETS) <= budget


def billed_request_cost(quota: Quota) -> int:
    """Keep an explicit free response free; only a missing header is one."""
    return quota.cost if quota.cost is not None else 1


def deadline_proximity(
    path: Path,
    *,
    within_days: float,
    now: datetime | None = None,
) -> DeadlineProximity:
    payload = read_json_file(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("deadlines"), list):
        raise ValueError(f"{path} published no deadline list")
    at = now if now is not None else datetime.now(UTC)
    upcoming: list[tuple[datetime, int]] = []
    for row in payload["deadlines"]:
        if not isinstance(row, dict):
            continue
        event = row.get("event")
        raw = row.get("deadline")
        if not isinstance(event, int) or not isinstance(raw, str):
            continue
        try:
            deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if deadline >= at:
            upcoming.append((deadline, event))
    if not upcoming:
        raise ValueError(f"{path} has no upcoming deadline")
    deadline, event = min(upcoming)
    days = (deadline - at).total_seconds() / 86_400
    return DeadlineProximity(
        due=days <= within_days,
        event=event,
        deadline=deadline,
        days=days,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest-player-odds")
    parser.add_argument("--season", required=True, help="e.g. 2026-27")
    parser.add_argument(
        "--output",
        default="apps/web/src/data/player-odds.json",
        help="Where the site bundle reads it from.",
    )
    parser.add_argument("--deadlines", default=str(DEFAULT_DEADLINES))
    parser.add_argument(
        "--within-days",
        type=float,
        default=DEFAULT_WINDOW_DAYS,
        help=(
            "Skip before reading the provider key unless the next FPL deadline "
            f"is this close. Default {DEFAULT_WINDOW_DAYS}."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore deadline proximity for an explicit manual survey.",
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
    for key in ("kickoff", "observed_at"):
        value = payload.pop(key)
        payload[key] = value.isoformat() if value is not None else None
    return payload


FixtureKey = tuple[str, str, datetime]


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def _event_key(event: Mapping[str, Any]) -> FixtureKey | None:
    home = event.get("home_team")
    away = event.get("away_team")
    kickoff = _timestamp(event.get("commence_time"))
    if not isinstance(home, str) or not isinstance(away, str) or kickoff is None:
        return None
    return home, away, kickoff


def _row_key(row: PlayerMatchOdds) -> FixtureKey | None:
    if row.kickoff is None:
        return None
    return row.home_team, row.away_team, row.kickoff.astimezone(UTC)


def prioritise_uncovered_events(
    events: Sequence[Mapping[str, Any]],
    previous: Sequence[PlayerMatchOdds],
) -> list[Mapping[str, Any]]:
    """Soonest uncovered fixtures first, then refresh the covered fixtures."""
    covered = {key for row in previous if (key := _row_key(row)) is not None}
    ordered = by_kickoff(events)
    return sorted(ordered, key=lambda event: _event_key(event) in covered)


def merge_fixture_rows(
    previous: Sequence[PlayerMatchOdds],
    fresh: Sequence[PlayerMatchOdds],
    current_fixtures: set[FixtureKey],
) -> list[PlayerMatchOdds]:
    """Replace freshly quoted fixtures and retain still-current older quotes."""
    refreshed = {key for row in fresh if (key := _row_key(row)) is not None}
    retained = [
        row
        for row in previous
        if (key := _row_key(row)) in current_fixtures and key not in refreshed
    ]
    return [*retained, *fresh]


def _read_previous(path: Path) -> list[PlayerMatchOdds]:
    if not path.exists():
        return []
    artifact = read_json_file(path)
    fallback = _timestamp(artifact.get("fetchedAt"))
    rows: list[PlayerMatchOdds] = []
    for raw in artifact.get("players", []):
        if not isinstance(raw, dict):
            continue
        home = raw.get("home_team")
        away = raw.get("away_team")
        name = raw.get("quoted_name")
        if not isinstance(home, str) or not isinstance(away, str) or not isinstance(name, str):
            continue
        rows.append(
            PlayerMatchOdds(
                element_id=(
                    raw.get("element_id") if isinstance(raw.get("element_id"), int) else None
                ),
                quoted_name=name,
                home_team=home,
                away_team=away,
                kickoff=_timestamp(raw.get("kickoff")),
                club=raw.get("club") if isinstance(raw.get("club"), str) else None,
                anytime_goal=_optional_number(raw.get("anytime_goal")),
                first_goal=_optional_number(raw.get("first_goal")),
                last_goal=_optional_number(raw.get("last_goal")),
                anytime_assist=_optional_number(raw.get("anytime_assist")),
                any_card=_optional_number(raw.get("any_card")),
                red_card=_optional_number(raw.get("red_card")),
                shots=_optional_number(raw.get("shots")),
                shots_on_target=_optional_number(raw.get("shots_on_target")),
                observed_at=_timestamp(raw.get("observed_at")) or fallback,
                books=int(raw.get("books", 0)),
            )
        )
    return rows


def _optional_number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.within_days <= 0:
        print("--within-days must be positive", flush=True)
        return 1
    if args.budget < len(PLAYER_MARKETS):
        print(
            f"--budget must reserve at least {len(PLAYER_MARKETS)} credits for one fixture",
            flush=True,
        )
        return 1
    if not args.force:
        try:
            proximity = deadline_proximity(
                Path(args.deadlines),
                within_days=args.within_days,
            )
        except ValueError as error:
            print(str(error), flush=True)
            return 1
        if not proximity.due:
            print(
                f"GW{proximity.event} is {proximity.days:.1f} days away, outside "
                f"the {args.within_days:g}-day player-market window. "
                "No provider request made.",
                flush=True,
            )
            return 0
    key = os.environ.get("THE_ODDS_API_KEY", "").strip()
    if not key:
        print("THE_ODDS_API_KEY is not set; nothing to fetch", flush=True)
        return 1

    output_path = Path(args.output)
    previous = _read_previous(output_path)
    fetched_at = datetime.now(UTC)

    with httpx.Client(timeout=ODDS_FEED, follow_redirects=True) as client:
        # Listing is free, so this is the cheap read of what the key has left
        # before a single credit is spent.
        events, opening = list_events(client, key)
        print(f"{len(events)} Premier League fixtures priced \u2014 {opening}")

        rows: list[PlayerMatchOdds] = []
        offered = 0
        spent = 0
        closing = opening
        current_fixtures = {
            fixture_key for event in events if (fixture_key := _event_key(event)) is not None
        }
        visited = 0
        for event in prioritise_uncovered_events(list(events), previous):
            event_id = event.get("id")
            if not isinstance(event_id, str):
                continue
            if closing.remaining is not None and closing.remaining <= 0:
                print("  stopping: the key has no requests left this month")
                break
            if not can_request_fixture(spent=spent, budget=args.budget):
                print(
                    f"  stopping: another fixture could exceed this run's hard "
                    f"cap of {args.budget} credits"
                )
                break
            payload, closing = fetch_event_odds(client, key, event_id)
            visited += 1
            # A host that reports no cost still charged something, so a fixture
            # counts for one rather than nothing. Otherwise a missing header
            # turns the budget off and the run prices the whole division.
            spent += billed_request_cost(closing)
            read = read_event(payload)
            if read:
                offered += 1
            print(
                f"  {payload.get('home_team')} v {payload.get('away_team')}: "
                f"{len(read)} players quoted \u2014 {describe_event(payload)}"
            )
            rows.extend(replace(row, observed_at=fetched_at) for row in read)

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
    merged = merge_fixture_rows(previous, rows, current_fixtures)
    matched, unmatched = crosswalk(merged, static.get("elements", []), clubs)

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
        "fetchedAt": fetched_at.isoformat(),
        "source": "the-odds-api",
        "markets": list(PLAYER_MARKETS),
        "coverage": {
            "fixturesListed": len(current_fixtures),
            "fixturesVisitedThisRun": visited,
            "fixturesWithQuotes": len(
                {fixture_key for row in priced if (fixture_key := _row_key(row)) is not None}
            ),
        },
        "unmatched": list(unmatched),
        "players": [_serialise(row) for row in priced],
    }
    path = output_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"Written to {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
