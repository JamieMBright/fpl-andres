"""Annotate a captured portfolio with realised FPL points for each element.

Run after the gameweek is scored. Reads the captured squad file for an event,
fetches the live endpoint for each player's total_points, and writes a sidecar
file alongside the portfolio.

The sidecar is a fact-of-record: what every held element scored, as FPL
published it, attached to the cohort snapshot from the same gameweek. It feeds
performance analysis (how did the FPL500 do?) and the thesis-agreement scorer
(did their captain choice pay off?).

Nothing here touches the portfolio file itself. Points are evidence after the
fact; the portfolio records intent before the deadline.

Usage:
    python -m fpl_andres.cli.annotate_portfolio --event 1
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres import cliargs, timeouts
from fpl_andres.jsonio import parse_json, read_json_file

LIVE = "https://fantasy.premierleague.com/api/event/{event}/live/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
DEFAULT_PORTFOLIO_DIR = Path("data/cohort/portfolio")

SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="annotate-portfolio")
    parser.add_argument("--event", type=cliargs.positive_int, required=True)
    parser.add_argument("--portfolio-dir", type=Path, default=DEFAULT_PORTFOLIO_DIR)
    return parser


def _fetch_live(event: int) -> dict[int, int]:
    """Return total_points keyed by element id for a scored gameweek.

    Returns an empty dict when FPL has not published the gameweek yet, or when
    the endpoint is unreachable. The caller decides whether empty is an error.
    """
    url = LIVE.format(event=event)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
            payload = parse_json(response.read().decode("utf-8"), source=url)
    except OSError:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    rows = payload.get("elements")
    if not isinstance(rows, list):
        return {}
    points: dict[int, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        element_id = row.get("id")
        stats = row.get("stats")
        if not isinstance(element_id, int) or not isinstance(stats, Mapping):
            continue
        total = stats.get("total_points")
        if isinstance(total, int):
            points[element_id] = total
    return points


def _portfolio_path(directory: Path, event: int) -> Path:
    return directory / f"gw{event:02d}.json"


def _output_path(directory: Path, event: int) -> Path:
    return directory / f"gw{event:02d}-points.json"


def annotate(event: int, portfolio_dir: Path) -> dict[int, int] | None:
    """Fetch live points for every element in the portfolio and write the sidecar.

    Returns the points mapping, or None when the portfolio file does not exist
    or the live endpoint has no data.
    """
    portfolio_path = _portfolio_path(portfolio_dir, event)
    if not portfolio_path.exists():
        return None

    portfolio = read_json_file(portfolio_path)
    element_ids = {int(holding["elementId"]) for holding in portfolio.get("holdings", [])}

    points = _fetch_live(event)
    if not points:
        return None

    # Restrict to elements the cohort held, so the sidecar is bounded in size
    # and tightly coupled to the portfolio it describes.
    held_points = {element_id: points[element_id] for element_id in element_ids if element_id in points}

    output_path = _output_path(portfolio_dir, event)
    output_path.write_text(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "event": event,
                "fetchedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "elementPoints": {str(k): v for k, v in sorted(held_points.items())},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return held_points


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = annotate(args.event, args.portfolio_dir)
    if result is None:
        portfolio_path = _portfolio_path(args.portfolio_dir, args.event)
        if not portfolio_path.exists():
            print(
                f"No portfolio at {portfolio_path}. "
                f"Run capture_cohort_picks --event {args.event} first.",
                file=sys.stderr,
            )
            return 1
        print(
            f"FPL has not published scores for gameweek {args.event} yet; "
            "nothing written.",
            file=sys.stderr,
        )
        return 1

    output_path = _output_path(args.portfolio_dir, args.event)
    covered = len(result)
    print(f"wrote {output_path} — {covered} elements annotated for gameweek {args.event}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
