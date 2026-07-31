"""Publish the per-player projection artifact the website reads.

Committed rather than served live, for the same reason the validation report is
committed: a projection is a claim tied to a commit. If the number on the page
changes, the diff says so.

Keyed by FPL player ``code``, which follows a footballer for life, because
element ids are reassigned every season and joining on them would silently
attach one player's history to another.

Usage:
    python -m fpl_andres.cli.publish_projections --season 2025-26
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres.backtesting.corpus import load_season
from fpl_andres.backtesting.projector import MatchProjection, project_next_match
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient

DEFAULT_OUTPUT = Path("apps/web/src/data/projections.json")
POSITION_CODES = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
# Below this the shape statistics describe a cameo, not a season.
MINIMUM_APPEARANCES = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-projections")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def _entry(projection: MatchProjection) -> dict[str, object]:
    shape = projection.shape
    enough = shape.appearances >= MINIMUM_APPEARANCES
    return {
        "code": projection.code,
        "name": projection.web_name,
        "position": POSITION_CODES[projection.position],
        "priceTenths": projection.price_tenths,
        "expectedPoints": round(projection.expected_points, 2),
        "expectedMinutes": round(projection.expected_minutes, 1),
        "probabilityAppear": round(projection.minutes.probability_appear, 3),
        "probabilityStart": round(projection.minutes.probability_sixty_minutes, 3),
        "appearances": shape.appearances,
        # Shape is a description of what happened, so it is withheld rather
        # than smoothed when there is too little of it to describe.
        "floor": shape.floor if enough else None,
        "median": shape.median if enough else None,
        "ceiling": shape.ceiling if enough else None,
        "returnRate": round(shape.return_rate, 3) if enough else None,
        "blankRate": round(shape.blank_rate, 3) if enough else None,
        "evidence": projection.minutes.evidence_level,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    credentials = SupabaseCredentials.from_env(os.environ)
    with SupabaseRestClient(credentials) as client:
        corpus = load_season(client, args.season)

    projections = project_next_match(corpus)
    if not projections:
        print(f"no projections for {args.season}", file=sys.stderr)
        return 1

    players = sorted(
        (_entry(projection) for projection in projections),
        key=lambda entry: entry["code"],  # type: ignore[arg-type,return-value]
    )
    artifact = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "season": corpus.season,
        "throughGameweek": corpus.last_event,
        "basis": "next match against an average opponent, no fixture applied",
        "players": players,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output} ({len(players)} players)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
