"""Annotate a captured portfolio with realised FPL points for each element.

The sidecar is a fact-of-record: what every held element scored, as FPL
published it, attached to the cohort snapshot from the same gameweek. It feeds
performance analysis (how did the FPL500 do?) and the thesis-agreement scorer
(did their captain choice pay off?).

A fact of record has to be final, and the live endpoint answers all week. It
answers while the match is being played, and it answers again after bonus lands
with different numbers. So the round is asked about first: every fixture FPL
lists for the event must carry `finished`, which it sets once the bonus for that
match is confirmed. Until then this writes nothing and says why, and the next
run asks again. That is also why the event is optional -- a round finishes days
after the deadline that triggered its capture, so the job that runs regularly
sweeps every captured week that has no sidecar yet rather than only the newest.

Nothing here touches the portfolio file itself. Points are evidence after the
fact; the portfolio records intent before the deadline.

Usage:
    python -m fpl_andres.cli.annotate_portfolio
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
from typing import Any

from fpl_andres import cliargs, timeouts
from fpl_andres.jsonio import parse_json, read_json_file

LIVE = "https://fantasy.premierleague.com/api/event/{event}/live/"
FIXTURES = "https://fantasy.premierleague.com/api/fixtures/?event={event}"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
DEFAULT_PORTFOLIO_DIR = Path("data/cohort/portfolio")

SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="annotate-portfolio")
    parser.add_argument(
        "--event",
        type=cliargs.positive_int,
        default=None,
        help=(
            "Annotate this gameweek and report a refusal as an error. "
            "Omit it to sweep every captured week that has no sidecar yet, "
            "which is what the scheduled job does."
        ),
    )
    parser.add_argument("--portfolio-dir", type=Path, default=DEFAULT_PORTFOLIO_DIR)
    return parser


def _get_json(url: str) -> object | None:
    """Fetch and parse, or None when FPL cannot be reached.

    Unreachable and unfinished are different facts, but they lead to the same
    decision here: do not write, and ask again next run.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
            parsed: object = parse_json(response.read().decode("utf-8"), source=url)
    except OSError:
        return None
    return parsed


def _fetch_fixtures(event: int) -> list[Mapping[str, Any]] | None:
    """Every fixture FPL currently assigns to this gameweek.

    None when the endpoint could not be read. An empty list is a different
    answer: FPL was reached and lists no fixtures for the round.
    """
    payload = _get_json(FIXTURES.format(event=event))
    if not isinstance(payload, list):
        return None
    return [row for row in payload if isinstance(row, Mapping)]


def round_is_complete(fixtures: Sequence[Mapping[str, Any]]) -> bool:
    """True once every fixture in the round has its confirmed final score.

    FPL sets `finished_provisional` at full time and `finished` once the bonus
    for that match is confirmed. Between the two, three points per match are
    still to be handed out, so `finished` is the flag that means the round has
    stopped moving.

    A round with no fixtures is not complete. `all([])` is True, and an empty
    list here means the fixture list has not been published rather than that
    nothing needs to be played.
    """
    if not fixtures:
        return False
    return all(bool(fixture.get("finished")) for fixture in fixtures)


def captured_events(portfolio_dir: Path) -> list[int]:
    """Gameweeks with a capture, oldest first.

    The sidecar this command writes is `gwNN-points.json`, which matches the
    same glob as the capture it describes. The digit check is what keeps it
    from being read back as a gameweek of its own.
    """
    if not portfolio_dir.exists():
        return []
    return sorted(
        int(stem)
        for path in portfolio_dir.glob("gw*.json")
        if (stem := path.stem.removeprefix("gw")).isdigit()
    )


def _fetch_live(event: int) -> dict[int, int]:
    """Return total_points keyed by element id for a scored gameweek.

    Returns an empty dict when FPL has not published the gameweek yet, or when
    the endpoint is unreachable. The caller decides whether empty is an error.
    """
    payload = _get_json(LIVE.format(event=event))
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
    """Write the sidecar for a finished round, or write nothing.

    Returns the points mapping, or None when the portfolio file does not exist,
    the round has not finished, or the live endpoint has no data. The round is
    checked before the points are fetched: reading them earlier would record a
    scoreline that is still changing.
    """
    portfolio_path = _portfolio_path(portfolio_dir, event)
    if not portfolio_path.exists():
        return None

    fixtures = _fetch_fixtures(event)
    if fixtures is None or not round_is_complete(fixtures):
        return None

    portfolio = read_json_file(portfolio_path)
    element_ids = {int(holding["elementId"]) for holding in portfolio.get("holdings", [])}

    points = _fetch_live(event)
    if not points:
        return None

    # Restrict to elements the cohort held, so the sidecar is bounded in size
    # and tightly coupled to the portfolio it describes.
    held_points = {
        element_id: points[element_id] for element_id in element_ids if element_id in points
    }

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


def _annotate_one(event: int, portfolio_dir: Path) -> bool:
    """Annotate one gameweek, reporting what happened. True when it wrote."""
    result = annotate(event, portfolio_dir)
    if result is not None:
        output_path = _output_path(portfolio_dir, event)
        print(f"wrote {output_path} — {len(result)} elements annotated for gameweek {event}")
        return True

    portfolio_path = _portfolio_path(portfolio_dir, event)
    if not portfolio_path.exists():
        print(
            f"No portfolio at {portfolio_path}. Run capture_cohort_picks --event {event} first.",
            file=sys.stderr,
        )
        return False

    fixtures = _fetch_fixtures(event)
    if fixtures is None:
        print(f"Could not read the fixture list for gameweek {event}.", file=sys.stderr)
        return False
    if not round_is_complete(fixtures):
        unfinished = sum(1 for fixture in fixtures if not fixture.get("finished"))
        print(
            f"Gameweek {event} is still in play: {unfinished} of {len(fixtures)} "
            f"fixtures have no confirmed score. Nothing written.",
            file=sys.stderr,
        )
        return False

    print(
        f"FPL has not published scores for gameweek {event} yet; nothing written.",
        file=sys.stderr,
    )
    return False


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.event is not None:
        return 0 if _annotate_one(args.event, args.portfolio_dir) else 1

    # The sweep. A round still in play is the expected answer on most days, so
    # it is reported and not failed: a job that goes red every day until the
    # weekend ends is a job whose red means nothing.
    pending = [
        event
        for event in captured_events(args.portfolio_dir)
        if not _output_path(args.portfolio_dir, event).exists()
    ]
    if not pending:
        print("Every captured gameweek already carries its points sidecar.")
        return 0

    written = [event for event in pending if _annotate_one(event, args.portfolio_dir)]
    print(
        f"annotated {len(written)} of {len(pending)} gameweeks awaiting a sidecar"
        + (f": {', '.join(str(event) for event in written)}" if written else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
