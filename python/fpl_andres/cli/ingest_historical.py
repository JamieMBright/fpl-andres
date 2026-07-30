"""Ingest pinned historical seasons into the history corpus.

Usage:
    python -m fpl_andres.cli.ingest_historical \\
        --season 2024-25 --commit <40-char-sha> --gameweeks 1-38

Requires ``SUPABASE_URL`` and ``SUPABASE_SECRET_KEY`` in the environment. Both
are read unprefixed and never echoed.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx

from fpl_andres.adapters.vaastav import VaastavRevision
from fpl_andres.ingest.historical import ArchiveFetcher, HistoricalIngest
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient
from fpl_andres.persistence.workflow import open_run

WORKFLOW_NAME = "historical-ingest"


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
    out_of_range = sorted(week for week in selected if not 1 <= week <= 38)
    if out_of_range:
        raise ValueError(f"gameweeks out of range: {out_of_range}")
    return tuple(sorted(selected))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest_historical",
        description="Ingest a pinned vaastav season into the history corpus.",
    )
    parser.add_argument("--season", required=True, help="archive season, e.g. 2024-25")
    parser.add_argument("--commit", required=True, help="40-character archive commit SHA")
    parser.add_argument(
        "--gameweeks",
        default="1-38",
        help="gameweek selection such as 1-38 or 1,2,7 (default: 1-38)",
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


def _resolve_available_at(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError("--data-available-at must carry a UTC offset")
    return parsed.astimezone(UTC)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    revision = VaastavRevision(commit_sha=args.commit, season=args.season)
    gameweeks = parse_gameweeks(args.gameweeks)
    data_available_at = _resolve_available_at(args.data_available_at)

    credentials = SupabaseCredentials.from_env(os.environ)

    with (
        SupabaseRestClient(credentials) as client,
        httpx.Client(timeout=60.0, follow_redirects=True) as http,
    ):
        recorder = open_run(
            client,
            workflow_name=WORKFLOW_NAME,
            parts={
                "season": revision.season,
                "commit": revision.commit_sha,
                "gameweeks": args.gameweeks,
            },
        )
        with recorder as run:
            ingest = HistoricalIngest(client=client, fetcher=ArchiveFetcher(http))
            result = ingest.ingest_season(
                revision,
                gameweeks=gameweeks,
                data_available_at=data_available_at,
            )
            run.record_rows("teams", result.teams)
            run.record_rows("elements", result.elements)
            run.record_rows("fixtures", result.fixtures)
            run.record_rows("element_gameweek_stats", result.total_stat_rows)

    print(
        f"{result.season}: {result.teams} teams, {result.elements} elements, "
        f"{result.fixtures} fixtures, {result.total_stat_rows} gameweek rows "
        f"across {len(result.gameweeks)} gameweeks"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
