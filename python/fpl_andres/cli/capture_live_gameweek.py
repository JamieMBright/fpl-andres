"""Capture an FPL gameweek as public evidence, while it plays and once it ends.

A gameweek can span four days. Waiting for the last whistle to publish anything
means the site tells a manager nothing about the matches already played, so the
round being played is captured too and replaced as results land. The moment
every match is confirmed the snapshot is written settled and never touched
again: that frozen file is the evidence the projections rest on.
"""

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
    round_complete: bool,
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
        "roundComplete": round_complete,
        "elements": elements,
    }


def _existing(output: Path) -> Mapping[str, Any] | None:
    """The snapshot already on disk, or None when there is nothing replaceable.

    Bytes that will not parse are reported as settled rather than absent. The
    archive is the evidence every projection rests on, so anything unreadable
    is left alone instead of overwritten on the assumption it was ours.
    """
    if not output.exists():
        return None
    try:
        payload = read_json_file(output)
    except (OSError, ValueError):
        return {"roundComplete": True}
    return payload if isinstance(payload, Mapping) else {"roundComplete": True}


def _any_match_started(fixtures: Sequence[Mapping[str, Any]]) -> bool:
    return any(row.get("started") is True for row in fixtures)


def capture(event: int, season: str, output: Path) -> bool:
    existing = _existing(output)
    # A settled round never moves again, so it is written exactly once.
    if existing is not None and existing.get("roundComplete") is not False:
        return False
    fixtures = _fetch_fixtures(event)
    if fixtures is None:
        return False
    complete = round_is_complete(fixtures)
    # A round nobody has kicked off yet has nothing measured to publish.
    if not complete and not _any_match_started(fixtures):
        return False
    raw = _get_bytes(LIVE.format(event=event))
    if raw is None:
        return False
    # Polling every two hours must not commit an identical round every two
    # hours, so an unmoved payload is left where it is.
    if (
        existing is not None
        and existing.get("sourceHash") == f"sha256:{hashlib.sha256(raw).hexdigest()}"
    ):
        return False
    snapshot = build_snapshot(
        raw,
        season=season,
        event=event,
        captured_at=datetime.now(UTC),
        round_complete=complete,
    )
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
                f"kept {output} unchanged; the round is unstarted, unreadable, "
                "already settled, or has not moved since the last capture"
            )
            continue
        print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
