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
from fpl_andres.adapters.payloads import BootstrapPayload
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


def season_from(bootstrap: BootstrapPayload) -> str | None:
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


def _current_event(bootstrap: BootstrapPayload) -> int | None:
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
    bootstrap: BootstrapPayload,
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
        missing = _unseeded(supabase, season)
        if missing is not None:
            # The season is not in the corpus yet. Seed it from the bootstrap
            # data that was already fetched, then proceed with the capture.
            snapshot_id = _record_snapshot(supabase, bootstrap.snapshot)
            _seed_live_season(
                supabase,
                bootstrap.payload,
                season=season,
                snapshot_id=snapshot_id,
            )
        else:
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


def _unseeded(client: SupabaseRestClient, season: str) -> str | None:
    """Why the write is about to fail, said before anything is written.

    `crowd_snapshots.season` references `seasons`, and `(season, element_id)`
    references `elements`. Both are filled by the historical ingest, which
    reads a published archive -- and an archive of a season only exists once
    that season has been played.

    So the live capture depends on a corpus that cannot yet contain the season
    it is capturing. Every run of this job since it was written has failed on
    that foreign key, and it failed as an opaque PostgREST status because the
    check happened inside the database rather than here.

    Checked before `source_snapshots` is written, because the old order left an
    orphan snapshot row behind on every failed run.
    """
    rows = client.select("seasons", columns="season", filters={"season": f"eq.{season}"})
    if rows:
        return None
    return (
        f"{season} is not in the corpus, so the crowd capture has nothing to "
        f"reference: crowd_snapshots.season is a foreign key into seasons, and "
        f"(season, element_id) is one into elements. Ingest the season first. "
        f"Refusing rather than writing a snapshot row that nothing can point at."
    )


def _seed_live_season(
    client: SupabaseRestClient,
    bootstrap: BootstrapPayload,
    *,
    season: str,
    snapshot_id: str,
) -> None:
    """Seed seasons/teams/elements for a live season from the FPL bootstrap.

    The historical ingest fills these tables from the vaastav archive, which
    only covers completed seasons. The crowd capture needs them for the current
    season too, so the first run that finds them absent seeds them from the
    same bootstrap payload it already fetched. This is idempotent: upserts
    replace nothing and the snapshot_id records what data was used.
    """
    client.insert_ignoring_duplicates("seasons", [{"season": season}], on_conflict="season")

    raw_teams = bootstrap.get("teams") or []
    teams = [
        {
            "season": season,
            "team_id": int(team["id"]),
            "code": int(team["code"]),
            "name": str(team.get("name") or ""),
            "short_name": str(team.get("short_name") or ""),
            "strength": team.get("strength"),
            "strength_overall_home": team.get("strength_overall_home"),
            "strength_overall_away": team.get("strength_overall_away"),
            "strength_attack_home": team.get("strength_attack_home"),
            "strength_attack_away": team.get("strength_attack_away"),
            "strength_defence_home": team.get("strength_defence_home"),
            "strength_defence_away": team.get("strength_defence_away"),
            "source_snapshot_id": snapshot_id,
        }
        for team in raw_teams
        if team.get("id") and team.get("code")
    ]
    if teams:
        client.upsert("teams", teams, on_conflict="season,team_id")

    raw_elements = bootstrap.get("elements") or []
    elements = []
    for raw in raw_elements:
        element_id = raw.get("id")
        code = raw.get("code")
        team_id = raw.get("team")
        if not (element_id and code and team_id):
            continue
        first_name = str(raw.get("first_name") or "")
        second_name = str(raw.get("second_name") or "")
        web_name = str(raw.get("web_name") or "") or second_name or first_name
        elements.append(
            {
                "season": season,
                "element_id": int(element_id),
                "code": int(code),
                "first_name": first_name,
                "second_name": second_name,
                "web_name": web_name,
                "element_type": int(raw.get("element_type", 0)),
                "team_id": int(team_id),
                "start_cost": raw.get("now_cost"),
                "source_snapshot_id": snapshot_id,
            }
        )
    if elements:
        client.upsert("elements", elements, on_conflict="season,element_id")

    print(
        f"seeded {season} live corpus: {len(teams)} teams, {len(elements)} elements",
        file=sys.stderr,
    )


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
