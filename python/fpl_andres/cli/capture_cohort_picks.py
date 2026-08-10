"""Capture the cohort's picks for one gameweek and reconcile them into a portfolio.

Run after a deadline. Picks are private until it passes, and this reads only
what FPL then makes public — the same endpoint the game's own "view team" link
uses.

Nothing here can be backfilled. FPL serves picks for the current season only:
probed on 2026-08-03, every gameweek of 2025/26 returned 404 for cohort members
whose season history is still published. The catalogue can say who was good for
ten years and cannot say what they owned last year. The portfolio therefore
starts empty and accumulates forward, one gameweek at a time, beginning with the
first deadline of the season.

Usage:
    python -m fpl_andres.cli.capture_cohort_picks --event 1
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

from fpl_andres import cliargs, timeouts
from fpl_andres.cli.sweep_managers import Throttle
from fpl_andres.cohorts.absence import DEFAULT_TOLERANCE, record_attempt
from fpl_andres.cohorts.portfolio import (
    CoverageTooLow,
    ManagerPicks,
    Pick,
    Portfolio,
    reconcile,
)
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.timeouts import client_timeout

PICKS_URL = "https://fantasy.premierleague.com/api/entry/{entry_id}/event/{event}/picks/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
COHORT_DIR = Path("data/cohort")
MANAGERS = COHORT_DIR / "managers.jsonl"
CHECKPOINT = COHORT_DIR / "sweep-checkpoint.json"
ABSENT = COHORT_DIR / "absent.json"
DEFAULT_OUTPUT = COHORT_DIR / "portfolio"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capture-cohort-picks")
    parser.add_argument("--event", type=cliargs.positive_int, required=True)
    parser.add_argument("--rate", type=cliargs.positive_float, default=25.0)
    parser.add_argument("--concurrency", type=cliargs.positive_int, default=8)
    parser.add_argument("--managers", default=str(MANAGERS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--absent", default=str(ABSENT))
    parser.add_argument(
        "--minimum-coverage",
        type=float,
        default=0.9,
        help="refuse to publish below this share of the cohort answering",
    )
    return parser


def _parse_picks(entry_id: int, event: int, payload: dict[str, object]) -> ManagerPicks:
    raw = payload.get("picks")
    if not isinstance(raw, list):
        raise ValueError(f"entry {entry_id} returned no picks for gameweek {event}")

    picks = tuple(
        Pick(
            element_id=int(row["element"]),
            position=int(row["position"]),
            multiplier=int(row["multiplier"]),
            is_captain=bool(row["is_captain"]),
            is_vice_captain=bool(row["is_vice_captain"]),
        )
        for row in raw
    )
    chip = payload.get("active_chip")
    return ManagerPicks(
        entry_id=entry_id,
        event=event,
        picks=picks,
        active_chip=None if chip is None else str(chip),
    )


async def _fetch(
    client: httpx.AsyncClient,
    throttle: Throttle,
    entry_id: int,
    event: int,
) -> ManagerPicks | None:
    await throttle.wait()
    try:
        response = await client.get(PICKS_URL.format(entry_id=entry_id, event=event))
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
        return _parse_picks(entry_id, event, payload)
    except (ValueError, KeyError, TypeError):
        return None


def _entry_ids(path: Path) -> list[int]:
    return [
        int(parse_json(line, source=f"{path}:{number}")["entryId"])
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip()
    ]


def _cohort_revision() -> str:
    """Which sweep this cohort came from, so a changed population is visible."""
    if not CHECKPOINT.exists():
        return "unknown"
    saved = read_json_file(CHECKPOINT)
    return f"swept-to-{saved.get('next_id', 'unknown')}"


def _write(portfolio: Portfolio, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"gw{portfolio.event:02d}.json"
    output.write_text(
        json.dumps(
            {
                "event": portfolio.event,
                "capturedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "cohortRevision": portfolio.cohort_revision,
                "attempted": portfolio.attempted,
                "responded": portfolio.responded,
                "counted": portfolio.counted,
                "freeHit": portfolio.free_hit,
                "coverage": round(portfolio.coverage, 4),
                "holdings": [
                    {
                        "elementId": holding.element_id,
                        "owned": holding.owned,
                        "started": holding.started,
                        "captained": holding.captained,
                        "viceCaptained": holding.vice_captained,
                        "ownedShare": round(holding.owned_share, 5),
                        "startedShare": round(holding.started_share, 5),
                        "captainedShare": round(holding.captained_share, 5),
                        "effectiveOwnership": round(holding.effective_ownership, 5),
                    }
                    for holding in portfolio.holdings
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def _read_absent(path: Path) -> dict[int, int]:
    if not path.exists():
        return {}
    saved = read_json_file(path)
    misses = saved.get("consecutiveMisses", {})
    if not isinstance(misses, dict):
        return {}
    return {int(entry): int(count) for entry, count in misses.items()}


def _write_absent(path: Path, ledger: dict[int, int], event: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "updatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "throughEvent": event,
                # Sorted so a diff shows who changed rather than the whole file.
                "consecutiveMisses": {str(entry): ledger[entry] for entry in sorted(ledger)},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


async def run(args: argparse.Namespace) -> int:
    managers = Path(args.managers)
    if not managers.exists():
        print(
            f"{managers} does not exist. Run sweep_managers first; the cohort is "
            f"the input to this job, not something it can infer.",
            file=sys.stderr,
        )
        return 1

    entry_ids = _entry_ids(managers)
    throttle = Throttle(args.rate)
    semaphore = asyncio.Semaphore(args.concurrency)
    print(f"reading gameweek {args.event} picks for {len(entry_ids):,} managers")

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=client_timeout(timeouts.FPL_API),
        follow_redirects=True,
    ) as client:

        async def one(entry_id: int) -> ManagerPicks | None:
            async with semaphore:
                return await _fetch(client, throttle, entry_id, args.event)

        results = await asyncio.gather(*(one(entry_id) for entry_id in entry_ids))

    captured = [row for row in results if row is not None]
    # Written before the coverage gate. A run that fails to publish still
    # learned who answered, and a cohort where too few answer is exactly the
    # run whose evidence about who is gone is worth keeping.
    absent = Path(args.absent)
    ledger = record_attempt(_read_absent(absent), entry_ids, (row.entry_id for row in captured))
    _write_absent(absent, ledger, args.event)
    settled = sum(1 for misses in ledger.values() if misses >= DEFAULT_TOLERANCE)
    print(
        f"{len(ledger):,} managers are mid-absence; "
        f"{settled:,} have missed {DEFAULT_TOLERANCE} and lose their place"
    )

    try:
        portfolio = reconcile(
            captured,
            event=args.event,
            attempted=len(entry_ids),
            cohort_revision=_cohort_revision(),
            minimum_coverage=args.minimum_coverage,
        )
    except CoverageTooLow as error:
        print(f"\n{error}", file=sys.stderr)
        return 2

    output = _write(portfolio, Path(args.output_dir))
    top = portfolio.holdings[:5]
    print(
        f"wrote {output} — {portfolio.counted:,} squads counted, "
        f"{portfolio.coverage:.1%} coverage, {portfolio.free_hit} on Free Hit"
    )
    for holding in top:
        print(
            f"  element {holding.element_id:>5}  "
            f"owned {holding.owned_share:6.1%}  EO {holding.effective_ownership:6.1%}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
