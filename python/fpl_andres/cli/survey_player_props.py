"""Catalogue every player-market source this project could use.

football-data.co.uk prices matches, and FPL scores players. Most of what FPL
pays for -- a goal, an assist, a save, a card -- is priced somewhere as a
player prop, but "somewhere" is not a data source. This CLI turns the guess
into a table: which providers exist, which answer, and the exact fields each
one returns.

It decides nothing. Choosing a source needs the column lists side by side, and
this produces them. Every probe is read-only and asks for the smallest response
that still names the fields.

Runs on a GitHub runner, never on the owner's machine: every price host fails
at the TLS handshake behind that network's gambling-category filter. A source
with no credential configured is reported as such and does not fail the run,
because "not signed up yet" is an answer, not a bug.

Usage:

    python -m fpl_andres.cli.survey_player_props
    python -m fpl_andres.cli.survey_player_props --source the-odds-api --json out.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fpl_andres.adapters.player_props import (
    PROP_SOURCES,
    ProbeResult,
    PropSource,
    source_by_key,
    survey,
)
from fpl_andres.timeouts import ODDS_FEED

#: How many field names to print per source before truncating the console
#: table. The JSON output always carries every one of them.
CONSOLE_FIELD_LIMIT = 400


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="survey-player-props")
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        metavar="KEY",
        help=(
            "Probe only this source. Repeatable. "
            f"Known: {', '.join(source.key for source in PROP_SOURCES)}."
        ),
    )
    parser.add_argument(
        "--json",
        default=None,
        metavar="PATH",
        help="Also write the full catalogue here, every field name included.",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=None,
        metavar="KEY",
        help=(
            "Exit non-zero unless this source answered. Use it to make a "
            "credential that stopped working visible instead of silent."
        ),
    )
    return parser


def _selected(keys: Sequence[str] | None) -> tuple[PropSource, ...]:
    if not keys:
        return PROP_SOURCES
    return tuple(source_by_key(key) for key in keys)


def _report(source: PropSource, result: ProbeResult) -> None:
    mark = {
        "ok": "ok      ",
        "no_credential": "no key  ",
        "unreachable": "blocked ",
        "refused": "refused ",
        "unreadable": "unread  ",
    }.get(result.status, result.status)
    print(f"\n{mark} {source.name}  <{source.homepage}>")
    print(f"         terms: {source.terms}")
    print(f"         covers: {', '.join(source.covers)}")
    print(f"         {result.note}")
    if result.markets:
        print(f"         {len(result.markets)} markets named:")
        for name in result.markets:
            print(f"           - {name}")
    if result.fields:
        shown = result.fields[:CONSOLE_FIELD_LIMIT]
        hidden = len(result.fields) - len(shown)
        print(f"         {len(result.fields)} fields:")
        for name in shown:
            print(f"           {name}")
        if hidden:
            print(f"           ... and {hidden} more, in the JSON output")


def _as_json(
    sources: Sequence[PropSource],
    results: Sequence[ProbeResult],
) -> dict[str, object]:
    return {
        "surveyedAt": datetime.now(UTC).isoformat(),
        "sources": [
            {
                "key": source.key,
                "name": source.name,
                "homepage": source.homepage,
                "terms": source.terms,
                "credentialEnv": list(source.credential_env),
                "covers": list(source.covers),
                "status": result.status,
                "note": result.note,
                "httpStatus": result.http_status,
                "markets": list(result.markets),
                "fields": list(result.fields),
            }
            for source, result in zip(sources, results, strict=True)
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    sources = _selected(args.source)

    with httpx.Client(timeout=ODDS_FEED, follow_redirects=True) as client:
        results = survey(client, sources)

    for source, result in zip(sources, results, strict=True):
        _report(source, result)

    answered = {result.key for result in results if result.ok}
    print(f"\n{len(answered)} of {len(results)} sources answered.")
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_as_json(sources, results), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Catalogue written to {path}")

    required = set(args.require or ())
    unknown = required - {source.key for source in sources}
    if unknown:
        print(f"\nrequired sources were not probed: {', '.join(sorted(unknown))}")
        return 1
    silent = required - answered
    if silent:
        print(f"\nrequired sources did not answer: {', '.join(sorted(silent))}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
