"""Capture the published crowd signal for the current gameweek.

Aggregate ownership is legal to read before a deadline, unlike individual rival
picks, so this can run on a schedule from gameweek one without waiting for
anything to be processed.

Run repeatedly across a gameweek. Every capture is kept: how ownership moves
through the week is the signal, and an overwrite would destroy it.

Usage:
    python -m fpl_andres.cli.capture_crowd --season 2026-27
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from fpl_andres import cliargs
from fpl_andres.adapters.fpl import FplClient
from fpl_andres.bootstrap import CrowdElement, parse_elements
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capture-crowd")
    parser.add_argument(
        "--season",
        default=None,
        help="Season label. Defaults to the one implied by the fixture calendar.",
    )
    parser.add_argument(
        "--event",
        type=cliargs.event_id,
        default=None,
        help="Gameweek to label the capture with. Defaults to the current event.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def season_from(bootstrap: dict[str, Any]) -> str | None:
    """Derive the season label from the earliest published deadline.

    A season beginning in August 2026 is 2026-27. Deriving it beats configuring
    it: a stale repository variable would silently file a whole season of
    captures under the wrong label.
    """
    deadlines = [
        str(event["deadline_time"])
        for event in bootstrap.get("events") or []
        if event.get("deadline_time")
    ]
    if not deadlines:
        return None
    start = datetime.fromisoformat(min(deadlines).replace("Z", "+00:00"))
    # A deadline in January belongs to the season that began the previous August.
    year = start.year if start.month >= 7 else start.year - 1
    return f"{year}-{str(year + 1)[2:]}"


def _current_event(bootstrap: dict[str, Any]) -> int | None:
    for event in bootstrap.get("events") or []:
        if event.get("is_current"):
            return int(event["id"])
    # Before the season starts there is no current event; the next one is the
    # one being planned for, and ownership is already published for it.
    for event in bootstrap.get("events") or []:
        if event.get("is_next"):
            return int(event["id"])
    return None


def _rows(
    bootstrap: dict[str, Any],
    *,
    season: str,
    event: int,
    captured_at: datetime,
    snapshot_id: str,
) -> list[dict[str, Any]]:
    total_managers = bootstrap.get("total_players")
    rows: list[dict[str, Any]] = []
    for element in parse_elements(bootstrap.get("elements") or [], model=CrowdElement):
        rows.append(
            {
                "season": season,
                "event": event,
                "element_id": element.id,
                "captured_at": captured_at.isoformat(),
                "selected_by_percent": element.selected_by_percent,
                "transfers_in_event": element.transfers_in_event,
                "transfers_out_event": element.transfers_out_event,
                "total_managers": _optional_int(total_managers),
                "source_snapshot_id": snapshot_id,
            }
        )
    return rows


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


async def _capture(args: argparse.Namespace) -> int:
    async with httpx.AsyncClient() as http:
        client = FplClient(http=http, clock=lambda: datetime.now(UTC))
        bootstrap = await client.fetch_bootstrap()

    event = args.event or _current_event(bootstrap.payload)
    if event is None:
        # Failing is correct: labelling a capture with a guessed gameweek would
        # make the whole series unusable.
        print("FPL reports no current or next event; refusing to guess", file=sys.stderr)
        return 1

    season = args.season or season_from(bootstrap.payload)
    if season is None:
        print("FPL published no deadlines to derive a season from", file=sys.stderr)
        return 1

    captured_at = datetime.now(UTC)
    elements = len(bootstrap.payload.get("elements") or [])
    print(f"captured {elements} elements for {season} GW{event} at {captured_at.isoformat()}")

    if args.dry_run:
        return 0

    credentials = SupabaseCredentials.from_env(os.environ)
    with SupabaseRestClient(credentials) as supabase:
        snapshot_id = _record_snapshot(supabase, bootstrap.snapshot)
        rows = _rows(
            bootstrap.payload,
            season=season,
            event=event,
            captured_at=captured_at,
            snapshot_id=snapshot_id,
        )
        supabase.insert_ignoring_duplicates(
            "crowd_snapshots",
            rows,
            on_conflict="season,event,element_id,captured_at",
        )
    print(f"wrote {len(rows)} crowd rows")
    return 0


def _record_snapshot(client: SupabaseRestClient, snapshot: Any) -> str:
    written = client.insert(
        "source_snapshots",
        [
            {
                "source": snapshot.source,
                "fetched_at": snapshot.fetched_at.isoformat(),
                "data_available_at": snapshot.data_available_at.isoformat(),
                "content_hash": snapshot.content_hash,
                "upstream_reference": snapshot.upstream_reference,
            }
        ],
        returning=True,
    )
    return str(written[0]["id"])


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_capture(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
