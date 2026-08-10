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
import json
import sys
import urllib.request
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from fpl_andres import timeouts
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
from fpl_andres.models.fixture_odds import club_views, load_fixture_odds
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
    fixture_difficulty,
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
DEFAULT_OUTPUT = Path("apps/web/src/data/season-inputs.json")

SCHEMA_VERSION = 2
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

#: How many of each position may start, from the published rules.
LINEUP_RANGE = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}

#: How many of each position a squad holds.
SQUAD_SHAPE = {1: 2, 2: 5, 3: 5, 4: 3}

#: FPL awards one a week. The number is in the rules page, not the bootstrap.
WEEKLY_FREE_TRANSFERS = 1


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


def _market_attacking(
    priced: tuple[MarketAttack, date] | None,
    position: int,
    record: Mapping[str, object],
    multipliers: Sequence[float],
    slots: Mapping[date, int],
    weight: float,
) -> float | None:
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
    goals = float(str(record["expectedGoals"]))
    assists = float(str(record["expectedAssists"]))
    if attack.goals is not None:
        goals = blend_rate(goals, attack.goals / multiplier, weight)
    if attack.assists is not None:
        assists = blend_rate(assists, attack.assists / multiplier, weight)
    return goals * goal_points + assists * ASSIST_POINTS


#: How many of a club's players a book must have priced before its silence about
#: one of them means anything. A book that has opened an anytime-scorer market
#: prices the whole matchday squad, so anything under a starting eleven is a
#: partial read rather than a team sheet, and reading absence off it would bench
#: a defender because the book only quoted the strikers.
CLUB_QUOTE_FLOOR = 11


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

    def absent(self, element_id: int, club: str) -> bool:
        return club in self.covered and element_id not in self.quoted


def _quoted_squads(odds_path: Path) -> QuotedSquads:
    """Who the book named, by club, when it can be trusted to have named everyone.

    Refused outright when any quoted name failed the crosswalk. An unmatched
    name is a player who *was* priced and is not in `quoted`, so absence would
    read him as dropped -- and the one thing worse than not using this signal is
    using it on the players it is wrong about.
    """
    empty = QuotedSquads(quoted=frozenset(), covered=frozenset())
    if not odds_path.exists():
        return empty
    artifact = read_json_file(odds_path)
    if artifact.get("unmatched"):
        return empty
    quoted: set[int] = set()
    by_club: Counter[str] = Counter()
    for row in artifact.get("players", []):
        element_id = row.get("element_id")
        club = row.get("club")
        if not isinstance(element_id, int):
            continue
        quoted.add(element_id)
        if isinstance(club, str):
            by_club[club] += 1
    return QuotedSquads(
        quoted=frozenset(quoted),
        covered=frozenset(club for club, count in by_club.items() if count >= CLUB_QUOTE_FLOOR),
    )


def _quoted_cards(odds_path: Path) -> dict[int, MarketCards]:
    """Bookings the market expects, by element.

    No kickoff travels with these. The attacking routes are de-fixtured by the
    gameweek's own multiplier before publishing, because the ladder has one; the
    card routes have no rung, so there is nothing to divide out and nothing to
    correct with. What is published is therefore a fixture's booking rate read
    as if it were an average one, which flatters a player quoted in a derby and
    is stated here rather than hidden. It is bounded by the blend weight.
    """
    if not odds_path.exists():
        return {}
    artifact = read_json_file(odds_path)
    quoted: dict[int, MarketCards] = {}
    for row in artifact.get("players", []):
        element_id = row.get("element_id")
        if not isinstance(element_id, int):
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
            quoted[element_id] = cards
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


def _market_ladder(
    odds_path: Path,
    slots_by_team: Mapping[int, Mapping[date, int]],
    clubs: Mapping[int, Mapping[str, object]],
    ordered: Sequence[int],
) -> dict[tuple[str, int], RouteAdjustment]:
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
    rungs: dict[tuple[str, int], RouteAdjustment] = {}
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
            rungs[key] = market_route_adjustment(view, baseline)
    return rungs


