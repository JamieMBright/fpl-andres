"""Harvest this season's elite from the Overall league, and learn their history.

Two hundred requests for the top ten thousand, against thirteen million for a
pass of every entry id. See `cohorts/league.py` for why both exist.

Writes two things:

* `data/cohort/fpl100.json` -- the current season's standings down to the rank
  ceiling, which is the only honest answer to "who is good *this* year".
* new rows in `data/cohort/managers.jsonl` -- one history per entry id the
  catalogue has not seen. Past seasons never change, so a manager is fetched
  once and never again, which is what keeps later runs cheap.

Usage:
    python -m fpl_andres.cli.harvest_league
    python -m fpl_andres.cli.harvest_league --rank-ceiling 100 --skip-histories

Nothing here reads a private endpoint. Every entry id, name and rank on the
Overall league is public.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fpl_andres import cliargs, timeouts
from fpl_andres.cohorts.league import (
    OVERALL_LEAGUE,
    PAGE_SIZE,
    StandingRow,
    pages_for,
    parse_standings,
    unseen,
)
from fpl_andres.cohorts.sweep import parse_history
from fpl_andres.jsonio import parse_json
from fpl_andres.timeouts import client_timeout

STANDINGS_URL = (
    "https://fantasy.premierleague.com/api/leagues-classic/"
    f"{OVERALL_LEAGUE}/standings/?page_standings={{page}}"
)
HISTORY_URL = "https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
OUTPUT_DIR = Path("data/cohort")
STANDINGS = OUTPUT_DIR / "fpl100.json"
RESULTS = OUTPUT_DIR / "managers.jsonl"
SCHEMA_VERSION = 1

#: How many of the standings to keep. Ten thousand is the bar the cohort rule
#: already uses, so harvesting to it means the page and the rule agree.
DEFAULT_RANK_CEILING = 10_000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harvest-league")
    parser.add_argument(
        "--rank-ceiling",
        type=cliargs.positive_int,
        default=DEFAULT_RANK_CEILING,
        help=f"How far down the Overall league to read. Default {DEFAULT_RANK_CEILING}.",
    )
    parser.add_argument(
        "--rate", type=cliargs.positive_float, default=8.0, help="requests a second"
    )
    parser.add_argument("--standings", default=str(STANDINGS))
    parser.add_argument("--results", default=str(RESULTS))
    parser.add_argument(
        "--skip-histories",
        action="store_true",
        help="Read the standings only. Cheap, and enough to publish FPL100.",
    )
    parser.add_argument(
        "--max-histories",
        type=cliargs.positive_int,
        default=2_000,
        help="Bound one run's history fetches so a scheduled job is bounded.",
    )
    return parser


def _known(path: Path) -> frozenset[int]:
    if not path.exists():
        return frozenset()
    seen: set[int] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = parse_json(line, source=f"{path}:{number}")
        if isinstance(row, dict) and isinstance(row.get("entryId"), int):
            seen.add(int(row["entryId"]))
    return frozenset(seen)


async def _standings(
    client: httpx.AsyncClient,
    rank_ceiling: int,
    rate: float,
) -> list[StandingRow]:
    """Page the Overall league to the ceiling, in order, one page at a time.

    Sequential on purpose. Paging is a hundredth of the work a full sweep is,
    and a league page is a heavier query for FPL to answer than a single entry
    history; there is nothing to gain by asking for several at once.
    """
    rows: list[StandingRow] = []
    interval = 1.0 / rate
    for page in range(1, pages_for(rank_ceiling) + 1):
        response = await client.get(STANDINGS_URL.format(page=page))
        response.raise_for_status()
        parsed = parse_standings(response.json())
        if parsed is None:
            raise SystemExit(f"page {page} of the Overall league was not a standings payload")
        rows.extend(row for row in parsed.rows if row.rank <= rank_ceiling)
        if not parsed.has_next:
            break
        await asyncio.sleep(interval)
    return rows


async def _histories(
    client: httpx.AsyncClient,
    ids: Sequence[int],
    rate: float,
    results: Path,
) -> tuple[int, int]:
    """One history per id, appended as they arrive. Returns kept and missing."""
    kept = 0
    missing = 0
    interval = 1.0 / rate
    results.parent.mkdir(parents=True, exist_ok=True)
    with results.open("a", encoding="utf-8") as handle:
        for entry_id in ids:
            try:
                response = await client.get(HISTORY_URL.format(entry_id=entry_id))
            except httpx.HTTPError:
                missing += 1
                await asyncio.sleep(interval)
                continue
            if response.status_code != 200:
                missing += 1
                await asyncio.sleep(interval)
                continue
            record = parse_history(entry_id, response.json())
            if record is not None:
                handle.write(
                    json.dumps(
                        {
                            "entryId": record.entry_id,
                            "seasons": [
                                {
                                    "season": season.season,
                                    "points": season.points,
                                    "rank": season.rank,
                                    "percentile": season.percentile,
                                }
                                for season in record.seasons
                            ],
                        }
                    )
                    + "\n"
                )
                kept += 1
            else:
                missing += 1
            await asyncio.sleep(interval)
    return kept, missing


async def run(args: argparse.Namespace) -> int:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=client_timeout(timeouts.FPL_API),
        follow_redirects=True,
    ) as client:
        rows = await _standings(client, args.rank_ceiling, args.rate)
        print(f"Overall league: {len(rows)} entries down to rank {args.rank_ceiling}")

        standings = Path(args.standings)
        standings.parent.mkdir(parents=True, exist_ok=True)
        standings.write_text(
            json.dumps(
                {
                    "schemaVersion": SCHEMA_VERSION,
                    "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "league": OVERALL_LEAGUE,
                    "rankCeiling": args.rank_ceiling,
                    "pageSize": PAGE_SIZE,
                    "size": len(rows),
                    "managers": [
                        {"rank": row.rank, "entryId": row.entry_id, "total": row.total}
                        for row in rows
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {standings}")

        if args.skip_histories or not rows:
            # Between seasons there are no standings, which is not a fault.
            if not rows:
                print("the Overall league has no standings yet; the season has not started")
            return 0

        results = Path(args.results)
        fresh = unseen(rows, _known(results))[: args.max_histories]
        if not fresh:
            print("every entry in the standings is already in the catalogue")
            return 0
        kept, missing = await _histories(client, fresh, args.rate, results)
        print(f"fetched {len(fresh)} histories: {kept} catalogued, {missing} unreadable")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
