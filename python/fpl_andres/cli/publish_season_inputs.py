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
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres import timeouts
from fpl_andres.backtesting.fixtures import TeamStrength, route_adjustment
from fpl_andres.bootstrap import BootstrapElement, parse_elements
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.planning.fixture_routes import fixture_difficulty
from fpl_andres.positions import Position

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
PROJECTIONS = Path("apps/web/src/data/projections.json")
OPENING_SQUAD = Path("apps/web/src/data/opening-squad.json")
DEFAULT_OUTPUT = Path("apps/web/src/data/season-inputs.json")

SCHEMA_VERSION = 1
POSITION_CODES = {position.value: position.code for position in Position}
# Enough that the solver has real choices, small enough to ship and to search.
POOL_PER_POSITION = 40


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-season-inputs")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--projections", default=str(PROJECTIONS))
    parser.add_argument("--opening-squad", default=str(OPENING_SQUAD))
    return parser


def _get(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
        return parse_json(response.read().decode("utf-8"), source=url)


# Where the measured tie sits on the published one-to-five scale. A fixture is
# rated on both halves of it: what this side is likely to score and what it is
# likely to concede, at the venue it is played. Blanks are None, not three:
# there is no fixture to be difficult.


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
    # One to five per club per gameweek, the published difficulty of the tie.
    ratings: dict[str, list[int | None]] = {}
    for team_id, team in clubs.items():
        defensive: list[float] = []
        attacking: list[float] = []
        difficulty: list[int | None] = []
        against: list[list[str]] = []
        for event in ordered:
            games = schedule.get((event, team_id), ())
            back = 0.0
            front = 0.0
            for opponent, home in games:
                if opponent not in strength or team_id not in strength:
                    back += 1.0
                    front += 1.0
                    continue
                # The backtested per-route multipliers, rather than a hand-rolled
                # inversion here. `clean_sheet` and `attacking` both account for
                # this club's own strength as well as the opponent's.
                adjustment = route_adjustment(strength, team_id, opponent, home=home)
                back += adjustment.clean_sheet
                front += adjustment.attacking
            defensive.append(round(back, 4))
            attacking.append(round(front, 4))
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
        }
        ratings[str(team["short_name"])] = difficulty
        opponents[str(team["short_name"])] = against

    players: list[tuple[int, float, dict[str, object]]] = []
    for element in parse_elements(bootstrap["elements"], model=BootstrapElement):
        if element.element_type not in POSITION_CODES or not element.is_available:
            continue
        record = record_by_code.get(element.code)
        if record is None:
            continue
        base_points = round(float(record["expectedPoints"]), 3)
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
                    "startRate": round(float(record["probabilityStart"]), 3),
                    "squadNumber": element.squad_number,
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
