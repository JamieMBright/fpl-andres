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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

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
from fpl_andres.planning.season_plan import (
    chip_windows,
    plan_season,
)
from fpl_andres.positions import Position
from fpl_andres.rules import RulesSnapshot

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
    squad_number: int | None


def _opponent_multiplier(
    *,
    position: int,
    opponent: int,
    home: bool,
    strength: Mapping[int, TeamStrength],
) -> float:
    """How much this fixture is worth to this player, against an average one."""
    measured = strength.get(opponent)
    if measured is None:
        return 1.0
    defensive = position in (1, 2)
    # A defender's return depends on the opponent's attack; an attacker's on
    # their defence. The opponent's home/away is the inverse of the player's.
    return measured.attack(home=not home) if defensive else measured.defence(home=not home)


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

    # Keep the squad, plus the strongest of everyone else, position by position.
    held = {by_code[code].element_id for code in squad_codes}
    pool: list[Candidate] = [by_code[code] for code in squad_codes]
    for position in SQUAD_SHAPE:
        ranked = sorted(
            (c for c in candidates if c.position == position and c.element_id not in held),
            key=lambda c: -c.record,
        )
        pool.extend(ranked[:POOL_PER_POSITION])

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
    now = datetime.now(UTC)
    for event in ordered_events:
        weights: list[float] = []
        for candidate in pool:
            games = schedule.get((event, candidate.team_id), ())
            if not games:
                # A blank gameweek is zero, not an average week. Nothing is a
                # more honest projection for a player who is not playing.
                expected = 0.0
            else:
                expected = sum(
                    candidate.record
                    * _opponent_multiplier(
                        position=candidate.position,
                        opponent=opponent,
                        home=home,
                        strength=strength,
                    )
                    for opponent, home in games
                )
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
                        position=3, opponent=opponent, home=home, strength=strength
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
                "freeTransfersBefore": event_plan.free_transfers_before,
                "paidTransfers": event_plan.paid_transfers,
                "transferCostPoints": event_plan.transfer_cost_points,
                "projectedPoints": round(event_plan.projected_points_before_cost, 2),
                "netExpectedPoints": round(event_plan.net_expected_points, 2),
                "bankAfterTenths": event_plan.bank_after_tenths,
            }
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
        "chipWindows": list(chip_windows(difficulty, count=2)),
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
