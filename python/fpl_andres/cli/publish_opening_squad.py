"""Publish the opening squad the evidence supports, and what it cannot see.

There is no personal squad before the first deadline: FPL wipes them all, so
every manager starts from the same hundred million and nothing. This job
therefore publishes one squad, not a per-manager one, and says plainly which
players it was structurally unable to consider.

Live prices and fixtures come from FPL. The scoring record comes from the
committed projection artifact, joined on the player code, which is the Opta id.

Usage:
    python -m fpl_andres.cli.publish_opening_squad
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres.backtesting.fixtures import Fixture, TeamStrength
from fpl_andres.planning.opening import OpeningSettings, choose_opening_squad
from fpl_andres.simulation.squad import Candidate, SquadRules

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
PROJECTIONS = Path("apps/web/src/data/projections.json")
DEFAULT_OUTPUT = Path("apps/web/src/data/opening-squad.json")

RULES = SquadRules(budget_tenths=1000, club_limit=3, position_counts={1: 2, 2: 5, 3: 5, 4: 3})
POSITION_CODES = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
# Long enough to matter to an opening squad, short enough that the sides playing
# them still resemble the ones named today.
RUN_WINDOW = 5
# Roughly a third of a season. Below this a man was a substitute last year, and
# nothing in this model knows whether that has changed.
LAST_SEASON_MINUTES_FLOOR = 900


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-opening-squad")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--projections", default=str(PROJECTIONS))
    return parser


def _get(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


@dataclass(frozen=True)
class Rated:
    candidate: Candidate
    club: str
    record: float
    adjusted: float
    run: float | None
    rated_fixtures: int
    fixtures: int
    start_rate: float


def _run_rating(
    team_id: int,
    position: int,
    fixtures: Sequence[Fixture],
    strength: Mapping[int, TeamStrength],
) -> tuple[float | None, int, int]:
    """Mean opponent multiplier on the route that matters for this position."""
    defensive = position in (1, 2)
    events = sorted({fixture.event for fixture in fixtures if fixture.event})[:RUN_WINDOW]
    horizon = set(events)

    multipliers: list[float] = []
    played = 0
    for fixture in fixtures:
        if fixture.event not in horizon:
            continue
        opponent = fixture.opponent_of(team_id)
        if opponent is None:
            continue
        played += 1
        measured = strength.get(opponent)
        if measured is None:
            continue
        home = fixture.is_home(team_id)
        multipliers.append(
            measured.attack(home=not home) if defensive else measured.defence(home=not home)
        )
    if not multipliers:
        return None, 0, played
    return sum(multipliers) / len(multipliers), len(multipliers), played


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    artifact = json.loads(Path(args.projections).read_text(encoding="utf-8"))
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
    # Club ids are reassigned every season; the code is not.
    strength = {
        team_id: strength_by_code[int(team["code"])]
        for team_id, team in clubs.items()
        if int(team["code"]) in strength_by_code
    }

    raw_fixtures = _get(FIXTURES)
    assert isinstance(raw_fixtures, list)
    by_team: dict[int, list[Fixture]] = {}
    for row in raw_fixtures:
        fixture = Fixture(
            fixture_id=int(row["id"]),
            event=row["event"],
            team_h=int(row["team_h"]),
            team_a=int(row["team_a"]),
            kickoff_time=None,
        )
        by_team.setdefault(fixture.team_h, []).append(fixture)
        by_team.setdefault(fixture.team_a, []).append(fixture)

    rated: list[Rated] = []
    unseen = 0
    unavailable = 0
    bit_part = 0
    for element in bootstrap["elements"]:
        position = int(element["element_type"])
        if position not in POSITION_CODES:
            continue
        # FPL's own flag. Injured, suspended and departed players are not picks.
        if str(element["status"]) != "a":
            unavailable += 1
            continue
        # This field is last season's total. A man on two hundred minutes was
        # not a starter then and there is no evidence he is one now.
        if int(element["minutes"]) < LAST_SEASON_MINUTES_FLOOR:
            bit_part += 1
            continue
        record = record_by_code.get(int(element["code"]))
        if record is None:
            unseen += 1
            continue
        team_id = int(element["team"])
        run, rated_count, fixtures = _run_rating(
            team_id, position, by_team.get(team_id, ()), strength
        )
        points = float(record["expectedPoints"])
        rated.append(
            Rated(
                candidate=Candidate(
                    element_id=int(element["id"]),
                    element_code=int(element["code"]),
                    position=position,
                    team_id=team_id,
                    price_tenths=int(element["now_cost"]),
                    web_name=str(element["web_name"]),
                ),
                club=str(clubs[team_id]["short_name"]),
                record=points,
                # Fixtures scale the whole expectation; an unrated run does not.
                adjusted=points * (run if run is not None else 1.0),
                run=run,
                rated_fixtures=rated_count,
                fixtures=fixtures,
                start_rate=float(record["probabilityStart"]),
            )
        )

    ranking = {entry.candidate.element_id: entry.adjusted for entry in rated}
    plan = choose_opening_squad(
        [entry.candidate for entry in rated],
        ranking,
        {entry.candidate.element_id: entry.start_rate for entry in rated},
        OpeningSettings(rules=RULES),
    )
    squad = list(plan.squad)
    starting = {player.element_id for player in plan.starters}
    detail = {entry.candidate.element_id: entry for entry in rated}

    picks = []
    for player in sorted(squad, key=lambda member: (member.position, -ranking[member.element_id])):
        entry = detail[player.element_id]
        picks.append(
            {
                "code": player.element_code,
                "name": player.web_name,
                "position": POSITION_CODES[player.position],
                "club": entry.club,
                "priceTenths": player.price_tenths,
                "record": round(entry.record, 2),
                "adjusted": round(entry.adjusted, 2),
                "startRate": round(entry.start_rate, 2),
                "starter": player.element_id in starting,
                "run": None if entry.run is None else round(entry.run, 2),
                "ratedFixtures": entry.rated_fixtures,
                "fixtures": entry.fixtures,
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "generatedAt": datetime.now(UTC).isoformat(),
                "basis": artifact["season"],
                "budgetTenths": RULES.budget_tenths,
                "spentTenths": plan.spent_tenths,
                "expectedPoints": round(plan.expected_points, 2),
                "consideredPlayers": len(rated),
                "withoutRecord": unseen,
                "unavailable": unavailable,
                "bitPart": bit_part,
                "minutesFloor": LAST_SEASON_MINUTES_FLOOR,
                "picks": picks,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    spent = sum(player.price_tenths for player in squad)
    print(
        f"considered {len(rated)}; skipped {unseen} with no record, "
        f"{unavailable} flagged by FPL, {bit_part} under "
        f"{LAST_SEASON_MINUTES_FLOOR} minutes last season"
    )
    print(
        f"spent {spent / 10:.1f}m of {RULES.budget_tenths / 10:.1f}m, "
        f"starting eleven {plan.expected_points:.2f} pts"
    )
    for player in sorted(squad, key=lambda member: (member.position, -ranking[member.element_id])):
        entry = detail[player.element_id]
        mark = "  " if player.element_id in starting else "b "
        print(
            f"{mark}{POSITION_CODES[player.position]:<4}{player.web_name:<18}"
            f"{entry.club:<5}{player.price_tenths / 10:>5.1f}m  "
            f"rec={entry.record:<5} start={entry.start_rate:<5} run={entry.run}"
        )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
