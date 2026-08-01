"""Ingest pinned historical seasons into the history corpus.

Usage:
    python -m fpl_andres.cli.ingest_historical --commit <40-char-sha>

Ingests every supported season by default. Requires ``SUPABASE_URL`` and
``SUPABASE_SECRET_KEY`` in the environment. Both are read unprefixed and never
echoed.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from fpl_andres import timeouts
from fpl_andres.adapters.vaastav import FutureInformationError, VaastavRevision
from fpl_andres.ingest.historical import (
    ArchiveFetcher,
    ArchiveFileNotPublished,
    HistoricalIngest,
    SeasonIngestResult,
)
from fpl_andres.persistence.supabase import (
    SupabaseCredentials,
    SupabaseRestClient,
    SupabaseWriteError,
)
from fpl_andres.persistence.workflow import open_run

WORKFLOW_NAME = "historical-ingest"

# 2019/20 was suspended and resumed, running to gameweek 47.
MAX_GAMEWEEK = 47

# The archive only publishes teams.csv and fixtures.csv from 2019-20 onward.
# Earlier seasons cannot satisfy the schema's foreign keys, so they are refused
# rather than partially ingested.
SUPPORTED_SEASONS: tuple[str, ...] = (
    "2019-20",
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26",
)


def parse_gameweeks(spec: str) -> tuple[int, ...]:
    """Parse ``1-38`` or ``1,4,9`` into an ordered, de-duplicated tuple."""
    selected: set[int] = set()
    for part in spec.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, _, end_text = chunk.partition("-")
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"gameweek range {chunk!r} is inverted")
            selected.update(range(start, end + 1))
        else:
            selected.add(int(chunk))
    if not selected:
        raise ValueError("no gameweeks selected")
    out_of_range = sorted(week for week in selected if not 1 <= week <= MAX_GAMEWEEK)
    if out_of_range:
        raise ValueError(f"gameweeks out of range: {out_of_range}")
    return tuple(sorted(selected))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest_historical",
        description="Ingest pinned vaastav seasons into the history corpus.",
    )
    parser.add_argument(
        "--seasons",
        default="all",
        help=(
            "comma-separated seasons, or 'all' for every supported season "
            f"({SUPPORTED_SEASONS[0]}..{SUPPORTED_SEASONS[-1]}). Default: all"
        ),
    )
    parser.add_argument("--commit", required=True, help="40-character archive commit SHA")
    parser.add_argument(
        "--gameweeks",
        default=f"1-{MAX_GAMEWEEK}",
        help=(
            f"gameweek selection such as 1-{MAX_GAMEWEEK} or 1,2,7 "
            f"(default: 1-{MAX_GAMEWEEK}). Gameweeks the archive does not "
            "publish for a season are skipped."
        ),
    )
    parser.add_argument(
        "--data-available-at",
        default=None,
        help=(
            "ISO-8601 UTC timestamp at which this archive revision became public. "
            "Defaults to now, which is correct for a completed season."
        ),
    )
    return parser


def parse_seasons(spec: str) -> tuple[str, ...]:
    """Resolve a season selection, rejecting anything the archive cannot serve."""
    if spec.strip().casefold() == "all":
        return SUPPORTED_SEASONS
    selected = tuple(part.strip() for part in spec.split(",") if part.strip())
    if not selected:
        raise ValueError("no seasons selected")
    unsupported = [season for season in selected if season not in SUPPORTED_SEASONS]
    if unsupported:
        raise ValueError(
            f"unsupported seasons: {', '.join(unsupported)}. "
            f"The archive publishes teams.csv and fixtures.csv only from "
            f"{SUPPORTED_SEASONS[0]} onward, and the schema's foreign keys "
            "require both."
        )
    return selected


def _resolve_available_at(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError("--data-available-at must carry a UTC offset")
    return parsed.astimezone(UTC)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    seasons = parse_seasons(args.seasons)
    gameweeks = parse_gameweeks(args.gameweeks)
    data_available_at = _resolve_available_at(args.data_available_at)
    credentials = SupabaseCredentials.from_env(os.environ)

    completed: list[SeasonIngestResult] = []
    failures: list[tuple[str, str]] = []

    with (
        SupabaseRestClient(credentials) as client,
        httpx.Client(timeout=timeouts.ARCHIVE_DOWNLOAD, follow_redirects=True) as http,
    ):
        ingest = HistoricalIngest(client=client, fetcher=ArchiveFetcher(http))
        for season in seasons:
            revision = VaastavRevision(commit_sha=args.commit, season=season)
            recorder = open_run(
                client,
                workflow_name=WORKFLOW_NAME,
                parts={
                    "season": season,
                    "commit": revision.commit_sha,
                    "gameweeks": args.gameweeks,
                },
            )
            # One workflow_run per season, so a partial failure stays traceable
            # and the surviving seasons are still resumable independently.
            try:
                with recorder as run:
                    result = ingest.ingest_season(
                        revision,
                        gameweeks=gameweeks,
                        data_available_at=data_available_at,
                    )
                    run.record_rows("teams", result.teams)
                    run.record_rows("elements", result.elements)
                    run.record_rows("fixtures", result.fixtures)
                    run.record_rows("element_gameweek_stats", result.total_stat_rows)
                completed.append(result)
                skipped = (
                    f", {len(result.unavailable_gameweeks)} not published "
                    f"({', '.join(str(gw) for gw in result.unavailable_gameweeks)})"
                    if result.unavailable_gameweeks
                    else ""
                )
                print(
                    f"  OK   {result.season}: {result.teams} teams, "
                    f"{result.elements} elements, {result.fixtures} fixtures, "
                    f"{result.total_stat_rows} gameweek rows{skipped}",
                    flush=True,
                )
            except (
                httpx.HTTPError,
                ArchiveFileNotPublished,
                FutureInformationError,
                SupabaseWriteError,
                ValidationError,
                ValueError,
                KeyError,
            ) as error:
                # Typed rather than bare: a schema break, a network failure and
                # a leak guard are three different problems, and one season
                # failing must not take the rest of the run with it. Anything
                # outside this set is a defect here and should crash loudly.
                failures.append((season, f"{type(error).__name__}: {error}"))
                print(f"  FAIL {season}: {type(error).__name__}: {error}", flush=True)

    print()
    print(f"seasons ingested: {len(completed)}/{len(seasons)}")
    print(f"total gameweek rows: {sum(r.total_stat_rows for r in completed)}")
    if failures:
        print()
        print("failures:")
        for season, reason in failures:
            print(f"  {season}: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
