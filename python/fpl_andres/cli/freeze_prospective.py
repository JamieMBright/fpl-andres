"""Freeze the pre-deadline model revision, parameters and planning artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from fpl_andres.jsonio import read_json_file
from fpl_andres.prospective import build_prospective_manifest

DEFAULT_DEADLINES = Path("apps/web/src/data/deadlines.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="freeze-prospective")
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--event", type=int)
    parser.add_argument("--deadline")
    parser.add_argument("--deadlines", default=str(DEFAULT_DEADLINES))
    parser.add_argument("--frozen-at", required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output")
    return parser


def _event_and_deadline(
    path: Path,
    requested_event: int | None,
    requested_deadline: str | None,
) -> tuple[int, datetime]:
    payload = read_json_file(path)
    rows = payload.get("deadlines")
    if not isinstance(rows, list):
        raise ValueError(f"{path} publishes no deadlines list")
    selected = next(
        (
            row
            for row in rows
            if isinstance(row, dict) and (requested_event is None and row.get("finished") is False)
        ),
        None,
    )
    if requested_event is not None:
        selected = next(
            (row for row in rows if isinstance(row, dict) and row.get("event") == requested_event),
            None,
        )
    if selected is None:
        raise ValueError("no matching unfinished FPL event is published")
    if selected.get("finished") is not False:
        raise ValueError(f"gameweek {selected.get('event')} is already finished")

    event = int(selected["event"])
    deadline = datetime.fromisoformat(str(selected["deadline"]).replace("Z", "+00:00"))
    if requested_deadline is not None:
        supplied = datetime.fromisoformat(requested_deadline.replace("Z", "+00:00"))
        if supplied != deadline:
            raise ValueError(
                f"gameweek {event} deadline is {deadline.isoformat()}, not {supplied.isoformat()}"
            )
    return event, deadline


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        event, deadline = _event_and_deadline(
            Path(args.deadlines),
            args.event,
            args.deadline,
        )
    except (KeyError, TypeError, ValueError) as error:
        print(f"prospective event unavailable: {error}", file=sys.stderr)
        return 1
    output = Path(args.output or f"data/prospective/gw{event}-{args.season}.json")
    if output.exists():
        print(f"{output} is already frozen; leaving it unchanged")
        return 0
    payload = build_prospective_manifest(
        Path.cwd(),
        season=args.season,
        event=event,
        deadline=deadline,
        frozen_at=datetime.fromisoformat(args.frozen_at.replace("Z", "+00:00")),
        code_revision=args.code_revision,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
