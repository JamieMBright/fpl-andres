"""Pin the ranked FPL500 membership that existed around one deadline."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres import cliargs
from fpl_andres.cohorts.fpl500_membership import build_membership, write_membership
from fpl_andres.jsonio import parse_json, read_json_file

DEFAULT_SOURCE_PATH = "data/cohort/fpl500.json"
DEFAULT_DEADLINE_LEDGER = Path("apps/web/src/data/deadlines.json")
DEFAULT_OUTPUT_DIR = Path("data/cohort/fpl500-membership")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pin-fpl500-membership")
    parser.add_argument("--event", type=cliargs.positive_int, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-path", default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--deadline-ledger", type=Path, default=DEFAULT_DEADLINE_LEDGER)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def _git_source(revision: str, path: str) -> tuple[str, Mapping[str, object]]:
    resolved = subprocess.run(
        ["git", "rev-parse", f"{revision}^{{commit}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    shown = subprocess.run(
        ["git", "show", f"{resolved}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    parsed = parse_json(shown, source=f"{resolved}:{path}")
    if not isinstance(parsed, Mapping):
        raise ValueError(f"{resolved}:{path} is not a JSON object")
    return resolved, parsed


def _deadline(path: Path, event: int) -> datetime:
    raw = read_json_file(path)
    rows = raw.get("deadlines") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{path} contains no deadline ledger")
    for row in rows:
        if not isinstance(row, Mapping) or row.get("event") != event:
            continue
        value = row.get("deadline")
        if not isinstance(value, str):
            break
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError(f"gameweek {event} deadline has no timezone in {path}")
        return parsed
    raise ValueError(f"gameweek {event} has no deadline in {path}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_commit, source = _git_source(args.source_commit, args.source_path)
    membership = build_membership(
        source,
        event=args.event,
        deadline=_deadline(args.deadline_ledger, args.event),
        source_commit=source_commit,
        source_path=args.source_path,
        pinned_at=datetime.now(UTC),
    )
    output = args.output or DEFAULT_OUTPUT_DIR / f"gw{args.event:02d}.json"
    write_membership(membership, output)
    print(
        f"wrote {output} — {membership.size} managers from {source_commit[:7]}, "
        f"{membership.source_timing} by {abs(membership.seconds_from_deadline)} seconds"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
