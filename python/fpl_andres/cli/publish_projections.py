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
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast, get_args

from fpl_andres import timeouts
from fpl_andres.artifacts import (
    PROJECTIONS_META_SCHEMA_VERSION,
    PROJECTIONS_SCHEMA_VERSION,
)
from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus, load_season
from fpl_andres.backtesting.fixtures import (
    Fixture,
    TeamStrength,
    season_strength,
)
from fpl_andres.backtesting.projector import MatchProjection, project_next_match
from fpl_andres.backtesting.scoring import PointsBreakdown
from fpl_andres.bootstrap import BootstrapElement, parse_elements
from fpl_andres.jsonio import MalformedJsonError, parse_json, read_json_file
from fpl_andres.models.minutes import AvailabilityEvidence, AvailabilityStatus
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient
from fpl_andres.positions import Position

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
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
    # Read for the defensive-contribution route alone, where a season played
    # under a different arrangement is a prior rather than a record. Empty says
    # there is no season before this one worth loading.
    parser.add_argument("--previous-season", default="")
    parser.add_argument(
        "--live",
        type=Path,
        default=None,
        help="Immutable settled current-season snapshot, or directory of gw*.json snapshots.",
    )
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
    yellowCards: float
    redCards: float
    ownGoals: float
    penaltiesMissed: float
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
    expectedBps: float | None
    bpsDeviation: float | None
    probabilityAppear: float
    #: Compatibility alias for P(60+) until schema 3 moves readers atomically.
    probabilityStart: float
    probabilityStartModel: float
    probabilitySixtyMinutes: float
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
    def priced(value: float) -> float:
        # `or` rather than a bare round: a route rounding to negative zero is
        # published as `-0.0`, which is true and reads as a defect.
        return round(value, 3) or 0.0

    return {
        "appearance": priced(breakdown.appearance),
        "attacking": priced(breakdown.attacking),
        "cleanSheet": priced(breakdown.clean_sheet),
        "bonus": priced(breakdown.bonus),
        "saves": priced(breakdown.saves),
        "conceding": priced(breakdown.conceding),
        "yellowCards": priced(breakdown.yellow_cards),
        "redCards": priced(breakdown.red_cards),
        "ownGoals": priced(breakdown.own_goals),
        "penaltiesMissed": priced(breakdown.penalties_missed),
        "defensiveContribution": priced(breakdown.defensive_contribution),
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
        "expectedBps": (
            round(projection.expected_bps, 3) if projection.expected_bps is not None else None
        ),
        "bpsDeviation": (
            round(projection.bps_deviation, 3) if projection.bps_deviation is not None else None
        ),
        "probabilityAppear": round(projection.minutes.probability_appear, 3),
        # Additive bridge: existing readers still consume `probabilityStart`
        # as P(60+) until the generated artifact carries both explicit fields.
        "probabilityStart": round(projection.minutes.probability_sixty_minutes, 3),
        "probabilityStartModel": round(projection.minutes.probability_start, 3),
        "probabilitySixtyMinutes": round(
            projection.minutes.probability_sixty_minutes,
            3,
        ),
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


def _clubs(
    corpus: SeasonCorpus,
    previous: SeasonCorpus | None = None,
) -> list[dict[str, object]]:
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
    previous_strength = (
        _strength(
            previous,
            [
                fixture
                for event in sorted(previous.fixtures_by_event)
                for fixture in previous.fixtures_by_event[event]
            ],
        )
        if previous is not None
        else {}
    )
    previous_by_code = {
        code: previous_strength[team_id]
        for team_id, code in (previous.code_by_team.items() if previous is not None else ())
        if team_id in previous_strength
    }
    carried_source_season = previous.season if previous is not None else corpus.season
    played_by_team: dict[int, int] = {}
    for fixture in played:
        if not fixture.finished:
            continue
        played_by_team[fixture.team_h] = played_by_team.get(fixture.team_h, 0) + 1
        played_by_team[fixture.team_a] = played_by_team.get(fixture.team_a, 0) + 1
    clubs: list[dict[str, object]] = []
    for team_id, code in sorted(corpus.code_by_team.items()):
        current_ready = played_by_team.get(team_id, 0) >= MINIMUM_MATCHES
        measured = strength.get(team_id) if current_ready else previous_by_code.get(code)
        if measured is None:
            continue
        current_basis = current_ready and team_id in strength
        clubs.append(
            {
                "code": code,
                "shortName": corpus.short_name_by_team.get(team_id, ""),
                "attackHome": round(measured.attack_home, 3),
                "attackAway": round(measured.attack_away, 3),
                "defenceHome": round(measured.defence_home, 3),
                "defenceAway": round(measured.defence_away, 3),
                "strengthBasis": ("current-season fitted" if current_basis else "carried fitted"),
                "sourceSeason": corpus.season if current_basis else carried_source_season,
            }
        )
    return clubs


def _published_bootstrap() -> Mapping[str, object] | None:
    request = urllib.request.Request(BOOTSTRAP, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
            payload = parse_json(response.read().decode("utf-8"), source=BOOTSTRAP)
    except (urllib.error.URLError, TimeoutError, MalformedJsonError) as error:
        print(f"bootstrap unavailable: {error}", file=sys.stderr)
        return None
    return payload if isinstance(payload, Mapping) else None


def _published_fixtures() -> list[Mapping[str, object]]:
    request = urllib.request.Request(FIXTURES, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
            payload = parse_json(response.read().decode("utf-8"), source=FIXTURES)
    except (urllib.error.URLError, TimeoutError, MalformedJsonError) as error:
        raise ValueError(f"live fixture evidence unavailable: {error}") from error
    if not isinstance(payload, list) or not all(isinstance(row, Mapping) for row in payload):
        raise ValueError("FPL fixtures payload must be a list of objects")
    return payload


def _published_availability(
    payload: Mapping[str, object] | None,
) -> dict[int, AvailabilityEvidence]:
    """FPL's own status per player code, for the upcoming event.

    Without this the projection reads an injured player's history and reports
    the minutes he used to play. The flag is free, already published, and the
    difference between "this player is good" and "this player is good and
    playing".

    A failure here is not fatal: availability sharpens a projection rather than
    defining it, and refusing to publish at all because a second endpoint was
    briefly unreachable would be the worse trade.
    """
    if payload is None:
        print("availability unavailable, projecting without it", file=sys.stderr)
        return {}
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


def corpus_from_live_snapshot(
    snapshot: Mapping[str, object],
    bootstrap: Mapping[str, object],
    fixtures: Sequence[Mapping[str, object]],
) -> SeasonCorpus:
    """Build current-season rows from one immutable settled live event."""
    season = snapshot.get("season")
    event = snapshot.get("event")
    captured_at = snapshot.get("capturedAt")
    live_rows = snapshot.get("elements")
    if (
        not isinstance(season, str)
        or not isinstance(event, int)
        or not isinstance(captured_at, str)
        or snapshot.get("roundComplete") is not True
        or not isinstance(live_rows, list)
    ):
        raise ValueError("live projection snapshot is incomplete")
    elements = parse_elements(bootstrap.get("elements"), model=BootstrapElement)
    teams = bootstrap.get("teams")
    if not isinstance(teams, list):
        raise ValueError("bootstrap teams must be a list")
    corpus = SeasonCorpus(season=season)
    for team in teams:
        if not isinstance(team, Mapping):
            continue
        team_id = int(team["id"])
        corpus.code_by_team[team_id] = int(team["code"])
        corpus.short_name_by_team[team_id] = str(team["short_name"])
        corpus.name_by_team[team_id] = str(team["name"])
    metadata = {element.id: element for element in elements}
    fixtures_by_id: dict[int, tuple[datetime, frozenset[int]]] = {}
    fixtures_by_team: dict[int, list[int]] = {}
    for fixture in fixtures:
        fixture_id = fixture.get("id")
        home_team = fixture.get("team_h")
        away_team = fixture.get("team_a")
        if (
            fixture.get("event") != event
            or not isinstance(fixture.get("kickoff_time"), str)
            or not isinstance(fixture_id, int)
            or not isinstance(home_team, int)
            or not isinstance(away_team, int)
        ):
            continue
        kickoff = datetime.fromisoformat(str(fixture["kickoff_time"]).replace("Z", "+00:00"))
        home_score = fixture.get("team_h_score")
        away_score = fixture.get("team_a_score")
        teams = frozenset((home_team, away_team))
        fixtures_by_id[fixture_id] = (kickoff, teams)
        for team_id in teams:
            fixtures_by_team.setdefault(team_id, []).append(fixture_id)
        corpus.fixtures_by_event.setdefault(event, []).append(
            Fixture(
                fixture_id=fixture_id,
                event=event,
                team_h=home_team,
                team_a=away_team,
                kickoff_time=kickoff,
                team_h_score=home_score if isinstance(home_score, int) else None,
                team_a_score=away_score if isinstance(away_score, int) else None,
                finished=fixture.get("finished") is True,
            )
        )
    rows: list[ElementRow] = []
    for raw in live_rows:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("stats"), Mapping):
            continue
        element_id = raw.get("id")
        element = metadata.get(element_id) if isinstance(element_id, int) else None
        if element is None:
            continue
        try:
            position = element.position.value
        except ValueError:
            continue
        corpus.position_by_element[element.id] = position
        corpus.team_by_element[element.id] = element.team
        corpus.name_by_element[element.id] = element.web_name
        corpus.code_by_element[element.id] = element.code
        corpus.price_by_element[element.id] = element.now_cost
        stats = raw["stats"]
        assert isinstance(stats, Mapping)
        explanations = raw.get("explain")
        first = explanations[0] if isinstance(explanations, list) and explanations else {}
        explained_fixture = first.get("fixture") if isinstance(first, Mapping) else None
        team_fixtures = fixtures_by_team.get(element.team, [])
        fixture_id = (
            int(explained_fixture)
            if isinstance(explained_fixture, int)
            else team_fixtures[0]
            if len(team_fixtures) == 1
            else 0
        )
        fixture_evidence = fixtures_by_id.get(fixture_id)
        if fixture_evidence is None:
            raise ValueError(f"fixture {fixture_id or explained_fixture} kickoff is unavailable")
        kickoff = fixture_evidence[0]
        rows.append(
            ElementRow(
                gameweek=event,
                element_id=element.id,
                element_code=element.code,
                fixture_id=fixture_id,
                minutes=int(stats.get("minutes", 0)),
                started=int(stats.get("starts", 0)) > 0,
                goals=int(stats.get("goals_scored", 0)),
                assists=int(stats.get("assists", 0)),
                expected_goals=float(stats.get("expected_goals", 0.0)),
                expected_assists=float(stats.get("expected_assists", 0.0)),
                total_points=int(stats.get("total_points", 0)),
                price_tenths=element.now_cost,
                selected=None,
                kickoff_time=kickoff,
                clean_sheets=int(stats.get("clean_sheets", 0)),
                saves=int(stats.get("saves", 0)),
                bonus=int(stats.get("bonus", 0)),
                bps=int(stats.get("bps", 0)),
                goals_conceded=int(stats.get("goals_conceded", 0)),
                yellow_cards=int(stats.get("yellow_cards", 0)),
                red_cards=int(stats.get("red_cards", 0)),
                own_goals=int(stats.get("own_goals", 0)),
                penalties_saved=int(stats.get("penalties_saved", 0)),
                penalties_missed=int(stats.get("penalties_missed", 0)),
                defensive_contribution=int(stats.get("defensive_contribution", 0)),
                clearances_blocks_interceptions=int(
                    stats.get("clearances_blocks_interceptions", 0)
                ),
                tackles=int(stats.get("tackles", 0)),
                recoveries=int(stats.get("recoveries", 0)),
            )
        )
    corpus.rows_by_gameweek[event] = rows
    return corpus


def corpus_from_live_snapshots(
    snapshots: Sequence[Mapping[str, object]],
    bootstrap: Mapping[str, object],
    fixtures: Sequence[Mapping[str, object]],
) -> SeasonCorpus:
    """Combine immutable settled events into one current-season corpus."""
    if not snapshots:
        raise ValueError("live projection requires at least one settled snapshot")
    combined: SeasonCorpus | None = None
    for snapshot in snapshots:
        event_corpus = corpus_from_live_snapshot(snapshot, bootstrap, fixtures)
        if combined is None:
            combined = event_corpus
            continue
        if event_corpus.season != combined.season:
            raise ValueError("live projection snapshots must name one season")
        repeated = set(combined.rows_by_gameweek) & set(event_corpus.rows_by_gameweek)
        if repeated:
            raise ValueError(f"live projection snapshots repeat event(s) {sorted(repeated)}")
        combined.rows_by_gameweek.update(event_corpus.rows_by_gameweek)
        combined.fixtures_by_event.update(event_corpus.fixtures_by_event)
    assert combined is not None
    return combined


def _live_snapshots(path: Path) -> list[Mapping[str, object]]:
    paths = sorted(path.glob("gw*.json")) if path.is_dir() else [path]
    snapshots = [read_json_file(candidate) for candidate in paths if candidate.is_file()]
    if not snapshots:
        raise ValueError(f"no live snapshots found at {path}")
    return snapshots


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    credentials = SupabaseCredentials.from_env(os.environ)
    bootstrap = _published_bootstrap()
    with SupabaseRestClient(credentials) as client:
        previous = load_season(client, args.previous_season) if args.previous_season else None
        if args.live is not None:
            if previous is None or bootstrap is None:
                raise ValueError("live projection requires previous-season history and bootstrap")
            corpus = corpus_from_live_snapshots(
                _live_snapshots(args.live),
                bootstrap,
                _published_fixtures(),
            )
        else:
            corpus = load_season(client, args.season)

    availability = _published_availability(bootstrap)
    projections = project_next_match(corpus, availability=availability, previous=previous)
    if not projections:
        print(f"no projections for {args.season}", file=sys.stderr)
        return 1

    players = sorted(
        (_entry(projection) for projection in projections),
        key=lambda entry: entry["code"],
    )
    clubs = _clubs(corpus, previous)
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
