"""Sweep every FPL entry id and catalogue the managers worth following.

Deliberately conservative. This puts millions of requests on somebody else's
service, so it self-throttles well below what the server will tolerate, backs
off hard when told to, and stops entirely rather than hammering through a wall
of 429s. It checkpoints every block so a sixteen-hour run survives a crash and
resumes where it stopped instead of starting again.

Usage:
    python -m fpl_andres.cli.sweep_managers --rate 25 --until 2400000
    python -m fpl_andres.cli.sweep_managers --resume
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fpl_andres.cohorts.sweep import CohortRule, parse_history, qualifies

HISTORY_URL = "https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
OUTPUT_DIR = Path("data/cohort")
# Written every block so a long run is never repeated from the start.
CHECKPOINT = OUTPUT_DIR / "sweep-checkpoint.json"
RESULTS = OUTPUT_DIR / "managers.jsonl"
BLOCK = 2_000
# Consecutive rejections that mean stop rather than push on.
REFUSAL_LIMIT = 25


@dataclass
class Progress:
    next_id: int
    with_history: int = 0
    qualifying: int = 0
    missing: int = 0
    errors: int = 0


class Throttle:
    """A plain rate limiter. One shared clock, no bursts."""

    def __init__(self, per_second: float) -> None:
        self._interval = 1.0 / per_second
        self._next = time.monotonic()
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self._interval


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sweep-managers")
    parser.add_argument("--rate", type=float, default=25.0, help="requests a second")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--until", type=int, default=2_500_000)
    parser.add_argument("--since-start-year", type=int, default=2021)
    parser.add_argument("--rank-ceiling", type=int, default=10_000)
    parser.add_argument("--minimum-seasons", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    return parser


def _load_progress(start: int, resume: bool) -> Progress:
    if resume and CHECKPOINT.exists():
        saved = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        return Progress(**saved)
    return Progress(next_id=start)


def _save_progress(progress: Progress) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(progress.__dict__, indent=2), encoding="utf-8")


class Refused(RuntimeError):
    """Raised when FPL has told us to stop often enough that we should."""


async def _fetch(
    client: httpx.AsyncClient,
    throttle: Throttle,
    entry_id: int,
    refusals: list[int],
) -> tuple[int, dict[str, object] | None, str]:
    await throttle.wait()
    try:
        response = await client.get(HISTORY_URL.format(entry_id=entry_id))
    except httpx.HTTPError:
        return entry_id, None, "error"

    if response.status_code == 404:
        return entry_id, None, "missing"
    if response.status_code == 429 or response.status_code >= 500:
        refusals.append(entry_id)
        # Give the server room before anything else goes out.
        await asyncio.sleep(min(60.0, 2.0 * len(refusals)))
        return entry_id, None, "error"
    if response.status_code != 200:
        return entry_id, None, "error"

    refusals.clear()
    try:
        return entry_id, response.json(), "ok"
    except ValueError:
        return entry_id, None, "error"


async def run(args: argparse.Namespace) -> int:
    rule = CohortRule(
        since_start_year=args.since_start_year,
        rank_ceiling=args.rank_ceiling,
        minimum_qualifying_seasons=args.minimum_seasons,
    )
    progress = _load_progress(args.start, args.resume)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    throttle = Throttle(args.rate)
    semaphore = asyncio.Semaphore(args.concurrency)
    refusals: list[int] = []

    print(
        f"sweeping {progress.next_id:,} to {args.until:,} at {args.rate:g}/s, "
        f"keeping {rule.minimum_qualifying_seasons}+ finishes inside "
        f"{rule.rank_ceiling:,} since {rule.since_start_year}"
    )
    started = time.monotonic()

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(20.0, connect=8.0),
        follow_redirects=True,
    ) as client:
        with RESULTS.open("a", encoding="utf-8") as sink:
            while progress.next_id <= args.until:
                stop = min(progress.next_id + BLOCK, args.until + 1)
                block = range(progress.next_id, stop)

                async def one(
                    entry_id: int,
                ) -> tuple[int, dict[str, object] | None, str]:
                    async with semaphore:
                        return await _fetch(client, throttle, entry_id, refusals)

                for entry_id, payload, outcome in await asyncio.gather(
                    *(one(entry_id) for entry_id in block)
                ):
                    if outcome == "missing":
                        progress.missing += 1
                        continue
                    if outcome == "error" or payload is None:
                        progress.errors += 1
                        continue
                    record = parse_history(entry_id, payload)
                    if record is None:
                        continue
                    progress.with_history += 1
                    if not qualifies(record, rule):
                        continue
                    progress.qualifying += 1
                    sink.write(
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
                sink.flush()

                progress.next_id = stop
                _save_progress(progress)
                elapsed = time.monotonic() - started
                done = progress.next_id - args.start
                rate = done / elapsed if elapsed else 0.0
                remaining = (args.until - progress.next_id) / rate if rate else 0.0
                print(
                    f"  {progress.next_id:>9,}  found {progress.qualifying:>6,}"
                    f"  history {progress.with_history:>8,}"
                    f"  gaps {progress.missing:>8,}"
                    f"  {rate:5.1f}/s  {remaining / 3600:5.1f}h left",
                    flush=True,
                )

                if len(refusals) >= REFUSAL_LIMIT:
                    raise Refused(
                        f"FPL refused {len(refusals)} requests in a row; stopping at "
                        f"{progress.next_id:,}. Resume with --resume once it is happy."
                    )

    print(f"\ndone. {progress.qualifying:,} managers written to {RESULTS}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except Refused as error:
        print(f"\n{error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nstopped; rerun with --resume", file=sys.stderr)
        return 130


if __name__ == "__main__":
    print(f"started {datetime.now(UTC).isoformat()}")
    sys.exit(main())
