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
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast, get_args

from fpl_andres import timeouts
from fpl_andres.artifacts import (
    PROJECTIONS_META_SCHEMA_VERSION,
    PROJECTIONS_SCHEMA_VERSION,
)
from fpl_andres.backtesting.corpus import SeasonCorpus, load_season
from fpl_andres.backtesting.fixtures import (
    Fixture,
    TeamStrength,
    season_strength,
)
from fpl_andres.backtesting.projector import MatchProjection, project_next_match
from fpl_andres.backtesting.scoring import PointsBreakdown
from fpl_andres.bootstrap import BootstrapElement, parse_elements
from fpl_andres.jsonio import MalformedJsonError, parse_json
from fpl_andres.models.minutes import AvailabilityEvidence, AvailabilityStatus
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient
from fpl_andres.positions import Position

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
DEFAULT_OUTPUT = Path("apps/web/src/data/projections.json")
POSITION_CODES = {position.value: position.code for position in Position}
# Below this the shape statistics describe a cameo, not a season.
MINIMUM_APPEARANCES = 4
#: The same divisor `scoring.py` turns expected minutes into 90s with, so the
#: goals and assists published here multiply back to the attacking route it
#: priced rather than to a number near it.
MINUTES_PER_90 = 90.0
# Dixon-Coles fit. Half-weight at roughly a season's distance, so the fit leans
# on recent form without discarding the rest of the year.
DECAY_RATE_PER_DAY = 0.002
MINIMUM_MATCHES = 5
MAX_ITERATIONS = 200


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-projections")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


class RouteEntry(TypedDict):
    """What `expectedPoints` is made of, before the suspension derate.

    Published because a single number cannot be argued with. The parts also
    respond to a fixture differently -- a hard away tie suppresses clean sheets
    while raising saves -- so anything applying a fixture to a scalar is
    applying it to the wrong thing.
    """

    appearance: float
    attacking: float
    cleanSheet: float
    bonus: float
    saves: float
    conceding: float
    discipline: float
    defensiveContribution: float


