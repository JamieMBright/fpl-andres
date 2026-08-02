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
from typing import TypedDict

from fpl_andres.artifacts import (
    PROJECTIONS_META_SCHEMA_VERSION,
    PROJECTIONS_SCHEMA_VERSION,
)
from fpl_andres.backtesting.corpus import SeasonCorpus, load_season
from fpl_andres.backtesting.fixtures import estimate_strength
from fpl_andres.backtesting.projector import MatchProjection, project_next_match
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient
from fpl_andres.positions import Position

DEFAULT_OUTPUT = Path("apps/web/src/data/projections.json")
POSITION_CODES = {position.value: position.code for position in Position}
# Below this the shape statistics describe a cameo, not a season.
MINIMUM_APPEARANCES = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-projections")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


class ProjectionEntry(TypedDict):
    """One player's row in `projections.json`.

    Audit items #147 and #181. `_entry` returned `dict[str, object]`, so
    `entry["code"]` was an `object` and sorting by it needed
    `# type: ignore[arg-type,return-value]` -- which also silenced the check
    that would have caught the key being renamed.

    Named here rather than in the contracts package because this is a published
    artifact, not a boundary two languages agree on: the web app reads it
    through `apps/web/src/state/squad-projection.ts`, and the schema version in
    `artifacts.py` is what keeps the two in step.
    """

    code: int
    name: str
    position: str
    priceTenths: int | None
    expectedPoints: float
    expectedMinutes: float
    probabilityAppear: float
    probabilityStart: float
    appearances: int
    recentMinutes: int
    recentStarts: int
    recentMatches: int
    floor: float | None
    median: float | None
    ceiling: float | None
    returnRate: float | None
    blankRate: float | None
    evidence: str


def _entry(projection: MatchProjection) -> ProjectionEntry:
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
        # The closing stretch, which says what a player's role became rather
        # than what it averaged. A January arrival reads correctly here.
        "recentMinutes": projection.recent_minutes,
        "recentStarts": projection.recent_starts,
        "recentMatches": projection.recent_matches,
        # Shape is a description of what happened, so it is withheld rather
        # than smoothed when there is too little of it to describe.
        "floor": shape.floor if enough else None,
        "median": shape.median if enough else None,
        "ceiling": shape.ceiling if enough else None,
        "returnRate": round(shape.return_rate, 3) if enough else None,
        "blankRate": round(shape.blank_rate, 3) if enough else None,
        "evidence": projection.minutes.evidence_level,
    }


def _clubs(corpus: SeasonCorpus) -> list[dict[str, object]]:
    """Attack and defence multipliers per club, keyed by the permanent code.

    Club ids are reassigned every season exactly as player ids are, so the code
    is the only safe join. A club that was not in the division last season has
    no entry, and the site must show a blank rather than an average.
    """
    played = [
        fixture
        for event in sorted(corpus.fixtures_by_event)
        for fixture in corpus.fixtures_by_event[event]
    ]
    strength = estimate_strength(played)
    clubs: list[dict[str, object]] = []
    for team_id, measured in sorted(strength.items()):
        code = corpus.code_by_team.get(team_id)
        if code is None:
            continue
        clubs.append(
            {
                "code": code,
                "shortName": corpus.short_name_by_team.get(team_id, ""),
                "attackHome": round(measured.attack_home, 3),
                "attackAway": round(measured.attack_away, 3),
                "defenceHome": round(measured.defence_home, 3),
                "defenceAway": round(measured.defence_away, 3),
            }
        )
    return clubs


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
        key=lambda entry: entry["code"],
    )
    clubs = _clubs(corpus)
    artifact = {
        "schemaVersion": PROJECTIONS_SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(),
        "season": corpus.season,
        "throughGameweek": corpus.last_event,
        "basis": "next match against an average opponent, no fixture applied",
        "players": players,
        "clubs": clubs,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    # The header alone, so a component that only needs the season label does not
    # pull two hundred kilobytes of players into the first paint.
    meta = output.with_name(output.stem + "-meta.json")
    meta.write_text(
        json.dumps(
            {
                "schemaVersion": PROJECTIONS_META_SCHEMA_VERSION,
                **{
                    key: artifact[key]
                    for key in ("generatedAt", "season", "throughGameweek", "basis")
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output} ({len(players)} players, {len(clubs)} clubs)")
    print(f"wrote {meta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
