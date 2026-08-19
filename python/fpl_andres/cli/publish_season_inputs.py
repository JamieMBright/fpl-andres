"""Publish what a browser needs to solve a season for itself.

The plan a manager wants is unique to them: their squad, their bank, their free
transfers, their remaining chips. None of that can be precomputed, and a
thirty-eight gameweek solve does not fit in a fifteen-second serverless budget.
So the solving moves to the browser, and this publishes its inputs.

Sent as a base projection per player plus a fixture multiplier per club per
gameweek, rather than expected points per player per gameweek. The second form
is 500 x 38 numbers; this one is 500 + 20 x 38, and the browser multiplies. Same
information, a twentieth of the bytes.

Their private state never leaves the device, because the solve never does.

Usage:
    python -m fpl_andres.cli.publish_season_inputs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from fpl_andres import timeouts
from fpl_andres.artifacts import SEASON_INPUTS_SCHEMA_VERSION
from fpl_andres.backtesting.fixtures import (
    RouteAdjustment,
    TeamStrength,
    market_baseline,
    market_route_adjustment,
    route_adjustment,
)
from fpl_andres.backtesting.scoring import (
    ASSIST_POINTS,
    GOAL_POINTS,
    RED_CARD_POINTS,
    YELLOW_CARD_POINTS,
)
from fpl_andres.bootstrap import BootstrapElement, parse_elements
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.models.fixture_odds import ClubMatchOdds, club_views, load_fixture_odds
from fpl_andres.models.market_evidence import (
    BonusCandidate,
    bonus_expectations,
    infer_participation,
)
from fpl_andres.models.market_routes import (
    MarketAttack,
    MarketCards,
    MarketRoutesError,
    blend_rate,
    market_attack,
    market_cards,
)
from fpl_andres.planning.fixture_routes import (
    PROMOTED_STRENGTH,
    ROUTE_KEYS,
    adjustment_difficulty,
    published_strength,
)
from fpl_andres.planning.opening import PLAYABLE_START_RATE
from fpl_andres.planning.transfers import TransferPlanSettings
from fpl_andres.positions import Position

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
PROJECTIONS = Path("apps/web/src/data/projections.json")
OPENING_SQUAD = Path("apps/web/src/data/opening-squad.json")
PLAYER_ODDS = Path("apps/web/src/data/player-odds.json")
FIXTURE_ODDS = Path("apps/web/src/data/fixture-odds.json")
UNDERSTAT = Path("apps/web/src/data/understat.json")
DEFAULT_OUTPUT = Path("apps/web/src/data/season-inputs.json")

SCHEMA_VERSION = SEASON_INPUTS_SCHEMA_VERSION
POSITION_CODES = {position.value: position.code for position in Position}
# Everyone the projector can rate, not a top-forty cut per position.
#
# The trim was justified as "small enough to ship". Measured 2026-08-07 that is
# not true: 144 players gzip to 3.67 kB and all 441 to 5.73 kB, so the whole
# saving was about two kilobytes. What it cost was the ability to represent a
# manager's own squad -- a declared fifteen containing anyone outside the cut
# could not be solved at all, and the plan silently fell back to the generic
# season. A pool that cannot express the user's team is the wrong pool.
#
# Players with no Premier League record still have no row, here or anywhere:
# that is a limit of the evidence, not of this number.
POOL_PER_POSITION = 250

#: FPL's own bootstrap does not publish the hit, so it is cited rather than read.
TRANSFER_COST_POINTS = 4

#: A single fixture quote is strongest for that fixture and then yields to the
#: player's measured record. Assumed until retained quotes can fit this decay.
MARKET_CARRY_HALF_LIFE_GAMEWEEKS = 2.0

#: How many of each position may start, from the published rules.
LINEUP_RANGE = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}

#: How many of each position a squad holds.
SQUAD_SHAPE = {1: 2, 2: 5, 3: 5, 4: 3}

#: FPL awards one a week. The number is in the rules page, not the bootstrap.
WEEKLY_FREE_TRANSFERS = 1

# Official 2026/27 BPS weights for the direct player markets this publisher
# can move. The full table is applied in models.market_evidence.
_BPS_GOAL_POINTS = {1: 12.0, 2: 12.0, 3: 18.0, 4: 24.0}
_BPS_ASSIST_POINTS = 9.0
_BONUS_CANDIDATE_FLOOR_PER_CLUB = 11


def _setting(bootstrap: Mapping[str, object], key: str) -> int:
    """One rule from FPL's own settings, or a refusal naming what is missing.

    The browser solver declared these as literals. A rule that cannot be read
    from its source has to stop the publish, not be typed in from memory.
    """
    settings = bootstrap.get("game_settings")
    if not isinstance(settings, Mapping) or key not in settings:
        raise ValueError(f"bootstrap game_settings does not publish {key}")
    value = settings[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"bootstrap game_settings.{key} is not a whole number")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-season-inputs")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--projections", default=str(PROJECTIONS))
    parser.add_argument("--opening-squad", default=str(OPENING_SQUAD))
    parser.add_argument(
        "--rules-reference",
        default="FPL rules page, Transfers section",
        help="Where the transfer rules that are not in the bootstrap were read.",
    )
    parser.add_argument(
        "--player-odds",
        default=str(PLAYER_ODDS),
        help=(
            "Anytime-scorer and assist prices, written by ingest-player-odds. "
            "Absent means no market view, and every route stays the record's."
        ),
    )
    parser.add_argument(
        "--fixture-odds",
        default=str(FIXTURE_ODDS),
        help=(
            "Match prices, written by ingest-odds. Where a fixture is priced "
            "its clean sheet and goals conceded replace the fitted strength."
        ),
    )
    parser.add_argument(
        "--understat",
        default=str(UNDERSTAT),
        help="Historical shot volume keyed by stable FPL player code.",
    )
    parser.add_argument(
        "--market-weight",
        type=float,
        default=0.35,
        help=(
            "How much of a player's goal and assist expectation the market "
            "owns. Sourced here rather than in the model, so it is one number "
            "in one place."
        ),
    )
    return parser


def _get(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
        return parse_json(response.read().decode("utf-8"), source=url)


def _understat_shots(path: Path) -> dict[int, float]:
    if not path.exists():
        return {}
    artifact = read_json_file(path)
    players = artifact.get("players")
    if not isinstance(players, list):
        raise ValueError(f"{path} publishes no players list")
    shots: dict[int, float] = {}
    for row in players:
        if not isinstance(row, Mapping):
            continue
        code = row.get("code")
        rate = row.get("shotsPer90")
        if isinstance(code, int) and isinstance(rate, (int, float)) and float(rate) >= 0.0:
            shots[code] = float(rate)
    return shots


def _artifact_provenance(
    path: Path,
    *,
    source: str,
    default_level: str,
) -> dict[str, object]:
    if not path.exists():
        return {
            "source": source,
            "level": "unavailable",
            "updatedAt": None,
            "contentHash": None,
        }
    artifact = read_json_file(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    updated = artifact.get("fetchedAt", artifact.get("generatedAt"))
    level = artifact.get("evidenceLevel", default_level)
    return {
        "source": str(artifact.get("source") or source),
        "level": str(level),
        "updatedAt": str(updated) if isinstance(updated, str) else None,
        "contentHash": f"sha256:{digest}",
    }


# Where the measured tie sits on the published one-to-five scale. A fixture is
# rated on both halves of it: what this side is likely to score and what it is
# likely to concede, at the venue it is played. Blanks are None, not three:
# there is no fixture to be difficult.


def _quoted_attack(odds_path: Path) -> dict[int, tuple[MarketAttack, date]]:
    """Goals and assists the market expects, by element, with the day quoted.

    A price is for one fixture, so the day it was quoted for has to travel with
    it: the number below is de-fixtured against that gameweek's multiplier
    before it can be published as a per-average-match route.
    """
    if not odds_path.exists():
        return {}
    artifact = read_json_file(odds_path)
    quoted: dict[int, tuple[MarketAttack, date]] = {}
    for row in artifact.get("players", []):
        element_id = row.get("element_id")
        kickoff = row.get("kickoff")
        if not isinstance(element_id, int) or not isinstance(kickoff, str):
            continue
        goal = row.get("anytime_goal")
        assist = row.get("anytime_assist")
        try:
            when = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).astimezone(UTC).date()
            attack = market_attack(
                float(goal) if isinstance(goal, (int, float)) else None,
                float(assist) if isinstance(assist, (int, float)) else None,
            )
        except (ValueError, MarketRoutesError):
            # A malformed kickoff, or a player priced certain to score. Both are
            # faults in the feed rather than in him; skipping him keeps the rest.
            continue
        if attack is not None:
            quoted[element_id] = (attack, when)
    return quoted


@dataclass(frozen=True)
class MarketAttackBlend:
    points: float
    goals: float
    assists: float
    recorded_events: float
    market_events: float


def _market_attack_blend(
    priced: tuple[MarketAttack, date] | None,
    position: int,
    record: Mapping[str, object],
    multipliers: Sequence[float],
    slots: Mapping[date, int],
    weight: float,
) -> MarketAttackBlend | None:
    """The attacking route with the market's view of it blended in.

    The market prices a fixture; this artifact publishes a route against an
    average opponent and lets the browser bend it by a per-gameweek multiplier.
    Publishing a fixture's number as if it were the average would apply that
    fixture twice, so the market rate is divided back out by the multiplier of
    the gameweek it was quoted in. What survives is what the book thinks of the
    footballer once his opponent is taken off, which is the quantity this file
    carries.

    Goals and assists are blended separately against the projector's own
    estimate of each, so a fixture with an anytime-scorer market and no assist
    market still counts for something and leaves the assists alone.

    Returns None wherever any part of that is unavailable -- no quote, no
    gameweek on that day, or a multiplier of nothing. Silence from a bookmaker
    leaves the record's own number standing.
    """
    if priced is None:
        return None
    attack, when = priced
    index = slots.get(when)
    goal_points = GOAL_POINTS.get(position)
    if index is None or index >= len(multipliers) or goal_points is None:
        return None
    multiplier = multipliers[index]
    if multiplier <= 0.0:
        return None
    if "expectedGoals" not in record or "expectedAssists" not in record:
        # The version of this that shipped before read a projection field the
        # projector never published, took the absence as "no market view" and
        # returned nothing for everybody. Refusing is the whole lesson.
        raise ValueError(
            "the projections artifact publishes no expectedGoals/expectedAssists, "
            "so a quoted price has nothing to blend against; regenerate it with "
            "publish_projections before publishing season inputs"
        )
    recorded_goals = float(str(record["expectedGoals"]))
    recorded_assists = float(str(record["expectedAssists"]))
    goals = recorded_goals
    assists = recorded_assists
    recorded_events = 0.0
    market_events = 0.0
    if attack.goals is not None:
        market_goals = attack.goals / multiplier
        recorded_events += recorded_goals
        market_events += market_goals
        goals = blend_rate(goals, market_goals, weight)
    if attack.assists is not None:
        market_assists = attack.assists / multiplier
        recorded_events += recorded_assists
        market_events += market_assists
        assists = blend_rate(assists, market_assists, weight)
    return MarketAttackBlend(
        points=goals * goal_points + assists * ASSIST_POINTS,
        goals=goals,
        assists=assists,
        recorded_events=recorded_events,
        market_events=market_events,
    )


def _market_attacking(
    priced: tuple[MarketAttack, date] | None,
    position: int,
    record: Mapping[str, object],
    multipliers: Sequence[float],
    slots: Mapping[date, int],
    weight: float,
) -> float | None:
    """Compatibility wrapper for callers that only need attacking points."""
    blended = _market_attack_blend(priced, position, record, multipliers, slots, weight)
    return blended.points if blended is not None else None


#: How many outfield players a book must have priced before silence about one
#: can mean anything. The live 2026-08-17 scorer market named seventeen Arsenal
#: players but no goalkeeper, then the old eleven-player floor read Raya as
#: dropped. A twenty-player matchday squad normally carries two keepers, so
#: eighteen is the smallest scorer list that can claim complete outfield cover.
CLUB_QUOTE_FLOOR = 18


@dataclass(frozen=True)
class QuotedSquads:
    """Which clubs the book named a squad for, and who it named.

    The only part of a player market this reads that is not a price. A book
    opens a market on players it expects to be available, so a man missing from
    an otherwise complete squad is the market saying he is not playing -- which
    is information last season's appearances cannot hold, and which is not the
    same evidence as the price level that `_market_attacking` already reads.
    """

    #: FPL element ids the book quoted.
    quoted: frozenset[int]
    #: Club short names the book priced a full enough squad for.
    covered: frozenset[str]
    #: Earliest fixture date represented for each club.
    anchors: Mapping[str, date]

    def absent(self, element_id: int, club: str) -> bool:
        return club in self.covered and element_id not in self.quoted


@dataclass(frozen=True)
class MarketShots:
    shots: float | None
    shots_on_target: float | None


PLAYER_MARKET_EVIDENCE_FIELDS = (
    ("anytime_goal", "anytimeGoal", "attacking-participation-bps"),
    ("first_goal", "firstGoal", "corroborating-overlap-not-added"),
    ("last_goal", "lastGoal", "corroborating-overlap-not-added"),
    ("anytime_assist", "anytimeAssist", "attacking-participation-bps"),
    ("any_card", "anyCard", "discipline-bps"),
    ("red_card", "redCard", "discipline-bps"),
    ("shots", "shots", "participation; bps-when-paired"),
    ("shots_on_target", "shotsOnTarget", "availability; bps-when-paired"),
)
PLAYER_MARKET_USAGE = {output: usage for _source, output, usage in PLAYER_MARKET_EVIDENCE_FIELDS}


def _quoted_shots(odds_path: Path) -> dict[int, tuple[MarketShots, date]]:
    if not odds_path.exists():
        return {}
    artifact = read_json_file(odds_path)
    quoted: dict[int, tuple[MarketShots, date]] = {}
    for row in artifact.get("players", []):
        element_id = row.get("element_id")
        kickoff = row.get("kickoff")
        if not isinstance(element_id, int) or not isinstance(kickoff, str):
            continue
        shots = row.get("shots")
        shots_on_target = row.get("shots_on_target")
        if not isinstance(shots, (int, float)) and not isinstance(shots_on_target, (int, float)):
            continue
        try:
            when = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).astimezone(UTC).date()
        except ValueError:
            continue
        quoted[element_id] = (
            MarketShots(
                shots=float(shots) if isinstance(shots, (int, float)) else None,
                shots_on_target=(
                    float(shots_on_target) if isinstance(shots_on_target, (int, float)) else None
                ),
            ),
            when,
        )
    return quoted


def _quoted_squads(odds_path: Path) -> QuotedSquads:
    """Who the book named, by club, when it can be trusted to have named everyone.

    Refused outright when any quoted name failed the crosswalk. An unmatched
    name is a player who *was* priced and is not in `quoted`, so absence would
    read him as dropped -- and the one thing worse than not using this signal is
    using it on the players it is wrong about.
    """
    empty = QuotedSquads(quoted=frozenset(), covered=frozenset(), anchors={})
    if not odds_path.exists():
        return empty
    artifact = read_json_file(odds_path)
    if artifact.get("unmatched"):
        return empty
    quoted: set[int] = set()
    by_club: Counter[str] = Counter()
    anchors: dict[str, date] = {}
    for row in artifact.get("players", []):
        element_id = row.get("element_id")
        club = row.get("club")
        if not isinstance(element_id, int):
            continue
        quoted.add(element_id)
        if isinstance(club, str):
            by_club[club] += 1
            kickoff = row.get("kickoff")
            if isinstance(kickoff, str):
                try:
                    when = (
                        datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                        .astimezone(UTC)
                        .date()
                    )
                except ValueError:
                    continue
                anchors[club] = min(when, anchors.get(club, when))
    return QuotedSquads(
        quoted=frozenset(quoted),
        covered=frozenset(club for club, count in by_club.items() if count >= CLUB_QUOTE_FLOOR),
        anchors=anchors,
    )


def _quoted_cards(odds_path: Path) -> dict[int, tuple[MarketCards, date]]:
    """Bookings the market expects, by element.

    Card routes have no fixture rung to divide out, but the kickoff still
    anchors how their deviation from history decays across future gameweeks.
    """
    if not odds_path.exists():
        return {}
    artifact = read_json_file(odds_path)
    quoted: dict[int, tuple[MarketCards, date]] = {}
    for row in artifact.get("players", []):
        element_id = row.get("element_id")
        kickoff = row.get("kickoff")
        if not isinstance(element_id, int) or not isinstance(kickoff, str):
            continue
        any_card = row.get("any_card")
        red = row.get("red_card")
        try:
            cards = market_cards(
                float(any_card) if isinstance(any_card, (int, float)) else None,
                float(red) if isinstance(red, (int, float)) else None,
            )
        except MarketRoutesError:
            continue
        if cards is not None:
            try:
                when = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).astimezone(UTC).date()
            except ValueError:
                continue
            quoted[element_id] = (cards, when)
    return quoted


def _market_discipline(
    priced: MarketCards | None,
    record: Mapping[str, object],
    weight: float,
) -> tuple[float, float] | None:
    """The yellow and red routes with the market's view of them blended in.

    The book prices "shown a card" without saying which colour, and prices reds
    separately on fewer fixtures. Where both are quoted the split is the
    market's own. Where only the card market is, the player's recorded ratio of
    reds to cards apportions it -- the market says how many, the record says
    what colour, and neither is asked a question it cannot answer.

    Returns points, not rates, because that is what the artifact publishes.
    None wherever nothing is quoted, which leaves the record standing.
    """
    if priced is None:
        return None
    routes = record.get("routes")
    if not isinstance(routes, Mapping):
        return None
    # Published as points; FPL's own table turns them back into rates.
    recorded_yellow = float(str(routes.get("yellowCards", 0.0))) / YELLOW_CARD_POINTS
    recorded_red = float(str(routes.get("redCards", 0.0))) / RED_CARD_POINTS

    if priced.red is not None:
        market_red = priced.red
        market_yellow = max(0.0, priced.cards - priced.red)
    else:
        recorded_total = recorded_yellow + recorded_red
        red_share = recorded_red / recorded_total if recorded_total > 0.0 else 0.0
        market_red = priced.cards * red_share
        market_yellow = priced.cards - market_red

    yellow = blend_rate(max(0.0, recorded_yellow), market_yellow, weight)
    red = blend_rate(max(0.0, recorded_red), market_red, weight)
    return yellow * YELLOW_CARD_POINTS, red * RED_CARD_POINTS


def _schedule(
    raw_fixtures: Sequence[Mapping[str, object]],
    ordered: Sequence[int],
) -> tuple[dict[tuple[int, int], list[tuple[int, bool]]], dict[int, dict[date, int]]]:
    """Who each club plays in each gameweek, and which ladder slot a day sits in.

    The second half is what lets a bookmaker's price find its gameweek. A quote
    carries a kickoff and no gameweek, and the two clocks agree on the date long
    before they agree on the minute, so the day is the join. A club plays at
    most once a day, which is what makes that unambiguous.
    """
    slot_of = {event: slot for slot, event in enumerate(ordered)}
    schedule: dict[tuple[int, int], list[tuple[int, bool]]] = {}
    slots: dict[int, dict[date, int]] = {}
    for row in raw_fixtures:
        event = row["event"]
        if event is None:
            continue
        home_id, away_id = int(str(row["team_h"])), int(str(row["team_a"]))
        schedule.setdefault((int(str(event)), home_id), []).append((away_id, True))
        schedule.setdefault((int(str(event)), away_id), []).append((home_id, False))
        slot = slot_of.get(int(str(event)))
        kickoff = row.get("kickoff_time")
        if slot is None or not isinstance(kickoff, str):
            continue
        try:
            day = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).astimezone(UTC).date()
        except ValueError:
            continue
        for team_id in (home_id, away_id):
            slots.setdefault(team_id, {})[day] = slot
    # A double gameweek's rung is the sum of both fixtures while a book prices
    # one of them, so there is no multiplier to divide a quote by. Dropping the
    # day leaves the record standing rather than publishing a halved market view.
    for team_id, days in slots.items():
        doubled = {
            slot for slot in days.values() if len(schedule.get((ordered[slot], team_id), ())) > 1
        }
        slots[team_id] = {day: slot for day, slot in days.items() if slot not in doubled}
    return schedule, slots


@dataclass(frozen=True)
class MarketFixtureRung:
    view: ClubMatchOdds
    adjustment: RouteAdjustment


def _market_ladder(
    odds_path: Path,
    slots_by_team: Mapping[int, Mapping[date, int]],
    clubs: Mapping[int, Mapping[str, object]],
    ordered: Sequence[int],
) -> dict[tuple[str, int], MarketFixtureRung]:
    """Fixture multipliers a bookmaker wrote, by club short name and gameweek.

    `ingest-odds` has been producing this artifact for four seasons and nothing
    has ever read it. Clean sheets and goals conceded are about a sixth of every
    point FPL awards, they are the two routes a match market prices directly,
    and the fitted strength they were coming from is a shrunk season-long ratio
    that cannot know who is injured.

    Empty whenever the artifact is absent, which is the state between seasons
    and any week the ingest has not run. A double gameweek is skipped: the rung
    is the sum of two fixtures and this keys one price to one rung.
    """
    if not odds_path.exists():
        return {}
    views = club_views(load_fixture_odds(odds_path))
    baseline = market_baseline(view for club in views.values() for view in club)
    if baseline is None:
        return {}
    by_short = {str(team["short_name"]): team_id for team_id, team in clubs.items()}
    rungs: dict[tuple[str, int], MarketFixtureRung] = {}
    seen: set[tuple[str, int]] = set()
    for short, matches in views.items():
        team_id = by_short.get(short)
        slots = slots_by_team.get(team_id) if team_id is not None else None
        if slots is None:
            continue
        for view in matches:
            if view.kickoff is None:
                continue
            slot = slots.get(view.kickoff.astimezone(UTC).date())
            if slot is None or slot >= len(ordered):
                continue
            key = (short, ordered[slot])
            if key in seen:
                rungs.pop(key, None)
                continue
            seen.add(key)
            rungs[key] = MarketFixtureRung(
                view=view,
                adjustment=market_route_adjustment(view, baseline),
            )
    return rungs


@dataclass(frozen=True)
class DepthRolePrior:
    base_points: float
    start_rate: float
    expected_minutes: float
    expected_goals: float
    expected_assists: float
    expected_shots: float | None
    expected_bps: float | None
    bps_deviation: float | None
    routes: Mapping[str, float]

    def as_record(self) -> dict[str, object]:
        return {
            "expectedPoints": self.base_points,
            "probabilityStart": self.start_rate,
            "expectedMinutes": self.expected_minutes,
            "expectedGoals": self.expected_goals,
            "expectedAssists": self.expected_assists,
            "expectedShots": self.expected_shots,
            "expectedBps": self.expected_bps,
            "bpsDeviation": self.bps_deviation,
            "routes": dict(self.routes),
            "evidence": "experimental",
        }


def _priors_by_depth(
    elements: Sequence[BootstrapElement],
    depth: Mapping[int, int],
    record_by_code: Mapping[int, Mapping[str, object]],
) -> dict[tuple[int, int], DepthRolePrior]:
    """What a player of this position and depth rank actually does.

    Measured from the players in this same bootstrap who do have a record, so a
    debutant is described by his role rather than by a number somebody typed.
    The median, not the mean: one rank-one keeper who missed the season with an
    injury should not drag the prior for every other first choice.

    Rank is capped at three by the caller — fourth choice and below all mean
    the same thing, which is "not expected to play".
    """
    grouped: dict[tuple[int, int], list[Mapping[str, object]]] = {}
    for element in elements:
        record = record_by_code.get(element.code)
        if record is None:
            continue
        routes = record.get("routes")
        required = (
            "expectedPoints",
            "probabilityStart",
            "expectedMinutes",
            "expectedGoals",
            "expectedAssists",
        )
        if not isinstance(routes, Mapping) or any(name not in record for name in required):
            continue
        key = (element.element_type, min(depth[element.id], 3))
        grouped.setdefault(key, []).append(record)

    priors: dict[tuple[int, int], DepthRolePrior] = {}
    for key, observed in grouped.items():
        ordered = sorted(observed, key=lambda row: float(str(row["expectedPoints"])))
        record = ordered[len(ordered) // 2]
        routes = record["routes"]
        assert isinstance(routes, Mapping)
        expected_bps = record.get("expectedBps")
        deviation = record.get("bpsDeviation")
        expected_shots = record.get("expectedShots")
        priors[key] = DepthRolePrior(
            base_points=round(float(str(record["expectedPoints"])), 3),
            start_rate=round(float(str(record["probabilityStart"])), 3),
            expected_minutes=round(float(str(record["expectedMinutes"])), 1),
            expected_goals=float(str(record["expectedGoals"])),
            expected_assists=float(str(record["expectedAssists"])),
            expected_shots=(
                float(expected_shots) if isinstance(expected_shots, (int, float)) else None
            ),
            expected_bps=(float(expected_bps) if isinstance(expected_bps, (int, float)) else None),
            bps_deviation=(float(deviation) if isinstance(deviation, (int, float)) else None),
            routes={route: float(str(routes.get(route, 0.0))) for route in ROUTE_KEYS},
        )
    return priors


def _scale_participation(
    routes: Mapping[str, float],
    recorded_minutes: float,
    expected_minutes: float,
    *,
    preserve_attacking: bool = True,
) -> dict[str, float]:
    if recorded_minutes <= 0.0 or expected_minutes == recorded_minutes:
        return dict(routes)
    ratio = expected_minutes / recorded_minutes
    return {
        key: value if preserve_attacking and key == "attacking" else value * ratio
        for key, value in routes.items()
    }


def _market_shot_volume(
    priced: tuple[MarketShots, date] | None,
    multipliers: Sequence[float],
    slots: Mapping[date, int],
) -> MarketShots | None:
    if priced is None:
        return None
    shots, when = priced
    index = slots.get(when)
    if index is None or index >= len(multipliers):
        return None
    multiplier = multipliers[index]
    if multiplier <= 0.0:
        return None
    return MarketShots(
        shots=shots.shots / multiplier if shots.shots is not None else None,
        shots_on_target=(
            shots.shots_on_target / multiplier if shots.shots_on_target is not None else None
        ),
    )


def _bonus_overrides(
    players: Sequence[Mapping[str, object]],
    ordered: Sequence[int],
    raw_fixtures: Sequence[Mapping[str, object]],
    priced_events: set[int],
    ladder: Mapping[str, Mapping[str, Sequence[float]]],
) -> dict[str, dict[str, float]]:
    """Expected bonus by player for complete, market-priced fixtures.

    Bonus is a rank inside one match, so it cannot be a club multiplier. The
    historical route remains the fallback. An override is published only when
    both clubs supply at least a starting eleven with a BPS distribution;
    ranking an incomplete field would award three points simply because the
    missing players were never allowed to compete.
    """
    event_index = {event: index for index, event in enumerate(ordered)}
    overrides: dict[str, dict[str, float]] = {}
    for fixture in raw_fixtures:
        event = fixture.get("event")
        home = fixture.get("team_h")
        away = fixture.get("team_a")
        if not isinstance(event, int) or event not in priced_events:
            continue
        if not isinstance(home, int) or not isinstance(away, int):
            continue
        index = event_index.get(event)
        if index is None:
            continue
        fixture_players: list[Mapping[str, object]] = []
        for team_id in (home, away):
            team_players = [
                player
                for player in players
                if player.get("teamId") == team_id
                and isinstance(player.get("startRate"), (int, float))
            ]
            fixture_players.extend(
                sorted(
                    team_players,
                    key=lambda player: -float(str(player["startRate"])),
                )[:_BONUS_CANDIDATE_FLOOR_PER_CLUB]
            )
        counts = {
            team_id: sum(1 for player in fixture_players if player.get("teamId") == team_id)
            for team_id in (home, away)
        }
        if any(count < _BONUS_CANDIDATE_FLOOR_PER_CLUB for count in counts.values()):
            continue

        candidates: list[BonusCandidate] = []
        for player in fixture_players:
            element_id = player.get("id")
            expected = player.get("_expectedBps", player.get("expectedBps"))
            deviation = player.get("_bpsDeviation", player.get("bpsDeviation"))
            club = player.get("club")
            position = player.get("positionId")
            goals = player.get("_expectedGoals", player.get("expectedGoals"))
            assists = player.get("_expectedAssists", player.get("expectedAssists"))
            routes = player.get("routes")
            if not isinstance(element_id, int) or not isinstance(position, int):
                continue
            if not isinstance(expected, (int, float)) or not isinstance(deviation, (int, float)):
                continue
            if not isinstance(goals, (int, float)) or not isinstance(assists, (int, float)):
                continue
            if not isinstance(club, str) or not isinstance(routes, Mapping):
                continue
            club_ladder = ladder.get(club)
            if club_ladder is None:
                continue
            attacking = club_ladder.get("attacking", ())
            defensive = club_ladder.get("defensive", ())
            if index >= len(attacking) or index >= len(defensive):
                continue
            attack_multiplier = float(attacking[index])
            defence_multiplier = float(defensive[index])
            fixture_bps = float(expected)
            fixture_bps += (
                float(goals) * (attack_multiplier - 1.0) * _BPS_GOAL_POINTS[int(position)]
            )
            fixture_bps += float(assists) * (attack_multiplier - 1.0) * _BPS_ASSIST_POINTS
            if int(position) in (1, 2):
                clean_sheet_points = float(str(routes.get("cleanSheet", 0.0)))
                fixture_bps += clean_sheet_points * (defence_multiplier - 1.0) / 4.0 * 12.0
            candidates.append(
                BonusCandidate(
                    element_id=element_id,
                    expected_bps=fixture_bps,
                    bps_deviation=float(deviation),
                )
            )

        if len(candidates) < _BONUS_CANDIDATE_FLOOR_PER_CLUB * 2:
            continue
        ranked = bonus_expectations(candidates)
        event_rows = overrides.setdefault(str(event), {})
        for element_id, expectation in ranked.items():
            event_rows[str(element_id)] = round(
                event_rows.get(str(element_id), 0.0) + expectation.expected_points,
                3,
            )
    return overrides


@dataclass
class PlayerMarketReach:
    attacking: int = 0
    cards: int = 0
    shots: int = 0
    benched: int = 0
    participation: int = 0


@dataclass
class PlayerDraft:
    element: BootstrapElement
    model_record: Mapping[str, object]
    rated: bool
    start_rate: float
    expected_minutes: float
    expected_goals: float
    expected_assists: float
    expected_shots: float | None
    expected_bps: float | None
    bps_deviation: float | None
    routes: dict[str, float]
    evidence: dict[str, str]


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _initial_player_draft(
    element: BootstrapElement,
    record: Mapping[str, object] | None,
    prior: DepthRolePrior | None,
) -> PlayerDraft | None:
    rated = record is not None
    if record is None:
        if prior is None:
            return None
        model_record: Mapping[str, object] = prior.as_record()
    else:
        model_record = record

    required = ("probabilityStart", "expectedMinutes", "expectedGoals", "expectedAssists")
    missing = [field for field in required if field not in model_record]
    if missing:
        raise ValueError(
            "the projections artifact publishes no "
            + "/".join(missing)
            + "; regenerate it with publish_projections before publishing season inputs"
        )
    model_routes = model_record.get("routes")
    if not isinstance(model_routes, Mapping):
        return None
    evidence: dict[str, str] = {}
    if not rated:
        evidence["all"] = "rolePrior"
    return PlayerDraft(
        element=element,
        model_record=model_record,
        rated=rated,
        start_rate=float(str(model_record["probabilityStart"])),
        expected_minutes=float(str(model_record["expectedMinutes"])),
        expected_goals=float(str(model_record["expectedGoals"])),
        expected_assists=float(str(model_record["expectedAssists"])),
        expected_shots=_optional_float(model_record.get("expectedShots")),
        expected_bps=_optional_float(model_record.get("expectedBps")),
        bps_deviation=_optional_float(model_record.get("bpsDeviation")),
        routes={
            key: value
            for key in ROUTE_KEYS
            if (value := float(str(model_routes.get(key, 0.0)))) != 0.0
        },
        evidence=evidence,
    )


def _apply_attack_market(
    draft: PlayerDraft,
    priced: tuple[MarketAttack, date] | None,
    multipliers: Sequence[float],
    slots: Mapping[date, int],
    weight: float,
) -> tuple[bool, bool]:
    blend = _market_attack_blend(
        priced,
        draft.element.element_type,
        draft.model_record,
        multipliers,
        slots,
        weight,
    )
    if blend is None:
        return False, False
    recorded_minutes = draft.expected_minutes
    recorded_goals = draft.expected_goals
    recorded_assists = draft.expected_assists
    participation = infer_participation(
        recorded_minutes=recorded_minutes,
        recorded_start_probability=draft.start_rate,
        recorded_events=blend.recorded_events,
        market_events=blend.market_events,
        weight=weight,
    )
    ratio = 1.0
    inferred = participation is not None and recorded_minutes > 0.0
    if inferred:
        assert participation is not None
        ratio = participation.expected_minutes / recorded_minutes
        draft.routes = _scale_participation(
            draft.routes,
            recorded_minutes,
            participation.expected_minutes,
        )
        draft.expected_minutes = participation.expected_minutes
        draft.start_rate = participation.start_probability
        draft.evidence["appearance"] = "marketParticipation"
    draft.routes["attacking"] = blend.points
    draft.expected_goals = blend.goals
    draft.expected_assists = blend.assists
    if draft.expected_bps is not None:
        draft.expected_bps *= ratio
        draft.expected_bps += (blend.goals - recorded_goals * ratio) * _BPS_GOAL_POINTS[
            draft.element.element_type
        ]
        draft.expected_bps += (blend.assists - recorded_assists * ratio) * _BPS_ASSIST_POINTS
    draft.evidence["attacking"] = "marketAttack"
    return True, inferred


def _apply_shot_market(
    draft: PlayerDraft,
    priced: tuple[MarketShots, date] | None,
    multipliers: Sequence[float],
    slots: Mapping[date, int],
    weight: float,
    *,
    participation_already_inferred: bool,
) -> tuple[bool, bool]:
    market = _market_shot_volume(priced, multipliers, slots)
    if market is None:
        return False, False
    inferred = False
    if (
        not participation_already_inferred
        and draft.expected_shots is not None
        and draft.expected_shots > 0.0
        and market.shots is not None
        and draft.expected_minutes > 0.0
    ):
        recorded_minutes = draft.expected_minutes
        participation = infer_participation(
            recorded_minutes=recorded_minutes,
            recorded_start_probability=draft.start_rate,
            recorded_events=draft.expected_shots,
            market_events=market.shots,
            weight=weight,
        )
        if participation is not None:
            inferred = True
            ratio = participation.expected_minutes / recorded_minutes
            draft.routes = _scale_participation(
                draft.routes,
                recorded_minutes,
                participation.expected_minutes,
                preserve_attacking=False,
            )
            draft.expected_minutes = participation.expected_minutes
            draft.start_rate = participation.start_probability
            draft.expected_goals *= ratio
            draft.expected_assists *= ratio
            draft.expected_shots *= ratio
            if draft.expected_bps is not None:
                draft.expected_bps *= ratio
            draft.evidence["appearance"] = "shotParticipation"
    bps_applied = _apply_shot_bps(draft, market, weight)
    if market.shots is not None:
        draft.expected_shots = (
            blend_rate(draft.expected_shots, market.shots, weight)
            if draft.expected_shots is not None
            else market.shots
        )
    return inferred or bps_applied, inferred


def _apply_shot_bps(draft: PlayerDraft, market: MarketShots, weight: float) -> bool:
    if (
        draft.expected_bps is None
        or draft.expected_shots is None
        or draft.expected_shots <= 0.0
        or market.shots is None
        or market.shots <= 0.0
        or market.shots_on_target is None
    ):
        return False
    on_target_share = min(1.0, market.shots_on_target / market.shots)
    baseline_on_target = draft.expected_shots * on_target_share
    baseline_shot_bps = 3.0 * baseline_on_target - draft.expected_shots
    market_shot_bps = 3.0 * market.shots_on_target - market.shots
    draft.expected_bps += weight * (market_shot_bps - baseline_shot_bps)
    draft.evidence["bonus"] = "shotBps"
    return True


def _apply_card_market(draft: PlayerDraft, priced: MarketCards | None, weight: float) -> bool:
    baseline_yellow = draft.routes.get("yellowCards", 0.0)
    baseline_red = draft.routes.get("redCards", 0.0)
    blended = _market_discipline(priced, draft.model_record, weight)
    if blended is None:
        return False
    yellow, red = blended
    draft.routes["yellowCards"] = yellow
    draft.routes["redCards"] = red
    if draft.expected_bps is not None:
        draft.expected_bps += (-yellow + baseline_yellow) * -3.0
        draft.expected_bps += ((-red + baseline_red) / 3.0) * -9.0
    for key in ("yellowCards", "redCards"):
        draft.evidence[key] = "marketCards"
    return True


def _omit_from_complete_squad(draft: PlayerDraft, weight: float) -> None:
    draft.start_rate = round(blend_rate(draft.start_rate, 0.0, weight), 3)
    draft.evidence["appearance"] = "marketAbsence"


def _final_player_row(
    draft: PlayerDraft,
    clubs: Mapping[int, Mapping[str, object]],
    depth: Mapping[int, int],
) -> tuple[int, float, dict[str, object]]:
    element = draft.element
    published_routes = {
        key: round(value, 3) for key, value in draft.routes.items() if round(value, 3)
    }
    base_points = round(sum(published_routes.values()), 3)
    payload: dict[str, object] = {
        "id": element.id,
        "code": element.code,
        "name": element.web_name,
        "position": POSITION_CODES[element.element_type],
        "positionId": element.element_type,
        "club": str(clubs[element.team]["short_name"]),
        "teamId": element.team,
        "priceTenths": element.now_cost,
        "basePoints": base_points,
        "routes": published_routes,
        "startRate": round(draft.start_rate, 3),
        "_expectedGoals": round(draft.expected_goals, 3),
        "_expectedAssists": round(draft.expected_assists, 3),
        "_expectedBps": (round(draft.expected_bps, 3) if draft.expected_bps is not None else None),
        "_bpsDeviation": (
            round(draft.bps_deviation, 3) if draft.bps_deviation is not None else None
        ),
        "squadNumber": element.squad_number,
        "rated": draft.rated,
        "depthRank": depth[element.id],
    }
    if draft.evidence:
        payload["evidence"] = draft.evidence
    return element.element_type, base_points, payload


def _projection_records(
    artifact: Mapping[str, object], shot_rates: Mapping[int, float]
) -> dict[int, Mapping[str, object]]:
    records: dict[int, Mapping[str, object]] = {}
    rows = artifact.get("players")
    if not isinstance(rows, list):
        raise ValueError("the projections artifact publishes no players list")
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        code = int(str(row["code"]))
        enriched = dict(row)
        routes = row.get("routes")
        expected_points = row.get("expectedPoints")
        if isinstance(routes, Mapping) and isinstance(expected_points, (int, float)):
            route_total = sum(float(str(routes.get(route, 0.0))) for route in ROUTE_KEYS)
            scale = float(expected_points) / route_total if route_total else 1.0
            enriched["routes"] = {
                route: float(str(routes.get(route, 0.0))) * scale for route in ROUTE_KEYS
            }
            for field in ("expectedGoals", "expectedAssists", "expectedBps", "bpsDeviation"):
                value = row.get(field)
                if isinstance(value, (int, float)):
                    enriched[field] = float(value) * scale
        rate = shot_rates.get(code)
        minutes = row.get("expectedMinutes")
        if rate is not None and isinstance(minutes, (int, float)):
            enriched["expectedShots"] = rate * float(minutes) / 90.0
        records[code] = enriched
    return records


def _complete_strength(
    clubs: Mapping[int, Mapping[str, object]],
    measured: Mapping[int, TeamStrength],
) -> dict[int, TeamStrength]:
    strength = dict(measured)
    for team_id, team in clubs.items():
        if team_id not in strength:
            published = published_strength(team, list(clubs.values()))
            strength[team_id] = published if published is not None else PROMOTED_STRENGTH
    return strength


@dataclass(frozen=True)
class FixtureLadders:
    routes: dict[str, dict[str, list[float]]]
    ratings: dict[str, list[float | None]]
    opponents: dict[str, list[list[str]]]
    market_rungs: int
    market_evidence: dict[str, list[dict[str, object]]]


def _fixture_adjustment_sum(
    games: Sequence[tuple[int, bool]],
    *,
    team_id: int,
    event: int,
    short_name: object,
    strength: Mapping[int, TeamStrength],
    market: Mapping[tuple[str, int], MarketFixtureRung],
) -> tuple[
    float,
    float,
    float,
    float,
    float,
    int,
    tuple[RouteAdjustment, ...],
    tuple[MarketFixtureRung, ...],
]:
    values = [0.0, 0.0, 0.0, 0.0, 0.0]
    priced_count = 0
    adjustments: list[RouteAdjustment] = []
    market_matches: list[MarketFixtureRung] = []
    for opponent, home in games:
        priced = market.get((str(short_name), event))
        if priced is not None:
            adjustment = priced.adjustment
            priced_count += 1
            market_matches.append(priced)
        else:
            adjustment = route_adjustment(strength, team_id, opponent, home=home)
        adjustments.append(adjustment)
        for index, value in enumerate(
            (
                adjustment.clean_sheet,
                adjustment.attacking,
                adjustment.saves,
                adjustment.conceding,
                adjustment.defensive_contribution,
            )
        ):
            values[index] += value
    return (
        values[0],
        values[1],
        values[2],
        values[3],
        values[4],
        priced_count,
        tuple(adjustments),
        tuple(market_matches),
    )


def _fixture_ladders(
    clubs: Mapping[int, Mapping[str, object]],
    ordered: Sequence[int],
    schedule: Mapping[tuple[int, int], Sequence[tuple[int, bool]]],
    strength: Mapping[int, TeamStrength],
    market: Mapping[tuple[str, int], MarketFixtureRung],
) -> FixtureLadders:
    ladders: dict[str, dict[str, list[float]]] = {}
    ratings: dict[str, list[float | None]] = {}
    opponents: dict[str, list[list[str]]] = {}
    market_evidence: dict[str, list[dict[str, object]]] = {}
    market_rungs = 0
    for team_id, team in clubs.items():
        route_rows: list[list[float]] = [[] for _ in range(5)]
        difficulty: list[float | None] = []
        against: list[list[str]] = []
        for event in ordered:
            games = schedule.get((event, team_id), ())
            *values, priced, adjustments, market_matches = _fixture_adjustment_sum(
                games,
                team_id=team_id,
                event=event,
                short_name=team["short_name"],
                strength=strength,
                market=market,
            )
            market_rungs += priced
            for rows, value in zip(route_rows, values, strict=True):
                rows.append(round(value, 3))
            difficulty.append(adjustment_difficulty(adjustments))
            for market_match in market_matches:
                raw_difficulty = adjustment_difficulty(
                    [market_match.adjustment],
                    bounded=False,
                )
                summary_difficulty = adjustment_difficulty([market_match.adjustment])
                market_evidence.setdefault(str(team["short_name"]), []).append(
                    {
                        "event": event,
                        "opponent": market_match.view.opponent,
                        "venue": "H" if market_match.view.home else "A",
                        "kickoff": (
                            None
                            if market_match.view.kickoff is None
                            else market_match.view.kickoff.isoformat()
                        ),
                        "expectedGoals": round(market_match.view.expected_goals, 4),
                        "opponentExpectedGoals": round(
                            market_match.view.opponent_expected_goals,
                            4,
                        ),
                        "cleanSheetProbability": round(
                            market_match.view.clean_sheet,
                            4,
                        ),
                        "adjustments": {
                            "attacking": round(market_match.adjustment.attacking, 3),
                            "cleanSheet": round(market_match.adjustment.clean_sheet, 3),
                            "conceding": round(market_match.adjustment.conceding, 3),
                            "saves": round(market_match.adjustment.saves, 3),
                            "defensiveContribution": round(
                                market_match.adjustment.defensive_contribution,
                                3,
                            ),
                        },
                        "difficulty": {
                            "raw": raw_difficulty,
                            "summary": summary_difficulty,
                            "clipped": raw_difficulty != summary_difficulty,
                        },
                    }
                )
            against.append(
                [
                    f"{clubs[opponent]['short_name']} ({'H' if home else 'A'})"
                    for opponent, home in games
                ]
            )
        short = str(team["short_name"])
        ladders[short] = dict(
            zip(
                ("defensive", "attacking", "saves", "conceding", "defensiveContribution"),
                route_rows,
                strict=True,
            )
        )
        ratings[short] = difficulty
        opponents[short] = against
    return FixtureLadders(ladders, ratings, opponents, market_rungs, market_evidence)


def _build_player_rows(
    available: Sequence[BootstrapElement],
    *,
    depth: Mapping[int, int],
    records: Mapping[int, Mapping[str, object]],
    priors: Mapping[tuple[int, int], DepthRolePrior],
    quoted_attack: Mapping[int, tuple[MarketAttack, date]],
    quoted_cards: Mapping[int, tuple[MarketCards, date]],
    quoted_shots: Mapping[int, tuple[MarketShots, date]],
    squads: QuotedSquads,
    ladder: Mapping[str, Mapping[str, Sequence[float]]],
    slots_by_team: Mapping[int, Mapping[date, int]],
    clubs: Mapping[int, Mapping[str, object]],
    weight: float,
) -> tuple[
    list[tuple[int, float, dict[str, object]]],
    PlayerMarketReach,
    dict[int, list[float]],
]:
    players: list[tuple[int, float, dict[str, object]]] = []
    reach = PlayerMarketReach()
    carry: dict[int, list[float]] = {}
    for element in available:
        prior = priors.get((element.element_type, min(depth[element.id], 3)))
        draft = _initial_player_draft(element, records.get(element.code), prior)
        if draft is None:
            continue
        baseline_start_rate = draft.start_rate
        baseline_minutes = draft.expected_minutes
        baseline_routes = dict(draft.routes)
        club = str(clubs[element.team]["short_name"])
        attack_multipliers = ladder.get(club, {}).get("attacking", ())
        slots = slots_by_team.get(element.team, {})
        attack_quote = quoted_attack.get(element.id)
        shot_quote = quoted_shots.get(element.id)
        card_quote = quoted_cards.get(element.id)
        attacked, attack_participation = _apply_attack_market(
            draft,
            attack_quote,
            attack_multipliers,
            slots,
            weight,
        )
        shot, shot_participation = _apply_shot_market(
            draft,
            shot_quote,
            attack_multipliers,
            slots,
            weight,
            participation_already_inferred=attack_participation,
        )
        reach.attacking += int(attacked)
        reach.shots += int(shot)
        reach.participation += int(attack_participation or shot_participation)
        carded = _apply_card_market(
            draft,
            card_quote[0] if card_quote is not None else None,
            weight,
        )
        reach.cards += int(carded)
        absent = squads.absent(element.id, club)
        if absent:
            reach.benched += 1
            _omit_from_complete_squad(draft, weight)
        anchor_dates = [
            quote[1] for quote in (attack_quote, shot_quote, card_quote) if quote is not None
        ]
        squad_anchor = squads.anchors.get(club) if absent else None
        if squad_anchor is not None:
            anchor_dates.append(squad_anchor)
        anchor_indices = [slots[when] for when in anchor_dates if when in slots]
        touched = attacked or shot or carded or absent
        if touched and anchor_indices and baseline_minutes > 0.0:
            carry[element.id] = [
                float(min(anchor_indices)),
                round(baseline_start_rate, 3),
                round(draft.expected_minutes / baseline_minutes, 6),
                round(baseline_routes.get("attacking", 0.0), 3),
                round(baseline_routes.get("yellowCards", 0.0), 3),
                round(baseline_routes.get("redCards", 0.0), 3),
            ]
        players.append(_final_player_row(draft, clubs, depth))
    return players, reach, carry


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    projections_path = Path(args.projections)
    player_odds_path = Path(args.player_odds)
    fixture_odds_path = Path(args.fixture_odds)
    understat_path = Path(args.understat)
    artifact = read_json_file(projections_path)
    shot_rates = _understat_shots(understat_path)
    record_by_code = _projection_records(artifact, shot_rates)
    strength_by_code = {
        int(row["code"]): TeamStrength(
            attack_home=row["attackHome"],
            attack_away=row["attackAway"],
            defence_home=row["defenceHome"],
            defence_away=row["defenceAway"],
        )
        for row in artifact.get("clubs", ())
    }

    bootstrap = _get(BOOTSTRAP)
    assert isinstance(bootstrap, dict)
    clubs = {int(team["id"]): team for team in bootstrap["teams"]}
    measured_strength = {
        team_id: strength_by_code[int(team["code"])]
        for team_id, team in clubs.items()
        if int(team["code"]) in strength_by_code
    }
    # A club with no Premier League record is rated on FPL's own published
    # strength, which it sets for all twenty before a ball is kicked. Those
    # fields were ingested and read by nothing, and a hand-picked constant for
    # every promoted side is a default standing in for a source that exists.
    strength = _complete_strength(clubs, measured_strength)

    events = {int(event["id"]): event for event in bootstrap["events"] if not event.get("finished")}
    if not events:
        print("every gameweek is finished; nothing to solve", file=sys.stderr)
        return 1
    ordered = sorted(events)

    raw_fixtures = _get(FIXTURES)
    assert isinstance(raw_fixtures, list)
    schedule, slots_by_team = _schedule(raw_fixtures, ordered)

    market = _market_ladder(fixture_odds_path, slots_by_team, clubs, ordered)
    fixture_ladders = _fixture_ladders(clubs, ordered, schedule, strength, market)
    ladder = fixture_ladders.routes
    ratings = fixture_ladders.ratings
    opponents = fixture_ladders.opponents
    market_rungs = fixture_ladders.market_rungs
    market_evidence = fixture_ladders.market_evidence

    available = [
        element
        for element in parse_elements(bootstrap["elements"], model=BootstrapElement)
        if element.element_type in POSITION_CODES and element.is_available
    ]

    # Where a player sits in his club's queue for a shirt, read from FPL's own
    # prices. FPL prices the intended starter above his understudy, and that
    # ordering is published before a ball is kicked.
    depth: dict[int, int] = {}
    by_squad: dict[tuple[int, int], list[BootstrapElement]] = {}
    for element in available:
        by_squad.setdefault((element.team, element.element_type), []).append(element)
    for squad in by_squad.values():
        for element in squad:
            depth[element.id] = 1 + sum(1 for other in squad if other.now_cost > element.now_cost)

    priors = _priors_by_depth(available, depth, record_by_code)
    quoted_attack = _quoted_attack(player_odds_path)
    quoted_cards = _quoted_cards(player_odds_path)
    quoted_shots = _quoted_shots(player_odds_path)
    squads = _quoted_squads(player_odds_path)
    players, player_reach, market_carry = _build_player_rows(
        available,
        depth=depth,
        records=record_by_code,
        priors=priors,
        quoted_attack=quoted_attack,
        quoted_cards=quoted_cards,
        quoted_shots=quoted_shots,
        squads=squads,
        ladder=ladder,
        slots_by_team=slots_by_team,
        clubs=clubs,
        weight=args.market_weight,
    )

    # The browser solve starts from the published opening squad, so every one of
    # its fifteen has to be here. A cheap bench enabler is chosen for what he
    # costs, not what he scores, and would never survive a top-forty cut.
    opening = read_json_file(Path(args.opening_squad))
    required = {int(pick["code"]) for pick in opening["picks"]}

    trimmed: list[dict[str, object]] = []
    for position in sorted(POSITION_CODES):
        ranked = sorted(
            (row for row in players if row[0] == position),
            key=lambda row: -row[1],
        )
        chosen = ranked[:POOL_PER_POSITION]
        chosen.extend(row for row in ranked[POOL_PER_POSITION:] if row[2]["code"] in required)
        trimmed.extend(payload for _, _, payload in chosen)

    absent = required - {int(str(payload["code"])) for payload in trimmed}
    if absent:
        raise ValueError(f"opening squad players missing from the solver pool: {sorted(absent)}")

    bonus_overrides = _bonus_overrides(
        trimmed,
        ordered,
        raw_fixtures,
        {event for _, event in market},
        ladder,
    )
    for player in trimmed:
        for key in [name for name in player if name.startswith("_")]:
            del player[key]
    trimmed_ids = {int(str(player["id"])) for player in trimmed}
    market_carry = {
        element_id: values
        for element_id, values in market_carry.items()
        if element_id in trimmed_ids
    }
    fixture_provenance = _artifact_provenance(
        fixture_odds_path,
        source="football-data.co.uk",
        default_level="observed",
    )

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "recordSeason": str(artifact["season"]),
        "events": ordered,
        "deadlines": [
            str(events[event]["deadline_time"]).replace("+00:00", "Z") for event in ordered
        ],
        "basis": (
            "base projection per player, multiplied by the club's fixture "
            "multiplier for the gameweek; blanks are zero and doubles are summed"
        ),
        "poolPerPosition": POOL_PER_POSITION,
        "evidence": {
            "historicalProjection": _artifact_provenance(
                projections_path,
                source="fpl-history-corpus",
                default_level="inferred",
            ),
            "playerMarkets": _artifact_provenance(
                player_odds_path,
                source="the-odds-api",
                default_level="observed",
            ),
            "fixtureMarkets": fixture_provenance,
            "understat": _artifact_provenance(
                understat_path,
                source="understat",
                default_level="inferred",
            ),
        },
        "evidenceDefinitions": {
            "rolePrior": {
                "level": "experimental",
                "sources": ["position-depth-role-prior"],
                "reasons": ["no-player-record"],
            },
            "marketParticipation": {
                "level": "experimental",
                "sources": ["historical-projection", "the-odds-api"],
                "reasons": ["market-implied-participation"],
            },
            "marketAttack": {
                "level": "inferred",
                "sources": ["historical-projection", "the-odds-api"],
                "reasons": ["anytime-probability-poisson-inversion"],
            },
            "shotParticipation": {
                "level": "experimental",
                "sources": ["understat", "the-odds-api"],
                "reasons": ["shot-market-implied-participation"],
            },
            "shotBps": {
                "level": "experimental",
                "sources": ["understat", "the-odds-api", "fpl-bps-rules"],
                "reasons": ["shot-volume-and-on-target-bps"],
            },
            "marketCards": {
                "level": "inferred",
                "sources": ["historical-projection", "the-odds-api"],
                "reasons": ["card-probability-poisson-inversion"],
            },
            "marketAbsence": {
                "level": "inferred",
                "sources": ["historical-projection", "the-odds-api"],
                "reasons": ["absent-from-complete-quoted-squad"],
            },
        },
        # How much of the market actually reached this run. Printed to stderr
        # for months while the page went on describing a bookmaker's
        # contribution in the present tense -- and the whole path was a no-op,
        # so every one of these was zero and nothing on the site could tell.
        # Published so the claim can be derived from the evidence instead of
        # asserted beside it.
        "market": {
            "attackingRoutes": player_reach.attacking,
            "playersQuoted": len(quoted_attack),
            "cardRoutes": player_reach.cards,
            "playersQuotedForCards": len(quoted_cards),
            "shotRoutes": player_reach.shots,
            "playersQuotedForShots": len(quoted_shots),
            "startRatesCut": player_reach.benched,
            "squadsNamed": len(squads.covered),
            "fixtureRungs": market_rungs,
            "participationInferred": player_reach.participation,
            "bonusEvents": len(bonus_overrides),
            "playerMarketUsage": PLAYER_MARKET_USAGE,
        },
        "marketCarry": {
            "halfLifeGameweeks": MARKET_CARRY_HALF_LIFE_GAMEWEEKS,
            "fields": [
                "anchorIndex",
                "baselineStartRate",
                "participationRatio",
                "baselineAttacking",
                "baselineYellowCards",
                "baselineRedCards",
            ],
            "players": market_carry,
        },
        # Read from FPL's own bootstrap, not retyped in TypeScript. The browser
        # solver declared the squad shape, the weekly award, the cap and the
        # hit as literals with a prose citation and no timestamp, which is the
        # one thing this repository says it never does with a controlling rule.
        "rules": {
            "weeklyFreeTransfers": WEEKLY_FREE_TRANSFERS,
            "maximumFreeTransfers": WEEKLY_FREE_TRANSFERS
            + _setting(bootstrap, "max_extra_free_transfers"),
            "transferCostPoints": TRANSFER_COST_POINTS,
            "transferCap": _setting(bootstrap, "transfers_cap"),
            "squadSize": _setting(bootstrap, "squad_squadsize"),
            "lineupSize": _setting(bootstrap, "squad_squadplay"),
            "clubLimit": _setting(bootstrap, "squad_team_limit"),
            "positions": [
                {
                    "positionId": position,
                    "squadCount": count,
                    "lineupMinimum": LINEUP_RANGE[position][0],
                    "lineupMaximum": LINEUP_RANGE[position][1],
                }
                for position, count in sorted(SQUAD_SHAPE.items())
            ],
            "sourceReference": args.rules_reference,
            "dataAvailableAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "playableStartRate": PLAYABLE_START_RATE,
            "transferMarginPoints": TransferPlanSettings().margin,
        },
        "fixtureLadder": ladder,
        "fixtureDifficulty": ratings,
        "fixtureEvidence": {
            "source": fixture_provenance["source"],
            "updatedAt": fixture_provenance["updatedAt"],
            "level": fixture_provenance["level"],
            "byClub": market_evidence,
        },
        "opponents": opponents,
        "bonusOverrides": bonus_overrides,
        "players": trimmed,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    size = output.stat().st_size / 1024
    print(
        f"wrote {output} — {len(trimmed)} players, {len(ordered)} gameweeks, "
        f"{len(ladder)} clubs, {size:.1f} kB"
    )
    # Said out loud because the last market blend here was a no-op for months:
    # it looked up a projection field that the projector never published, so it
    # returned nothing for everyone and nothing said so.
    print(
        f"market: {player_reach.attacking} attacking routes blended from "
        f"{len(quoted_attack)} players quoted; {player_reach.cards} card routes "
        f"from {len(quoted_cards)} quoted; {player_reach.benched} start rates cut "
        f"by a book that named {len(squads.covered)} full squads"
        f"; {market_rungs} fixture rungs priced by a bookmaker"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