class ProjectionEntry(TypedDict):
    """One player's row in `projections.json`.

    `_entry` returned `dict[str, object]`, so
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
    expectedCeiling: float
    ceilingRatio: float
    expectedMinutes: float
    # The two halves of the attacking route, in goals and assists rather than
    # points. `routes.attacking` prices them together and cannot be taken apart
    # again, which matters because a bookmaker quotes them separately: an
    # anytime-scorer price is evidence about one of these and says nothing about
    # the other. Per match, against an average opponent, like everything else here.
    expectedGoals: float
    expectedAssists: float
    probabilityAppear: float
    probabilityStart: float
    appearances: int
    recentMinutes: int
    recentStarts: int
    recentMatches: int
    yellowCards: int
    suspensionMultiplier: float
    routes: RouteEntry
    floor: float | None
    median: float | None
    ceiling: float | None
    returnRate: float | None
    blankRate: float | None
    evidence: str


def _routes(breakdown: PointsBreakdown) -> RouteEntry:
    return {
        "appearance": round(breakdown.appearance, 3),
        "attacking": round(breakdown.attacking, 3),
        "cleanSheet": round(breakdown.clean_sheet, 3),
        "bonus": round(breakdown.bonus, 3),
        "saves": round(breakdown.saves, 3),
        "conceding": round(breakdown.conceding, 3),
        "discipline": round(breakdown.discipline, 3),
        "defensiveContribution": round(breakdown.defensive_contribution, 3),
    }


def _entry(projection: MatchProjection) -> ProjectionEntry:
    shape = projection.shape
    enough = shape.appearances >= MINIMUM_APPEARANCES
    # The same 90s the breakdown scaled the rates by, so the published goals and
    # assists multiply back to the published attacking route exactly.
    nineties = projection.expected_minutes / MINUTES_PER_90
    return {
        "code": projection.code,
        "name": projection.web_name,
        "position": POSITION_CODES[projection.position],
        "priceTenths": projection.price_tenths,
        "expectedPoints": round(projection.expected_points, 2),
        # The same match on his best afternoon, and the multiple that produced
        # it. A chip or an armband is played for this number, not the mean.
        "expectedCeiling": round(projection.expected_ceiling, 2),
        "ceilingRatio": round(shape.ceiling_ratio, 3),
        "expectedMinutes": round(projection.expected_minutes, 1),
        # Three decimals because a fringe player's rate lives in the third one.
        "expectedGoals": round(nineties * projection.rates.goals_per_90, 3),
        "expectedAssists": round(nineties * projection.rates.assists_per_90, 3),
        "probabilityAppear": round(projection.minutes.probability_appear, 3),
        "probabilityStart": round(projection.minutes.probability_sixty_minutes, 3),
        "appearances": shape.appearances,
        # The closing stretch, which says what a player's role became rather
        # than what it averaged. A January arrival reads correctly here.
        "recentMinutes": projection.recent_minutes,
        "recentStarts": projection.recent_starts,
        "recentMatches": projection.recent_matches,
        # Already applied to expectedPoints; published so a reader can see why
        # a booked player is rated below his rate.
        "yellowCards": projection.yellow_cards,
        "suspensionMultiplier": round(projection.suspension_multiplier, 3),
        "routes": _routes(projection.breakdown),
        # Shape is a description of what happened, so it is withheld rather
        # than smoothed when there is too little of it to describe.
        "floor": shape.floor if enough else None,
        "median": shape.median if enough else None,
        "ceiling": shape.ceiling if enough else None,
        "returnRate": round(shape.return_rate, 3) if enough else None,
        "blankRate": round(shape.blank_rate, 3) if enough else None,
        "evidence": projection.minutes.evidence_level,
    }


def _strength(corpus: SeasonCorpus, played: Sequence[Fixture]) -> dict[int, TeamStrength]:
    """Club strength, shared with the backtest so the two cannot diverge."""
    return season_strength(
        corpus.season,
        played,
        on_fallback=lambda error: print(
            f"Dixon-Coles did not fit, using goal averages: {error}", file=sys.stderr
        ),
    )


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
    strength = _strength(corpus, played)
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


def _published_availability() -> dict[int, AvailabilityEvidence]:
    """FPL's own status per player code, for the upcoming event.

    Without this the projection reads an injured player's history and reports
    the minutes he used to play. The flag is free, already published, and the
    difference between "this player is good" and "this player is good and
    playing".

    A failure here is not fatal: availability sharpens a projection rather than
    defining it, and refusing to publish at all because a second endpoint was
    briefly unreachable would be the worse trade.
    """
    request = urllib.request.Request(BOOTSTRAP, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
            payload = parse_json(response.read().decode("utf-8"), source=BOOTSTRAP)
    except (urllib.error.URLError, TimeoutError, MalformedJsonError) as error:
        print(f"availability unavailable, projecting without it: {error}", file=sys.stderr)
        return {}

    assert isinstance(payload, dict)
    published: dict[int, AvailabilityEvidence] = {}
    for element in parse_elements(payload["elements"], model=BootstrapElement):
        status = element.status
        if status not in get_args(AvailabilityStatus):
            continue
        chance = element.chance_of_playing_next_round
        # A doubtful status without a published chance cannot be modelled, and
        # inventing one would be the guess this whole contract exists to stop.
        if status == "d" and chance is None:
            continue
        published[element.code] = AvailabilityEvidence(
            status=cast(AvailabilityStatus, status),
            chance_of_playing=chance,
        )
    return published


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    credentials = SupabaseCredentials.from_env(os.environ)
    with SupabaseRestClient(credentials) as client:
        corpus = load_season(client, args.season)

    availability = _published_availability()
    projections = project_next_match(corpus, availability=availability)
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
        "basis": (
            "next match against an average opponent, no fixture applied; "
            f"availability read for {len(availability)} players"
        ),
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
