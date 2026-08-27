"""Capture privacy-safe aggregate evidence for one pinned FPL500 event."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fpl_andres import cliargs, timeouts
from fpl_andres.cli.capture_cohort_picks import USER_AGENT, _fetch
from fpl_andres.cli.sweep_managers import Throttle
from fpl_andres.cohorts.fpl500_membership import read_membership
from fpl_andres.cohorts.portfolio import (
    DistributionSummary,
    ManagerPicks,
    PortfolioAggregate,
    aggregate_manager_history,
)
from fpl_andres.jsonio import read_json_file
from fpl_andres.timeouts import client_timeout

DEFAULT_MEMBERSHIP_DIR = Path("data/cohort/fpl500-membership")
DEFAULT_PORTFOLIO_DIR = Path("data/cohort/portfolio/fpl500")
SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capture-cohort-aggregate")
    parser.add_argument("--event", type=cliargs.positive_int, required=True)
    parser.add_argument("--membership", type=Path, default=None)
    parser.add_argument("--portfolio-dir", type=Path, default=DEFAULT_PORTFOLIO_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--rate", type=cliargs.positive_float, default=25.0)
    parser.add_argument("--concurrency", type=cliargs.positive_int, default=8)
    parser.add_argument("--minimum-coverage", type=float, default=0.9)
    return parser


def _summary_payload(summary: DistributionSummary) -> dict[str, int | float]:
    return {
        "mean": round(summary.mean, 4),
        "median": round(summary.median, 4),
        "p10": round(summary.p10, 4),
        "p90": round(summary.p90, 4),
        "minimum": summary.minimum,
        "maximum": summary.maximum,
    }


def write_aggregate(
    aggregate: PortfolioAggregate,
    output: Path,
    *,
    captured_at: datetime | None = None,
) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable aggregate {output}")
    timestamp = captured_at or datetime.now(UTC)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "event": aggregate.event,
                "capturedAt": timestamp.isoformat().replace("+00:00", "Z"),
                "basis": "ranked-500",
                "cohortRevision": aggregate.cohort_revision,
                "attempted": aggregate.attempted,
                "responded": aggregate.responded,
                "coverage": round(aggregate.coverage, 4),
                "chips": aggregate.chips,
                "totalPoints": _summary_payload(aggregate.total_points),
                "benchPoints": _summary_payload(aggregate.bench_points),
                "squadValueTenths": _summary_payload(aggregate.squad_value_tenths),
                "bankTenths": _summary_payload(aggregate.bank_tenths),
                "eventTransfers": _summary_payload(aggregate.event_transfers),
                "transferCost": _summary_payload(aggregate.transfer_cost),
                "transfersAvailable": aggregate.transfers_available,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


async def run(args: argparse.Namespace) -> int:
    event = int(args.event)
    membership_path = args.membership or DEFAULT_MEMBERSHIP_DIR / f"gw{event:02d}.json"
    membership = read_membership(membership_path)
    if membership.event != event:
        raise ValueError(f"membership belongs to gameweek {membership.event}, not {event}")
    portfolio_path = args.portfolio_dir / f"gw{event:02d}.json"
    portfolio = read_json_file(portfolio_path)
    if portfolio.get("cohortRevision") != membership.membership_hash:
        raise ValueError("portfolio and membership hashes do not agree")

    throttle = Throttle(args.rate)
    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=client_timeout(timeouts.FPL_API),
        follow_redirects=True,
    ) as client:

        async def one(entry_id: int) -> ManagerPicks | None:
            async with semaphore:
                return await _fetch(client, throttle, entry_id, event)

        results = await asyncio.gather(*(one(entry_id) for entry_id in membership.entry_ids))
    captured = [row for row in results if row is not None and row.history is not None]
    aggregate = aggregate_manager_history(
        captured,
        event=event,
        attempted=membership.size,
        cohort_revision=membership.membership_hash,
        minimum_coverage=args.minimum_coverage,
    )
    output = args.output or args.portfolio_dir / f"gw{event:02d}-aggregates.json"
    write_aggregate(aggregate, output)
    print(
        f"wrote {output} — {aggregate.responded} of {aggregate.attempted} histories, "
        f"{aggregate.coverage:.1%} coverage"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
