"""Publish a gameweek 1 to 38 plan from the opening squad.

Before the first deadline every manager owns the same nothing, so this publishes
one plan rather than a plan each. After the season starts the same planner needs
a per-manager squad, which is a different job with a different entry point.

Fixtures and prices come from FPL. Scoring records come from the committed
projection artifact, joined on player code. Per-gameweek expected points are the
player's record scaled by the opponent's measured strength on the route that
matters for his position, home or away, which is the same adjustment the opening
squad uses over its five-week window.

Usage:
    python -m fpl_andres.cli.publish_season_plan
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_andres import timeouts
from fpl_andres.backtesting.fixtures import TeamStrength
from fpl_andres.bootstrap import BootstrapElement, parse_elements
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.optimization.contracts import (
    CurrentSquadPlayer,
    HorizonPlayerForecast,
    OptimizationRules,
    OptimizationStateEvidence,
    PositionConstraint,
    TransferRulesAddendum,
)
from fpl_andres.planning.fixture_routes import fixture_difficulty, fixture_multiplier
from fpl_andres.planning.opening import (
    PLAYABLE_START_RATE,
    OpeningSettings,
    choose_opening_squad,
)
from fpl_andres.planning.season_plan import (
    plan_season,
)
from fpl_andres.positions import Position
from fpl_andres.rules import RulesSnapshot
from fpl_andres.simulation.squad import Candidate as SquadCandidate
from fpl_andres.simulation.squad import SquadRules

SQUAD_RULES = SquadRules(budget_tenths=1000, club_limit=3, position_counts={1: 2, 2: 5, 3: 5, 4: 3})

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
PROJECTIONS = Path("apps/web/src/data/projections.json")
OPENING_SQUAD = Path("apps/web/src/data/opening-squad.json")
DEFAULT_OUTPUT = Path("apps/web/src/data/season-plan.json")

SCHEMA_VERSION = 1
POSITION_CODES = {position.value: position.code for position in Position}
SQUAD_SHAPE = {1: 2, 2: 5, 3: 5, 4: 3}
LINEUP_RANGE = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}
# The pool the planner may transfer into. Trimmed hard because window solve time
# grows with it and because the four hundredth-best player is not a candidate for
# a plan; the artifact records the size so the trim is visible rather than
# implied.
POOL_PER_POSITION = 14
# Cheapest playable options per position, on top of the best ones.
#
# A pool ranked only by expected points contains no bench fodder, and a squad
# must still field fifteen: the solver was forced to spend a mean of 23.4 of the
# 100 million on players who score nothing, once benching a 12.0 million
# midfielder. The bench scores zero outside a Bench Boost, so every pound parked
# there is a pound not in the eleven, and the fix is to make cheap players
# available rather than to penalise expensive ones.
ENABLERS_PER_POSITION = 6


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-season-plan")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--projections", default=str(PROJECTIONS))
    parser.add_argument("--opening-squad", default=str(OPENING_SQUAD))
    parser.add_argument("--time-limit", type=float, default=30.0)
    # FPL publishes neither of these in the bootstrap. `docs/PARAMETERS.md`
    # records them as never inferred, so they are required rather than
    # defaulted: a plan built on a guessed transfer cost is a wrong plan that
    # looks right.
    parser.add_argument("--weekly-free-transfers", type=int, required=True)
    parser.add_argument("--transfer-cost-points", type=int, required=True)
    parser.add_argument(
        "--rules-reference",
        required=True,
        help="where those two numbers were read from, recorded in the artifact",
    )
    return parser


def _get_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
        raw: bytes = response.read()
    return raw


def _get(url: str) -> object:
    return parse_json(_get_bytes(url).decode("utf-8"), source=url)


def _season_of(first_deadline: datetime) -> str:
    """FPL seasons open in August and close in May, so the year the first
    deadline falls in is the opening year."""
    start = first_deadline.year
    return f"{start}-{str(start + 1)[-2:]}"


@dataclass(frozen=True)
class Candidate:
    element_id: int
    code: int
    name: str
    position: int
    team_id: int
    club: str
    price_tenths: int
    record: float
    # His best single match last season. What a chip is played hoping for.
    best_match: float
    squad_number: int | None
    # What `record` is made of, so a fixture can be applied to each route.
    routes: Mapping[str, float] = field(default_factory=dict)


def _opponent_multiplier(
    *,
    candidate: Candidate,
    opponent: int,
    home: bool,
    strength: Mapping[int, TeamStrength],
) -> float:
    """How much this fixture is worth to this player, against an average one.

    Each published scoring route is bent by what the fixture does to *it*, then
    the lot is expressed as a ratio against the neutral projection. One blended
    difficulty number cannot do this: the same hard away tie suppresses clean
    sheets and raises saves, so it is good for the keeper and bad for the
    defender in front of him.
    """
    if opponent not in strength or candidate.team_id not in strength:
        return 1.0
    return fixture_multiplier(
        candidate.routes,
        neutral_points=candidate.record,
        team_id=candidate.team_id,
        opponent_id=opponent,
        home=home,
        strength=strength,
    )


def _data_gaps(
    pool: Sequence[Candidate],
    clubs: Mapping[int, Mapping[str, Any]],
) -> dict[str, object]:
    """Which clubs the previous season cannot say anything about.

    The record season is the last Premier League season, so the three promoted
    clubs have almost no players in it and no measured strength at all. Their
    fixtures are therefore rated as exactly average, which is a guess wearing
    the same clothes as a measurement. Counting it here means the page can say
    how big the hole is rather than implying there is not one.
    """
    represented = {candidate.club for candidate in pool}
    absent = sorted(
        str(team["short_name"])
        for team in clubs.values()
        if str(team["short_name"]) not in represented
    )
    return {
        "clubsWithoutRecord": absent,
        "clubsInPool": len(represented),
        "clubsInLeague": len(clubs),
    }


# Every chip is available twice: once in the first half of the season, once in
# the second. FPL resets the set at the halfway point, so a chip unplayed by
# gameweek nineteen is simply lost.
FIRST_HALF_LAST_EVENT = 19
# What a chip is expected to be worth before it is worth planning around. Below
# this the plan still plays it, because an unplayed chip scores nothing at all,
# but it says so rather than presenting a thin week as a masterstroke.
CHIP_TARGET_POINTS = 20.0
# How far a wildcard's rebuild is credited forward. A wildcard keeps its squad,
# so the gain persists; eight weeks is the horizon the plan itself commits to.
WILDCARD_HORIZON = 8


def _upside(record: Mapping[str, Any] | None) -> float:
    """How much better a player's best week is than his ordinary one.

    Zero means his ceiling is his median: nothing to gain by trebling him over
    someone steadier. Derived from the published shape rather than assumed, and
    returns zero where the shape was withheld for want of appearances.
    """
    if record is None:
        return 0.0
    ceiling = record.get("ceiling")
    median = record.get("median")
    if not isinstance(ceiling, (int, float)) or not isinstance(median, (int, float)):
        return 0.0
    if ceiling <= 0:
        return 0.0
    return max(0.0, (float(ceiling) - float(median)) / float(ceiling))


def _chip_plan(
    gameweeks: Sequence[dict[str, Any]],
    named: Mapping[int, Candidate],
    ceiling: Mapping[int, float] | None = None,
    peak: Mapping[tuple[int, int], float] | None = None,
    code_of: Mapping[int, int] | None = None,
) -> list[dict[str, object]]:
    """When to play all eight chips: four in each half of the season.

    Each rule is the chip's own definition turned into a measurement of what
    playing it *adds*, which is not the same as what the week scores.

    - **Triple Captain** turns a double into a treble, so it adds one more
      copy of the captain.
    - **Bench Boost** scores the bench, so it adds exactly the bench.
    - **Free Hit** buys one week of unlimited transfers and hands the squad
      back, so it adds the gap between the best eleven money could buy and the
      eleven the plan actually fields.
    - **Wildcard** buys unlimited transfers and keeps them, so the same gap
      counts for every week it persists rather than only the week it is played.

    Every chip is scored twice. Expected points are the average being aimed at;
    the ceiling is the case the chip is actually played for. Trebling a captain
    who returns his average is a wasted chip -- it pays when he takes a goal, a
    clean sheet and a defensive contribution in the same afternoon, which is his
    ceiling and not his mean. So the target is judged on the ceiling, and both
    numbers are published rather than the flattering one.

    Chip *interaction* is not solved: playing one changes what the others are
    worth, and these are eight independent answers to eight separate questions.
    """
    if not gameweeks:
        return []

    peak_by = peak or {}
    code_for = code_of or {}
    chips: list[dict[str, object]] = []
    taken: set[int] = set()

    shortfall = {
        week["event"]: max(0.0, (ceiling or {}).get(week["event"], 0.0) - week["projectedPoints"])
        for week in gameweeks
    }

    def free(weeks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        return [week for week in weeks if week["event"] not in taken]

    def verdict(best: float) -> str:
        return (
            f"clears the {CHIP_TARGET_POINTS:.0f} points a chip wants to return"
            if best >= CHIP_TARGET_POINTS
            else (
                f"under the {CHIP_TARGET_POINTS:.0f} points that makes a chip worth "
                f"building around, but an unplayed chip expires at nothing"
            )
        )

    def peak_of(event: int, element_id: int) -> float:
        return float(peak_by.get((event, element_id), 0.0))

    def bench_points(week: dict[str, Any]) -> tuple[float, float]:
        mean = sum(week["expected"].get(str(code), 0.0) for code in week["bench"])
        best = sum(peak_of(week["event"], element) for element in week["benchElementIds"])
        return float(mean), float(best)

    def treble(week: dict[str, Any]) -> tuple[float, float, int]:
        """The best player to treble that week, at his mean and at his best."""
        candidates = [
            (
                peak_of(week["event"], element),
                week["expected"].get(str(code_for.get(element, 0)), 0.0),
                element,
            )
            for element in week["squadElementIds"]
        ]
        if not candidates:
            return 0.0, 0.0, 0
        best, mean, element = max(candidates, key=lambda entry: entry[0])
        return float(mean), float(best), element

    index_of = {week["event"]: index for index, week in enumerate(gameweeks)}

    def persisting(week: dict[str, Any]) -> float:
        start = index_of[week["event"]]
        return float(
            sum(shortfall[each["event"]] for each in gameweeks[start : start + WILDCARD_HORIZON])
        )

    halves = (
        ("first", [week for week in gameweeks if week["event"] <= FIRST_HALF_LAST_EVENT]),
        ("second", [week for week in gameweeks if week["event"] > FIRST_HALF_LAST_EVENT]),
    )

    for half, weeks in halves:
        if not weeks:
            continue

        candidates = free(weeks)
        if candidates:
            chosen = max(candidates, key=lambda week: treble(week)[1])
            mean, best, element = treble(chosen)
            taken.add(chosen["event"])
            code = code_for.get(element, 0)
            name = named[code].name if code in named else "the captain"
            chips.append(
                {
                    "event": chosen["event"],
                    "chip": "Triple Captain",
                    "half": half,
                    "gain": round(mean, 2),
                    "ceiling": round(best, 2),
                    "note": (
                        f"a third copy of {name}: {mean:.1f} if he returns his average, "
                        f"{best:.1f} on the sort of afternoon the chip is played for, which "
                        f"{verdict(best)}"
                    ),
                }
            )

        candidates = free(weeks)
        if candidates:
            chosen = max(candidates, key=lambda week: bench_points(week)[1])
            mean, best = bench_points(chosen)
            taken.add(chosen["event"])
            chips.append(
                {
                    "event": chosen["event"],
                    "chip": "Bench Boost",
                    "half": half,
                    "gain": round(mean, 2),
                    "ceiling": round(best, 2),
                    "note": (
                        f"the bench averages {mean:.1f} and reaches {best:.1f} if all four "
                        f"have the sort of week they are capable of, the best bench of the "
                        f"{half} half, which {verdict(best)}"
                    ),
                }
            )

        candidates = free(weeks)
        if candidates:
            chosen = max(candidates, key=lambda week: shortfall[week["event"]])
            gain = shortfall[chosen["event"]]
            taken.add(chosen["event"])
            chips.append(
                {
                    "event": chosen["event"],
                    "chip": "Free Hit",
                    "half": half,
                    "gain": round(gain, 2),
                    "ceiling": round(gain, 2),
                    "note": (
                        f"one week of unlimited transfers adds {gain:.1f}, the largest "
                        f"one-week gap in the {half} half, which {verdict(gain)}"
                    ),
                }
            )

        candidates = free(weeks)
        if candidates:
            chosen = max(candidates, key=persisting)
            gain = persisting(chosen)
            taken.add(chosen["event"])
            chips.append(
                {
                    "event": chosen["event"],
                    "chip": "Wildcard",
                    "half": half,
                    "gain": round(gain, 2),
                    "ceiling": round(gain, 2),
                    "note": (
                        f"rebuilding here recovers {gain:.1f} across the following "
                        f"{WILDCARD_HORIZON} gameweeks, which {verdict(gain)}"
                    ),
                }
            )

    return sorted(chips, key=lambda chip: (chip["event"] is None, chip["event"] or 0))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    artifact = read_json_file(Path(args.projections))
    record_by_code = {int(row["code"]): row for row in artifact["players"]}
    strength_by_code = {
        int(row["code"]): TeamStrength(
            attack_home=row["attackHome"],
            attack_away=row["attackAway"],
            defence_home=row["defenceHome"],
            defence_away=row["defenceAway"],
        )
        for row in artifact.get("clubs", ())
    }

    bootstrap_raw = _get_bytes(BOOTSTRAP)
    bootstrap = parse_json(bootstrap_raw.decode("utf-8"), source=BOOTSTRAP)
    bootstrap_hash = f"sha256:{hashlib.sha256(bootstrap_raw).hexdigest()}"
    assert isinstance(bootstrap, dict)
    clubs = {int(team["id"]): team for team in bootstrap["teams"]}
    strength = {
        team_id: strength_by_code[int(team["code"])]
        for team_id, team in clubs.items()
        if int(team["code"]) in strength_by_code
    }

    events = {int(event["id"]): event for event in bootstrap["events"] if not event.get("finished")}
    if not events:
        print("every gameweek is finished; nothing to plan", file=sys.stderr)
        return 1

    raw_fixtures = _get(FIXTURES)
    assert isinstance(raw_fixtures, list)
    # (event, team) -> list of (opponent, home)
    schedule: dict[tuple[int, int], list[tuple[int, bool]]] = {}
    for row in raw_fixtures:
        event = row["event"]
        if event is None:
            continue
        home_id, away_id = int(row["team_h"]), int(row["team_a"])
        schedule.setdefault((int(event), home_id), []).append((away_id, True))
        schedule.setdefault((int(event), away_id), []).append((home_id, False))

    candidates: list[Candidate] = []
    for element in parse_elements(bootstrap["elements"], model=BootstrapElement):
        if element.element_type not in POSITION_CODES or not element.is_available:
            continue
        record = record_by_code.get(element.code)
        if record is None:
            continue
        # The same floor the opening squad applies. Without it the plan happily
        # transferred in a fringe forward who has not started a match: his
        # per-match record looks fine because it is measured over the handful of
        # matches he did play.
        if float(record["probabilityStart"]) < PLAYABLE_START_RATE:
            continue
        candidates.append(
            Candidate(
                element_id=element.id,
                code=element.code,
                name=element.web_name,
                position=element.element_type,
                team_id=element.team,
                club=str(clubs[element.team]["short_name"]),
                price_tenths=element.now_cost,
                record=float(record["expectedPoints"]),
                best_match=float(record.get("ceiling") or record["expectedPoints"]),
                routes=record.get("routes", {}),
                squad_number=element.squad_number,
            )
        )

    opening = read_json_file(Path(args.opening_squad))
    squad_codes = [int(pick["code"]) for pick in opening["picks"]]
    by_code = {candidate.code: candidate for candidate in candidates}
    missing = [code for code in squad_codes if code not in by_code]
    if missing:
        print(
            f"opening squad references {len(missing)} players who are no longer "
            f"selectable: {missing}. Republish the opening squad first.",
            file=sys.stderr,
        )
        return 1

    # Keep the squad, the strongest of everyone else, and the cheapest players
    # worth a bench place, position by position.
    held = {by_code[code].element_id for code in squad_codes}
    pool: list[Candidate] = [by_code[code] for code in squad_codes]
    for position in SQUAD_SHAPE:
        available = [c for c in candidates if c.position == position and c.element_id not in held]
        best = sorted(available, key=lambda c: -c.record)[:POOL_PER_POSITION]
        chosen = {c.element_id for c in best}
        cheapest = sorted(
            (c for c in available if c.element_id not in chosen),
            key=lambda c: (c.price_tenths, -c.record),
        )[:ENABLERS_PER_POSITION]
        pool.extend(best)
        pool.extend(cheapest)

    ordered_events = sorted(events)
    cutoffs = {
        event: datetime.fromisoformat(events[event]["deadline_time"].replace("Z", "+00:00"))
        for event in ordered_events
    }
    season = _season_of(cutoffs[ordered_events[0]])
    snapshot = RulesSnapshot.from_bootstrap(
        bootstrap,
        season=season,
        source_hash=bootstrap_hash,
        weekly_free_transfers=args.weekly_free_transfers,
    )

    forecasts: list[HorizonPlayerForecast] = []
    difficulty: dict[int, float] = {}
    # (event, element id) -> points, so a card can show what the shirt is worth
    # that week rather than only the squad total.
    expected_by: dict[tuple[int, int], float] = {}
    # The same week priced at each player's best match rather than his average.
    # A chip is played for the upside, so this is what it is judged on.
    ceiling_by: dict[tuple[int, int], float] = {}
    now = datetime.now(UTC)
    for event in ordered_events:
        weights: list[float] = []
        for candidate in pool:
            games = schedule.get((event, candidate.team_id), ())
            if not games:
                # A blank gameweek is zero, not an average week. Nothing is a
                # more honest projection for a player who is not playing.
                expected = 0.0
                peak = 0.0
            else:
                multiplier = sum(
                    _opponent_multiplier(
                        candidate=candidate,
                        opponent=opponent,
                        home=home,
                        strength=strength,
                    )
                    for opponent, home in games
                )
                expected = candidate.record * multiplier
                peak = candidate.best_match * multiplier
            expected_by[(event, candidate.element_id)] = round(expected, 2)
            ceiling_by[(event, candidate.element_id)] = round(peak, 2)
            forecasts.append(
                HorizonPlayerForecast(
                    season=season,
                    event=event,
                    element_id=candidate.element_id,
                    team_id=candidate.team_id,
                    position_id=candidate.position,
                    buy_price_tenths=candidate.price_tenths,
                    sell_price_tenths=candidate.price_tenths,
                    expected_points=round(expected, 3),
                    evidence_level="inferred",
                    model_name="season-plan",
                    model_version=str(SCHEMA_VERSION),
                    data_available_at=cutoffs[event],
                    source_hashes=(f"sha256:{candidate.code:064x}",),
                )
            )
        for candidate in pool:
            for opponent, home in schedule.get((event, candidate.team_id), ()):
                weights.append(
                    _opponent_multiplier(
                        candidate=candidate, opponent=opponent, home=home, strength=strength
                    )
                )
        # Higher multiplier means an easier opponent, so invert it to read as
        # difficulty everywhere it is used.
        difficulty[event] = -(sum(weights) / len(weights)) if weights else 0.0

    rules = OptimizationRules(
        season=season,
        squad_size=snapshot.squad_size,
        lineup_size=snapshot.starting_size,
        club_limit=snapshot.club_limit,
        transfer_cap=snapshot.transfer_cap,
        positions=tuple(
            PositionConstraint(
                position_id=position,
                squad_count=count,
                lineup_minimum=LINEUP_RANGE[position][0],
                lineup_maximum=LINEUP_RANGE[position][1],
            )
            for position, count in SQUAD_SHAPE.items()
        ),
        transfer_rules=TransferRulesAddendum(
            season=season,
            weekly_free_transfers=snapshot.weekly_free_transfers,
            maximum_free_transfers=snapshot.max_free_transfers,
            transfer_cost_points=args.transfer_cost_points,
            source_reference=args.rules_reference,
            source_hash=bootstrap_hash,
            data_available_at=now,
        ),
        published_rules_hash=bootstrap_hash,
        data_available_at=now,
    )

    plan = plan_season(
        events=ordered_events,
        cutoffs=cutoffs,
        forecasts=forecasts,
        opening_squad=tuple(
            CurrentSquadPlayer(
                element_id=by_code[code].element_id,
                selling_price_tenths=by_code[code].price_tenths,
            )
            for code in squad_codes
        ),
        bank_tenths=int(opening["budgetTenths"]) - int(opening["spentTenths"]),
        free_transfers=1,
        rules=rules,
        state_evidence=OptimizationStateEvidence(
            public_state_as_of=now,
            public_data_available_at=now,
            overrides_updated_at=now,
            public_source_hashes=(f"sha256:{2:064x}",),
            manager_overrides_hash=f"sha256:{3:064x}",
        ),
        time_limit_seconds=args.time_limit,
    )

    detail = {candidate.element_id: candidate for candidate in pool}
    # Fifteen full player objects per gameweek repeated thirty-eight times is
    # most of the file. The plan references codes and carries one table.
    named: dict[int, Candidate] = {}

    def ref(element_id: int) -> int:
        candidate = detail[element_id]
        named[candidate.code] = candidate
        return candidate.code

    gameweeks = []
    for planned in plan.events:
        event_plan = planned.plan
        squad = set(event_plan.squad_element_ids)
        # "HUL (A)" per club, so a card can name the opponent rather than repeat
        # the club whose shirt is already drawn beside the player. A double
        # gameweek gets both.
        opponents: dict[str, list[str]] = {}
        # One to five for the same tie, so a card can show how hard the week is
        # without the reader working it out from club names.
        week_difficulty: dict[str, int | None] = {}
        for element_id in squad:
            candidate = detail[element_id]
            if candidate.club in opponents:
                continue
            games = schedule.get((planned.event, candidate.team_id), ())
            opponents[candidate.club] = [
                f"{clubs[opponent]['short_name']} ({'H' if home else 'A'})"
                for opponent, home in games
            ]
            week_difficulty[candidate.club] = fixture_difficulty(games, candidate.team_id, strength)

        gameweeks.append(
            {
                "event": planned.event,
                "deadline": cutoffs[planned.event]
                .astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "confidence": planned.confidence,
                "starters": [ref(pid) for pid in event_plan.starter_element_ids],
                "bench": [ref(pid) for pid in event_plan.bench_element_ids],
                "captain": ref(event_plan.captain_element_id),
                "viceCaptain": ref(event_plan.vice_captain_element_id),
                "transfersIn": [ref(pid) for pid in event_plan.transfers_in],
                "transfersOut": [ref(pid) for pid in event_plan.transfers_out],
                "opponents": opponents,
                "difficulty": week_difficulty,
                # Element ids alongside the published codes, so the chip planner
                # can price a week without re-deriving the mapping.
                "squadElementIds": sorted(squad),
                "benchElementIds": list(event_plan.bench_element_ids),
                "expected": {
                    str(detail[element_id].code): expected_by[(planned.event, element_id)]
                    for element_id in squad
                },
                "freeTransfersBefore": event_plan.free_transfers_before,
                "paidTransfers": event_plan.paid_transfers,
                "transferCostPoints": event_plan.transfer_cost_points,
                "projectedPoints": round(event_plan.projected_points_before_cost, 2),
                "netExpectedPoints": round(event_plan.net_expected_points, 2),
                "bankAfterTenths": event_plan.bank_after_tenths,
            }
        )

    # The best eleven the whole budget could buy that week, ignoring transfers.
    # A chip is only worth playing to the extent the plan falls short of it.
    #
    # Drawn from every candidate rather than the trimmed planning pool: a Free
    # Hit can buy anyone in the game for a week, so measuring it against the
    # eighty-five players the plan already shops from said it was worth nothing.
    ceiling: dict[int, float] = {}
    candidate_for = {
        candidate.element_id: SquadCandidate(
            element_id=candidate.element_id,
            element_code=candidate.code,
            position=candidate.position,
            team_id=candidate.team_id,
            price_tenths=candidate.price_tenths,
            web_name=candidate.name,
        )
        for candidate in candidates
    }
    for event in ordered_events:
        points = {
            candidate.element_id: sum(
                candidate.record
                * _opponent_multiplier(
                    candidate=candidate,
                    opponent=opponent,
                    home=home,
                    strength=strength,
                )
                for opponent, home in schedule.get((event, candidate.team_id), ())
            )
            for candidate in candidates
        }
        try:
            free_squad = choose_opening_squad(
                list(candidate_for.values()),
                points,
                {element_id: 1.0 for element_id in candidate_for},
                OpeningSettings(rules=SQUAD_RULES, bench_weight=0.0),
            )
        except ValueError:
            continue
        # The armband too, because the plan's own `projectedPoints` counts it.
        # Comparing an eleven against an eleven-plus-captain made the ceiling
        # look lower than the plan every week, so the shortfall was always zero
        # and the Free Hit and Wildcard were never played.
        starting = [points[player.element_id] for player in free_squad.starters]
        ceiling[event] = sum(starting) + max(starting, default=0.0)

    chips = _chip_plan(
        gameweeks,
        named,
        ceiling,
        ceiling_by,
        {candidate.element_id: candidate.code for candidate in pool},
    )

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "season": season,
        "recordSeason": str(artifact["season"]),
        "basis": (
            "opening squad, fixture-adjusted projections, solved in overlapping "
            f"windows and committed {len(plan.events)} gameweeks deep"
        ),
        "rulesReference": args.rules_reference,
        "weeklyFreeTransfers": snapshot.weekly_free_transfers,
        "maximumFreeTransfers": snapshot.max_free_transfers,
        "transferCostPoints": args.transfer_cost_points,
        "firstEvent": plan.events[0].event,
        "lastEvent": plan.events[-1].event,
        "windowsSolved": plan.windows_solved,
        "poolSize": plan.pool_size,
        "netExpectedPoints": round(plan.net_expected_points, 2),
        "chips": chips,
        "dataGaps": _data_gaps(pool, clubs),
        "players": {
            str(code): {
                "name": candidate.name,
                "position": POSITION_CODES[candidate.position],
                "club": candidate.club,
                "priceTenths": candidate.price_tenths,
                "squadNumber": candidate.squad_number,
            }
            for code, candidate in sorted(named.items())
        },
        "gameweeks": gameweeks,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {output} — gameweeks {payload['firstEvent']} to {payload['lastEvent']}, "
        f"{plan.windows_solved} windows, pool {plan.pool_size}, "
        f"{payload['netExpectedPoints']} net points"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
