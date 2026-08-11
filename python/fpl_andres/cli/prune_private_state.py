"""Delete manager request data once its short operational life ends.

Analysis diagnostics live for at most thirty days. A declared transfer lives
until seven days after its published gameweek deadline, also capped at thirty
days. Deadlines come from the committed season plan rather than from a guessed
calendar or a timestamp supplied by the browser.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from fpl_andres import cliargs
from fpl_andres.jsonio import read_json_file
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient

DEFAULT_PLAN = Path("apps/web/src/data/season-plan.json")
ANALYSIS_RETENTION = timedelta(days=30)
TRANSFER_GRACE = timedelta(days=7)
MAX_DELETE_ROWS = 1_000


class DeleteClient(Protocol):
    def count(self, table: str, *, filters: Mapping[str, str]) -> int: ...

    def delete(self, table: str, *, filters: Mapping[str, str]) -> None: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prune-private-state")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument(
        "--max-delete",
        type=cliargs.positive_int,
        default=MAX_DELETE_ROWS,
        help="Refuse the whole run if any one delete would exceed this many rows.",
    )
    return parser


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _retired_events(plan: Mapping[str, Any], now: datetime) -> tuple[str, list[int]]:
    season = plan.get("season")
    gameweeks = plan.get("gameweeks")
    if not isinstance(season, str) or not isinstance(gameweeks, list):
        raise ValueError("season plan must carry a season and gameweeks")

    retired: list[int] = []
    for index, raw in enumerate(gameweeks):
        if not isinstance(raw, Mapping):
            raise ValueError(f"season plan gameweek {index} is not an object")
        event = raw.get("event")
        deadline = raw.get("deadline")
        if not isinstance(event, int) or not isinstance(deadline, str):
            raise ValueError(f"season plan gameweek {index} lacks event or deadline")
        try:
            parsed = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"season plan gameweek {event} has an invalid deadline") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"season plan gameweek {event} deadline is not timezone-aware")
        if parsed + TRANSFER_GRACE < now:
            retired.append(event)
    return season, retired


def prune_private_state(
    client: DeleteClient,
    plan: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_delete_rows: int = MAX_DELETE_ROWS,
) -> dict[str, int]:
    at = now or datetime.now(UTC)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("retention time must be timezone-aware")
    cutoff = _timestamp(at - ANALYSIS_RETENTION)
    season, retired = _retired_events(plan, at)

    operations: list[tuple[str, str, dict[str, str]]] = [
        (
            "analysis requests older than 30 days",
            "analysis_requests",
            {"requested_at": f"lt.{cutoff}"},
        ),
        (
            "declared transfers older than 30 days",
            "declared_transfers",
            {"declared_at": f"lt.{cutoff}"},
        ),
    ]
    if retired:
        events = ",".join(str(event) for event in retired)
        operations.append(
            (
                "declared transfers past deadline grace",
                "declared_transfers",
                {"season": f"eq.{season}", "event": f"in.({events})"},
            )
        )

    counts = {label: client.count(table, filters=filters) for label, table, filters in operations}
    oversized = {label: count for label, count in counts.items() if count > max_delete_rows}
    if oversized:
        detail = ", ".join(f"{label}: {count}" for label, count in oversized.items())
        raise RuntimeError(f"refusing retention run above {max_delete_rows} rows ({detail})")

    for _, table, filters in operations:
        client.delete(table, filters=filters)
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = read_json_file(args.plan)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{args.plan} must contain a JSON object")

    credentials = SupabaseCredentials.from_env(os.environ)
    with SupabaseRestClient(credentials) as client:
        counts = prune_private_state(
            client,
            payload,
            max_delete_rows=args.max_delete,
        )
    print("; ".join(f"{label}: {count}" for label, count in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
