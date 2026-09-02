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
    PortfolioStructure,
    aggregate_manager_history,
    summarize_structure,
)
from fpl_andres.jsonio import read_json_file
from fpl_andres.positions import Position
from fpl_andres.timeouts import client_timeout

DEFAULT_MEMBERSHIP_DIR = Path("data/cohort/fpl500-membership")
DEFAULT_PORTFOLIO_DIR = Path("data/cohort/portfolio/fpl500")
DEFAULT_PLAYERS = Path("apps/web/public/fpl-global.json")
SCHEMA_VERSION = 2
STRUCTURE_SCHEMA_VERSION = 4
STANDING_SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capture-cohort-aggregate")
    parser.add_argument("--event", type=cliargs.positive_int, required=True)
    parser.add_argument("--membership", type=Path, default=None)
    parser.add_argument("--portfolio-dir", type=Path, default=DEFAULT_PORTFOLIO_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--structure-output", type=Path, default=None)
    parser.add_argument("--structure-supersedes", default=None)
    parser.add_argument("--structure-correction-reason", default=None)
    parser.add_argument("--standing-output", type=Path, default=None)
    parser.add_argument("--standing-supersedes", default=None)
    parser.add_argument("--standing-correction-reason", default=None)
    parser.add_argument("--players", type=Path, default=DEFAULT_PLAYERS)
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
                "seasonStanding": [
                    {
                        "overallRank": row.overall_rank,
                        "totalPoints": row.total_points,
                    }
                    for row in aggregate.season_standing
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_standing(
    aggregate: PortfolioAggregate,
    output: Path,
    *,
    captured_at: datetime | None = None,
    supersedes: str | None = None,
    correction_reason: str | None = None,
) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable standing {output}")
    if supersedes is None or correction_reason is None:
        raise ValueError("standing correction requires both supersedes and reason")
    timestamp = captured_at or datetime.now(UTC)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schemaVersion": STANDING_SCHEMA_VERSION,
                "event": aggregate.event,
                "capturedAt": timestamp.isoformat().replace("+00:00", "Z"),
                "basis": "ranked-500",
                "cohortRevision": aggregate.cohort_revision,
                "supersedes": supersedes,
                "correctionReason": correction_reason,
                "attempted": aggregate.attempted,
                "responded": aggregate.responded,
                "coverage": round(aggregate.coverage, 4),
                "seasonStanding": [
                    {
                        "overallRank": row.overall_rank,
                        "totalPoints": row.total_points,
                    }
                    for row in aggregate.season_standing
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_structure(
    structure: PortfolioStructure,
    output: Path,
    *,
    captured_at: datetime | None = None,
    supersedes: str | None = None,
    correction_reason: str | None = None,
) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable structure {output}")
    timestamp = captured_at or datetime.now(UTC)
    position_codes = {position.value: position.code for position in Position}
    output.parent.mkdir(parents=True, exist_ok=True)
    if (supersedes is None) != (correction_reason is None):
        raise ValueError("structure correction requires both supersedes and reason")
    payload = {
        "schemaVersion": STRUCTURE_SCHEMA_VERSION,
        "event": structure.event,
        "capturedAt": timestamp.isoformat().replace("+00:00", "Z"),
        "basis": "ranked-500",
        "cohortRevision": structure.cohort_revision,
        "attempted": structure.attempted,
        "responded": structure.responded,
        "coverage": round(structure.coverage, 4),
        "keeperPairings": [
            {
                "starterElementId": row.starter_element_id,
                "benchElementId": row.bench_element_id,
                "count": row.count,
                "share": round(row.share, 5),
            }
            for row in structure.keeper_pairings
        ],
        "commonStartingXi": {
            "method": "modal-formation-most-started",
            "formation": list(structure.formation),
            "elementIds": list(structure.common_starting_xi),
        },
        "positionalSpend": {
            position_codes[position]: _summary_payload(summary)
            for position, summary in structure.positional_spend.items()
        },
        "outfieldTrios": [
            {
                "position": position_codes[row.position],
                "elementIds": list(row.element_ids),
                "count": row.count,
                "share": round(row.share, 5),
            }
            for row in structure.outfield_trios
        ],
    }
    if structure.popularity_squad is not None:
        popularity = structure.popularity_squad
        payload["popularitySquad"] = {
            "method": "legal-aggregate-popularity",
            "squad": list(popularity.squad),
            "starters": list(popularity.starters),
            "bench": list(popularity.bench),
            "formation": list(popularity.formation),
            "spentTenths": popularity.spent_tenths,
            "xiSpentTenths": popularity.xi_spent_tenths,
            "bankTenths": 1000 - popularity.spent_tenths,
            "meanOwnership": round(popularity.mean_ownership, 5),
            "meanStartedShare": round(popularity.mean_started_share, 5),
        }
    if supersedes is not None and correction_reason is not None:
        payload.update(
            {
                "supersedes": supersedes,
                "correctionReason": correction_reason,
            }
        )
    output.write_text(
        json.dumps(
            payload,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _player_metadata(
    path: Path,
) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    raw = read_json_file(path)
    bootstrap = raw.get("bootstrap")
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("elements"), list):
        raise ValueError(f"player source has no bootstrap elements: {path}")
    elements = [row for row in bootstrap["elements"] if isinstance(row, dict)]
    return (
        {int(row["id"]): int(row["element_type"]) for row in elements},
        {int(row["id"]): int(row["now_cost"]) for row in elements},
        {int(row["id"]): int(row["team"]) for row in elements},
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
    structures = [row for row in results if row is not None]
    captured = [row for row in structures if row.history is not None]
    aggregate = aggregate_manager_history(
        captured,
        event=event,
        attempted=membership.size,
        cohort_revision=membership.membership_hash,
        minimum_coverage=args.minimum_coverage,
    )
    if args.standing_output is not None:
        if args.standing_output.exists():
            print(f"{args.standing_output} already exists; immutable standing retained")
            return 0
        write_standing(
            aggregate,
            args.standing_output,
            supersedes=args.standing_supersedes,
            correction_reason=args.standing_correction_reason,
        )
        print(
            f"wrote {args.standing_output} — "
            f"{len(aggregate.season_standing)} anonymous standings, "
            f"{aggregate.coverage:.1%} coverage"
        )
        return 0
    output = args.output or args.portfolio_dir / f"gw{event:02d}-aggregates.json"
    structure_output = args.structure_output or args.portfolio_dir / f"gw{event:02d}-structure.json"
    element_types, prices, team_ids = _player_metadata(args.players)
    structure = summarize_structure(
        structures,
        event=event,
        attempted=membership.size,
        cohort_revision=membership.membership_hash,
        element_types=element_types,
        team_ids=team_ids,
        prices=prices,
        minimum_coverage=args.minimum_coverage,
    )
    if output.exists():
        print(f"{output} already exists; immutable aggregate retained")
    else:
        write_aggregate(aggregate, output)
        print(
            f"wrote {output} — {aggregate.responded} of {aggregate.attempted} histories, "
            f"{aggregate.coverage:.1%} coverage"
        )
    if structure_output.exists():
        print(f"{structure_output} already exists; immutable structure retained")
    else:
        write_structure(
            structure,
            structure_output,
            supersedes=args.structure_supersedes,
            correction_reason=args.structure_correction_reason,
        )
        print(
            f"wrote {structure_output} — {len(structure.keeper_pairings)} keeper pairs, "
            f"{structure.coverage:.1%} coverage"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
