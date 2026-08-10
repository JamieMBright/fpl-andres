"""Keep a list of this season's deadlines, so other jobs can ask cheaply.

One request to the bootstrap. Written so a workflow can answer "is today a
deadline day, and which gameweek" without fetching anything itself -- a
scheduled capture that runs six times a weekend should not pull a megabyte of
bootstrap five times to learn it has nothing to do.

Usage:
    python -m fpl_andres.cli.publish_deadlines
    python -m fpl_andres.cli.publish_deadlines --due-within 6h
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fpl_andres import timeouts
from fpl_andres.jsonio import parse_json

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
DEFAULT_OUTPUT = Path("data/cohort/deadlines.json")
SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-deadlines")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--due-within",
        type=float,
        default=None,
        metavar="HOURS",
        help=(
            "Print the gameweek whose deadline has passed within this many "
            "hours and exit 0, or print nothing and exit 1. This is the whole "
            "reason the file exists: a capture job asks, and stops early when "
            "the answer is nothing."
        ),
    )
    return parser


def _events(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise SystemExit("bootstrap was not an object")
    events = payload.get("events")
    if not isinstance(events, list):
        raise SystemExit("bootstrap published no events")
    rows: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        identifier = event.get("id")
        deadline = event.get("deadline_time")
        if not isinstance(identifier, int) or not isinstance(deadline, str):
            continue
        rows.append(
            {
                "event": identifier,
                "deadline": deadline,
                "finished": bool(event.get("finished")),
            }
        )
    return sorted(rows, key=lambda row: int(str(row["event"])))


def due_within(rows: Sequence[dict[str, object]], hours: float, now: datetime) -> int | None:
    """The gameweek whose deadline has just passed, if one has.

    Just passed, not about to: picks are private until the deadline and public
    after it, so a capture wants the window behind the most recent one rather
    than the window in front of the next.
    """
    window = timedelta(hours=hours)
    for row in reversed(rows):
        try:
            deadline = datetime.fromisoformat(str(row["deadline"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if now - window <= deadline <= now:
            return int(str(row["event"]))
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)

    if args.due_within is not None and output.exists():
        # Answering from the committed file rather than the network is the
        # point: this branch runs on every scheduled capture and almost always
        # says "nothing to do".
        saved = parse_json(output.read_text(encoding="utf-8"), source=str(output))
        assert isinstance(saved, dict)
        rows = saved.get("deadlines")
        assert isinstance(rows, list)
        event = due_within(rows, args.due_within, datetime.now(UTC))
        if event is None:
            print("no deadline in the window", file=sys.stderr)
            return 1
        print(event)
        return 0

    request = urllib.request.Request(BOOTSTRAP, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
        payload = parse_json(response.read().decode("utf-8"), source=BOOTSTRAP)
    rows = _events(payload)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "deadlines": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    upcoming = [row for row in rows if not row["finished"]]
    print(f"wrote {output} — {len(rows)} gameweeks, {len(upcoming)} still to play")
    if upcoming:
        print(f"  next: gameweek {upcoming[0]['event']} at {upcoming[0]['deadline']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