def _priors_by_depth(
    elements: Sequence[BootstrapElement],
    depth: Mapping[int, int],
    record_by_code: Mapping[int, Mapping[str, object]],
) -> dict[tuple[int, int], tuple[float, float]]:
    """What a player of this position and depth rank actually does.

    Measured from the players in this same bootstrap who do have a record, so a
    debutant is described by his role rather than by a number somebody typed.
    The median, not the mean: one rank-one keeper who missed the season with an
    injury should not drag the prior for every other first choice.

    Rank is capped at three by the caller — fourth choice and below all mean
    the same thing, which is "not expected to play".
    """
    grouped: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for element in elements:
        record = record_by_code.get(element.code)
        if record is None:
            continue
        key = (element.element_type, min(depth[element.id], 3))
        grouped.setdefault(key, []).append(
            (
                float(str(record["expectedPoints"])),
                float(str(record["probabilityStart"])),
            )
        )

    priors: dict[tuple[int, int], tuple[float, float]] = {}
    for key, observed in grouped.items():
        points = sorted(value for value, _ in observed)
        starts = sorted(value for _, value in observed)
        middle = len(points) // 2
        priors[key] = (round(points[middle], 3), round(starts[middle], 3))
    return priors


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

    bootstrap = _get(BOOTSTRAP)
    assert isinstance(bootstrap, dict)
    clubs = {int(team["id"]): team for team in bootstrap["teams"]}
    strength = {
        team_id: strength_by_code[int(team["code"])]
        for team_id, team in clubs.items()
        if int(team["code"]) in strength_by_code
    }
    # A club with no Premier League record is rated on FPL's own published
    # strength, which it sets for all twenty before a ball is kicked. Those
    # fields were ingested and read by nothing, and a hand-picked constant for
    # every promoted side is a default standing in for a source that exists.
    for team_id, team in clubs.items():
        if team_id in strength:
            continue
        published = published_strength(team, list(clubs.values()))
        strength[team_id] = published if published is not None else PROMOTED_STRENGTH

    events = {int(event["id"]): event for event in bootstrap["events"] if not event.get("finished")}
    if not events:
        print("every gameweek is finished; nothing to solve", file=sys.stderr)
        return 1
    ordered = sorted(events)

    raw_fixtures = _get(FIXTURES)
    assert isinstance(raw_fixtures, list)
    schedule, slots_by_team = _schedule(raw_fixtures, ordered)

    # Two multipliers per club per gameweek: one for players who score by
    # keeping goals out, one for players who score by putting them in. A blank
    # gameweek is zero, and a double is the sum of both fixtures.
    ladder: dict[str, dict[str, list[float]]] = {}
    # "HUL (A)" per club per gameweek, so a solved card can name the opponent
    # rather than repeat the club whose shirt is already drawn beside the player.
    opponents: dict[str, list[list[str]]] = {}
    # One to five per club per gameweek, to a tenth, the measured difficulty.
    ratings: dict[str, list[float | None]] = {}
    market = _market_ladder(Path(args.fixture_odds), slots_by_team, clubs, ordered)
    market_rungs = 0
    for team_id, team in clubs.items():
        defensive: list[float] = []
        attacking: list[float] = []
        saving: list[float] = []
        conceding: list[float] = []
        defcon: list[float] = []
        difficulty: list[float | None] = []
        against: list[list[str]] = []
        for event in ordered:
            games = schedule.get((event, team_id), ())
            back = 0.0
            front = 0.0
            saves = 0.0
            leak = 0.0
            contribution = 0.0
            for opponent, home in games:
                # A book prices Saturday with the injuries and the rotation
                # already in the number, where the fitted strength prices the
                # average meeting of two clubs. Where the market has priced
                # this fixture it is the better estimate of the same thing.
                priced = market.get((team["short_name"], event))
                if priced is not None:
                    adjustment = priced
                    market_rungs += 1
                elif team_id not in strength:
                    back += 1.0
                    front += 1.0
                    saves += 1.0
                    leak += 1.0
                    contribution += 1.0
                    continue
                else:
                    # Every club is rated now: measured where there is a record,
                    # and on FPL's published strength where there is not.
                    adjustment = route_adjustment(strength, team_id, opponent, home=home)
                back += adjustment.clean_sheet
                front += adjustment.attacking
                saves += adjustment.saves
                leak += adjustment.conceding
                contribution += adjustment.defensive_contribution
            defensive.append(round(back, 3))
            attacking.append(round(front, 3))
            saving.append(round(saves, 3))
            conceding.append(round(leak, 3))
            defcon.append(round(contribution, 3))
            difficulty.append(fixture_difficulty(games, team_id, strength))
            against.append(
                [
                    f"{clubs[opponent]['short_name']} ({'H' if home else 'A'})"
                    for opponent, home in games
                ]
            )
        ladder[str(team["short_name"])] = {
            "defensive": defensive,
            "attacking": attacking,
            "saves": saving,
            "conceding": conceding,
            "defensiveContribution": defcon,
        }
        ratings[str(team["short_name"])] = difficulty
        opponents[str(team["short_name"])] = against

    players: list[tuple[int, float, dict[str, object]]] = []
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
    quoted_attack = _quoted_attack(Path(args.player_odds))
    quoted_cards = _quoted_cards(Path(args.player_odds))
    squads = _quoted_squads(Path(args.player_odds))
    priced_attack = 0
    priced_cards = 0
    benched = 0

    for element in available:
        record = record_by_code.get(element.code)
        rated = record is not None
        if rated:
            assert record is not None
            base_points = round(float(record["expectedPoints"]), 3)
            start_rate = round(float(record["probabilityStart"]), 3)
            # Every route, so the browser can bend each by its own fixture
            # multiplier. Applying one multiplier to the whole total priced a
            # defender's assists by his side's defensive difficulty and a
            # keeper's saves as if they were clean sheets.
            #
            # Zeroes are omitted and three decimals kept: a route worth nothing
            # needs no key, and the fourth decimal of a projection is well past
            # anything it can support. Together they hold the browser chunk
            # inside its budget.
            routes = {
                key: value
                for key in ROUTE_KEYS
                if (value := round(float(record["routes"][key]), 3))
            }
            # Where a book priced him to score, to assist or to be booked, its
            # view of those replaces part of the record's. Everything else on
            # the row is left alone: no market here prices a clean sheet for a
            # named player, a bonus point or a defensive contribution, and
            # inventing one would be worse than the measurement already there.
            blended_attack = _market_attacking(
                quoted_attack.get(element.id),
                element.element_type,
                record,
                ladder.get(str(clubs[element.team]["short_name"]), {}).get("attacking", ()),
                slots_by_team.get(element.team, {}),
                args.market_weight,
            )
            if blended_attack is not None:
                priced_attack += 1
                routes["attacking"] = round(blended_attack, 3)
            blended_cards = _market_discipline(
                quoted_cards.get(element.id), record, args.market_weight
            )
            if blended_cards is not None:
                priced_cards += 1
                yellow, red = blended_cards
                routes["yellowCards"] = round(yellow, 3)
                routes["redCards"] = round(red, 3)
        else:
            # No Premier League record at all. He is still pickable — somebody
            # will own him — but every number here is a prior taken from what
            # players at his depth rank and position actually do, not a
            # measurement of him.
            prior = priors.get((element.element_type, min(depth[element.id], 3)))
            if prior is None:
                continue
            base_points, start_rate = prior
            # A role prior has no route split to give, so the whole figure is
            # carried on the route his position is scored by. Splitting it any
            # further would be inventing a shape nobody measured.
            attacking_role = element.element_type in (3, 4)
            routes = {("attacking" if attacking_role else "cleanSheet"): round(base_points, 3)}
        # Applies to a rated player and to a prior alike: the book's silence is
        # about the man, not about how much history he has. Only downward --
        # being quoted proves he is in the squad, which the record already
        # implies, while being missing from a squad the book otherwise named in
        # full is the one thing last season cannot know.
        if squads.absent(element.id, str(clubs[element.team]["short_name"])):
            benched += 1
            start_rate = round(blend_rate(start_rate, 0.0, args.market_weight), 3)
        players.append(
            (
                element.element_type,
                base_points,
                {
                    "id": element.id,
                    "code": element.code,
                    "name": element.web_name,
                    "position": POSITION_CODES[element.element_type],
                    "positionId": element.element_type,
                    "club": str(clubs[element.team]["short_name"]),
                    "teamId": element.team,
                    "priceTenths": element.now_cost,
                    "basePoints": base_points,
                    "routes": routes,
                    "startRate": round(start_rate, 3),
                    "squadNumber": element.squad_number,
                    "rated": rated,
                    "depthRank": depth[element.id],
                },
            )
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
        # How much of the market actually reached this run. Printed to stderr
        # for months while the page went on describing a bookmaker's
        # contribution in the present tense -- and the whole path was a no-op,
        # so every one of these was zero and nothing on the site could tell.
        # Published so the claim can be derived from the evidence instead of
        # asserted beside it.
        "market": {
            "attackingRoutes": priced_attack,
            "playersQuoted": len(quoted_attack),
            "cardRoutes": priced_cards,
            "playersQuotedForCards": len(quoted_cards),
            "startRatesCut": benched,
            "squadsNamed": len(squads.covered),
            "fixtureRungs": market_rungs,
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
        "opponents": opponents,
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
        f"market: {priced_attack} attacking routes blended from {len(quoted_attack)} players quoted"
        f"; {priced_cards} card routes from {len(quoted_cards)} quoted"
        f"; {benched} start rates cut by a book that named {len(squads.covered)} full squads"
        f"; {market_rungs} fixture rungs priced by a bookmaker"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
