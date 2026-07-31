"""Verify a community list of FPL veterans against the official record.

The list is only ever a set of candidate entry ids. Every claim about a manager
is re-derived from FPL's own ``entry/{id}/history/`` response, so membership
rests on the official record rather than on the post that suggested the id.

Usage:
    python -m fpl_andres.cli.verify_veterans --source docs/design/fpl.html
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fpl_andres.adapters.fpl import FplClient
from fpl_andres.cohorts.veterans import (
    CohortCriteria,
    CohortError,
    ManagerRecord,
    extract_entry_ids,
    parse_history,
    qualifies,
    rank_cohort,
)

__all__ = ["build_parser", "main"]

# The API is public and unauthenticated; a pause keeps a bulk read polite.
_REQUEST_PAUSE_SECONDS = 0.4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verify-veterans")
    parser.add_argument("--source", required=True, help="File holding candidate entry ids")
    parser.add_argument("--elite-rank", type=int, default=10_000)
    parser.add_argument("--minimum-elite-seasons", type=int, default=3)
    parser.add_argument("--minimum-seasons", type=int, default=5)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--output", default=None)
    return parser


async def _fetch_records(entry_ids: Sequence[int]) -> tuple[list[ManagerRecord], list[str]]:
    records: list[ManagerRecord] = []
    problems: list[str] = []

    async with httpx.AsyncClient() as http:
        client = FplClient(http=http, clock=lambda: datetime.now(UTC))
        for index, entry_id in enumerate(entry_ids, start=1):
            try:
                fetched = await client.fetch_entry_history(entry_id)
                records.append(parse_history(entry_id, fetched.payload))
            except (CohortError, httpx.HTTPError) as error:
                problems.append(f"entry {entry_id}: {type(error).__name__}")
            if index % 10 == 0:
                print(f"  read {index}/{len(entry_ids)}", file=sys.stderr)
            await asyncio.sleep(_REQUEST_PAUSE_SECONDS)

    return records, problems


def _report_coverage(records: Sequence[ManagerRecord], elite_rank: int) -> None:
    """What the official record can and cannot support.

    A list of this kind is mostly reputation. Printing the distribution of best
    verifiable finishes makes the gap between claim and record visible, which is
    the entire reason for checking rather than trusting.
    """
    ranks = [record.best_rank for record in records if record.best_rank]
    if not ranks:
        return
    bands = (
        ("top 1k", 0, 1_000),
        ("1k to 10k", 1_000, 10_000),
        ("10k to 100k", 10_000, 100_000),
        ("never better than 100k", 100_000, 10**9),
    )
    print("\nbest finish the official record can confirm:")
    for label, low, high in bands:
        count = sum(1 for rank in ranks if low < rank <= high)
        print(f"  {label:<24}{count:>4} of {len(ranks)}")
    print(
        f"\nA rank threshold of {elite_rank:,} is not comparable across eras: the player\n"
        "base has grown roughly fivefold since 2010, so an equivalent finish today\n"
        "is several times harder. These counts are raw ranks, not percentiles."
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.source)
    if not source.exists():
        print(f"no such source: {source}", file=sys.stderr)
        return 1

    entry_ids = extract_entry_ids(
        source.read_text(encoding="utf-8", errors="replace"), limit=args.limit
    )
    if not entry_ids:
        print("no candidate entry ids found in the source", file=sys.stderr)
        return 1
    print(f"{len(entry_ids)} candidate ids; verifying against the official record")

    records, problems = asyncio.run(_fetch_records(entry_ids))
    criteria = CohortCriteria(
        elite_rank_threshold=args.elite_rank,
        minimum_elite_seasons=args.minimum_elite_seasons,
        minimum_seasons_played=args.minimum_seasons,
    )
    ranked = rank_cohort(records, criteria)
    rejected = [record for record in records if not qualifies(record, criteria)]

    print(
        f"\nverified {len(records)} of {len(entry_ids)} candidates; "
        f"{len(ranked)} qualify, {len(rejected)} rejected"
    )
    if problems:
        print(f"{len(problems)} could not be read: {', '.join(problems[:5])}")

    _report_coverage(records, args.elite_rank)

    print(f"\n{'entry':>10}{'seasons':>9}{'best':>8}{'elite':>7}  record")
    for record in ranked:
        finishes = ", ".join(f"{finish.season_name} {finish.rank:,}" for finish in record.recent(4))
        print(
            f"{record.entry_id:>10}{record.seasons_played:>9}"
            f"{record.best_rank or 0:>8,}{record.elite_seasons(args.elite_rank):>7}  {finishes}"
        )

    if args.output:
        Path(args.output).write_text(
            json.dumps(
                {
                    "generatedAt": datetime.now(UTC).isoformat(),
                    "criteria": {
                        "eliteRank": args.elite_rank,
                        "minimumEliteSeasons": args.minimum_elite_seasons,
                        "minimumSeasons": args.minimum_seasons,
                    },
                    "candidates": len(entry_ids),
                    "verified": len(records),
                    "qualified": [
                        {
                            "entryId": record.entry_id,
                            "seasonsPlayed": record.seasons_played,
                            "bestRank": record.best_rank,
                            "eliteSeasons": record.elite_seasons(args.elite_rank),
                        }
                        for record in ranked
                    ],
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
