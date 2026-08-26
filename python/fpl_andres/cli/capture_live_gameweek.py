"""Capture one completed FPL gameweek as immutable public evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_andres import cliargs, timeouts
from fpl_andres.cli.annotate_portfolio import USER_AGENT, _fetch_fixtures, round_is_complete
from fpl_andres.jsonio import parse_json, read_json_file

LIVE = "https://fantasy.premierleague.com/api/event/{event}/live/"
SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capture-live-gameweek")
    parser.add_argument("--event", type=cliargs.positive_int, default=None)
    parser.add_argument("--season", required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--deadlines",
        type=Path,
        default=Path("apps/web/src/data/deadlines.json"),
    )
    return parser


def _get_bytes(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
            return bytes(response.read())
    except OSError:
        return None


def build_snapshot(
    raw: bytes,
    *,
    season: str,
    event: int,
    captured_at: datetime,
) -> dict[str, Any]:
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("season must look like 2026-27")
    if not 1 <= event <= 38:
        raise ValueError("event must be in the FPL gameweek range")
    if captured_at.tzinfo is None:
        raise ValueError("capture time must carry a timezone")
    payload = parse_json(raw.decode("utf-8"), source=LIVE.format(event=event))
    if not isinstance(payload, Mapping):
        raise ValueError("the live gameweek was not an object")
    elements = payload.get("elements")
    if not isinstance(elements, list) or not elements:
        raise ValueError("the live gameweek published no elements")
    if any(not isinstance(row, Mapping) for row in elements):
        raise ValueError("the live gameweek contains a malformed element row")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "season": season,
        "event": event,
        "capturedAt": captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "source": LIVE.format(event=event),
        "sourceHash": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        "roundComplete": True,
        "elements": elements,
    }


def capture(event: int, season: str, output: Path) -> bool:
    if output.exists():
        return False
    fixtures = _fetch_fixtures(event)
    if fixtures is None or not round_is_complete(fixtures):
        return False
    raw = _get_bytes(LIVE.format(event=event))
    if raw is None:
        return False
    snapshot = build_snapshot(raw, season=season, event=event, captured_at=datetime.now(UTC))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return True


def finished_events(deadlines_path: Path) -> list[int]:
    payload = read_json_file(deadlines_path)
    rows = payload.get("deadlines") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("deadline ledger published no deadlines")
    return sorted(
        int(row["event"])
        for row in rows
        if isinstance(row, Mapping)
        and isinstance(row.get("event"), int)
        and row.get("finished") is True
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output is not None and args.event is None:
        print("--output requires --event", file=sys.stderr)
        return 1
    events = [args.event] if args.event is not None else finished_events(args.deadlines)
    for event in events:
        output = args.output or Path("data/live") / args.season / f"gw{event:02d}.json"
        if not capture(event, args.season, output):
            print(
                f"kept {output} unchanged; the round is unfinished, unreadable, or already captured"
            )
            continue
        print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
