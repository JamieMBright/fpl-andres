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
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres import timeouts
from fpl_andres.backtesting.fixtures import TeamStrength, route_adjustment
from fpl_andres.bootstrap import BootstrapElement, parse_elements
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.planning.fixture_routes import (
    PROMOTED_STRENGTH,
    ROUTE_KEYS,
    fixture_difficulty,
)
from fpl_andres.planning.opening import PLAYABLE_START_RATE
from fpl_andres.planning.transfers import TransferPlanSettings
from fpl_andres.positions import Position

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
PROJECTIONS = Path("apps/web/src/data/projections.json")
OPENING_SQUAD = Path("apps/web/src/data/opening-squad.json")
DEFAULT_OUTPUT = Path("apps/web/src/data/season-inputs.json")

SCHEMA_VERSION = 1
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
    return parser


def _get(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
        return parse_json(response.read().decode("utf-8"), source=url)


# Where the measured tie sits on the published one-to-five scale. A fixture is
# rated on both halves of it: what this side is likely to score and what it is
# likely to concede, at the venue it is played. Blanks are None, not three:
# there is no fixture to be difficult.


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

    events = {int(event["id"]): event for event in bootstrap["events"] if not event.get("finished")}
    if not events:
        print("every gameweek is finished; nothing to solve", file=sys.stderr)
        return 1
    ordered = sorted(events)

    raw_fixtures = _get(FIXTURES)
    assert isinstance(raw_fixtures, list)
    schedule: dict[tuple[int, int], list[tuple[int, bool]]] = {}
    for row in raw_fixtures:
        event = row["event"]
        if event is None:
            continue
        home_id, away_id = int(row["team_h"]), int(row["team_a"])
        schedule.setdefault((int(event), home_id), []).append((away_id, True))
        schedule.setdefault((int(event), away_id), []).append((home_id, False))

    # Two multipliers per club per gameweek: one for players who score by
    # keeping goals out, one for players who score by putting them in. A blank
    # gameweek is zero, and a double is the sum of both fixtures.
    ladder: dict[str, dict[str, list[float]]] = {}
    # "HUL (A)" per club per gameweek, so a solved card can name the opponent
    # rather than repeat the club whose shirt is already drawn beside the player.
    opponents: dict[str, list[list[str]]] = {}
    # One to five per club per gameweek, to a tenth, the measured difficulty.
    ratings: dict[str, list[float | None]] = {}
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
                if team_id not in strength:
                    back += 1.0
                    front += 1.0
                    saves += 1.0
                    leak += 1.0
                    contribution += 1.0
                    continue
                # A promoted opponent gets the same soft prior the difficulty
                # badge already used. Reading a missing club as league-average
                # here meant the badge beside a fixture said "easy" and the
                # points beside the badge said "ordinary", for every tie
                # against a promoted side.
                rated_strength = (
                    strength if opponent in strength else {**strength, opponent: PROMOTED_STRENGTH}
                )
                adjustment = route_adjustment(rated_strength, team_id, opponent, home=home)
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

    for element in available:
        record = record_by_code.get(element.code)
        rated = record is not None
        if rated:
            assert record is not None
            base_points = round(float(record["expectedPoints"]), 3)
            start_rate = round(float(record["probabilityStart"]), 3)
            # The eight routes, so the browser can bend each by its own fixture
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
                    "startRate": start_rate,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
