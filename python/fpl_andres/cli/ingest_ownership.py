"""Recover ownership and price history backwards from the fplcache archive.

`crowd_snapshots` only collects forwards from the day it was switched on. This
walks the archive instead, which has been storing the bootstrap payload four
times a day for years.

Writes a JSONL series and reports what it could not read, rather than filling
gaps. A silently-zeroed ownership would be indistinguishable from a genuinely
unowned player.

Usage:
    python -m fpl_andres.cli.ingest_ownership --from 2026-07-25 --to 2026-07-31
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from fpl_andres import timeouts
from fpl_andres.adapters.fplcache import (
    FplCacheUnavailable,
    parse_snapshot,
    snapshot_directory,
    snapshot_url,
)
from fpl_andres.jsonio import parse_json

DEFAULT_OUTPUT = Path("data/ownership")
_LISTING = "https://api.github.com/repos/Randdalf/fplcache/contents/cache"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest-ownership")
    parser.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def _day(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _files_for(client: httpx.Client, day: datetime) -> list[str]:
    url = f"{_LISTING}/{snapshot_directory(day)}"
    response = client.get(url)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    listing = parse_json(response.text, source=url)
    return sorted(entry["name"] for entry in listing if entry["name"].endswith(".json.xz"))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start, end = _day(args.start), _day(args.end)
    if end < start:
        print("--to must not precede --from", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    series = output / f"ownership-{args.start}-to-{args.end}.jsonl"

    captured = 0
    refused: list[str] = []
    with (
        httpx.Client(timeout=timeouts.ARCHIVE_DOWNLOAD, follow_redirects=True) as client,
        series.open("w", encoding="utf-8") as sink,
    ):
        day = start
        while day <= end:
            for file_name in _files_for(client, day):
                url = snapshot_url(day, file_name)
                try:
                    payload = client.get(url)
                    payload.raise_for_status()
                    snapshot, rows = parse_snapshot(
                        payload.content, source_url=url, day=day, file_name=file_name
                    )
                except (httpx.HTTPError, FplCacheUnavailable) as error:
                    refused.append(f"{url}: {error}")
                    continue

                sink.write(
                    json.dumps(
                        {
                            "capturedAt": snapshot.captured_at.isoformat(),
                            "sourceUrl": snapshot.source_url,
                            "contentHash": snapshot.content_hash,
                            "elements": [
                                {
                                    "code": row.element_code,
                                    "elementId": row.element_id,
                                    "nowCostTenths": row.now_cost_tenths,
                                    "selectedByPercent": row.selected_by_percent,
                                    "transfersInEvent": row.transfers_in_event,
                                    "transfersOutEvent": row.transfers_out_event,
                                }
                                for row in rows
                            ],
                        }
                    )
                    + "\n"
                )
                captured += 1
                print(f"  {snapshot.captured_at.isoformat()}  {snapshot.element_count} elements")
            day += timedelta(days=1)

    print(f"\ncaptured {captured} snapshots into {series}")
    if refused:
        print(f"refused {len(refused)}:")
        for line in refused:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
