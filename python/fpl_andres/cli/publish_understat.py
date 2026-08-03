"""Publish the Understat shot-quality artifact the analysis page reads.

FPL publishes a player's expected goals; it does not publish what those goals
were made of. Understat does, and the difference decides transfers: a striker
whose expected goals are three quarters penalties is a penalty taker with a
shot volume problem, and FPL's single `expected_goals` column cannot tell you
that.

Only the fields Understat adds are published here. Everything FPL already
serves -- price, ownership, minutes, points, defensive contributions -- stays
on the live bootstrap request the page already makes, so it keeps working when
the season turns over and these season totals do not.

Keyed by FPL player ``code``, matching every other artifact, because element
ids are reassigned each season.

Usage:
    python -m fpl_andres.cli.publish_understat --season 2025-26
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TypedDict

from fpl_andres.artifacts import UNDERSTAT_SCHEMA_VERSION
from fpl_andres.jsonio import MalformedJsonError, parse_json

DEFAULT_CROSSWALK = Path("data/crosswalk/understat-{season}.json")
DEFAULT_OUTPUT = Path("apps/web/src/data/understat.json")


class UnderstatEntry(TypedDict):
    """One player's Understat row in `understat.json`."""

    code: int
    shots: int
    shotsPer90: float
    expectedGoalsPerShot: float
    expectedGoalsPer90: float
    nonPenaltyExpectedGoals: float
    penaltyExpectedGoals: float
    penaltyShare: float
    expectedGoalsAtRiskPer90: float


class CrosswalkError(Exception):
    """Raised when the crosswalk cannot support the artifact."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-understat")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--crosswalk", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def _entries(
    shot_profile: dict[str, Any], penalty_exposure: dict[str, Any]
) -> list[UnderstatEntry]:
    """Join the two derived blocks on FPL code.

    A player present in one block and not the other is dropped rather than
    half-filled: the penalty share is only meaningful beside the shot volume it
    came from, and a row carrying one without the other reads as a player who
    took no penalties instead of one we could not join.
    """
    entries: list[UnderstatEntry] = []
    for raw_code in sorted(set(shot_profile) & set(penalty_exposure), key=int):
        shots = shot_profile[raw_code]
        penalties = penalty_exposure[raw_code]
        entries.append(
            {
                "code": int(raw_code),
                "shots": int(shots["shots"]),
                "shotsPer90": float(shots["shotsPer90"]),
                "expectedGoalsPerShot": float(shots["expectedGoalsPerShot"]),
                "expectedGoalsPer90": float(shots["expectedGoalsPer90"]),
                "nonPenaltyExpectedGoals": float(penalties["nonPenaltyExpectedGoals"]),
                "penaltyExpectedGoals": float(penalties["penaltyExpectedGoals"]),
                # Named `share` upstream; spelled out here because a bare
                # "share" in the browser says nothing about share of what.
                "penaltyShare": float(penalties["share"]),
                "expectedGoalsAtRiskPer90": float(penalties["expectedGoalsAtRiskPer90"]),
            }
        )
    return entries


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    crosswalk_path = Path(
        args.crosswalk if args.crosswalk else str(DEFAULT_CROSSWALK).format(season=args.season)
    )
    if not crosswalk_path.exists():
        raise CrosswalkError(
            f"no Understat crosswalk at {crosswalk_path}; run the crosswalk CLI first"
        )

    try:
        crosswalk = parse_json(
            crosswalk_path.read_text(encoding="utf-8"), source=str(crosswalk_path)
        )
    except MalformedJsonError as error:
        raise CrosswalkError(f"{crosswalk_path} is not readable JSON") from error

    if not isinstance(crosswalk, dict):
        raise CrosswalkError(f"{crosswalk_path} is not a JSON object")

    season = str(crosswalk.get("season", ""))
    if season != args.season:
        raise CrosswalkError(
            f"{crosswalk_path} covers {season!r}, not the requested {args.season!r}"
        )

    shot_profile = crosswalk.get("shotProfile")
    penalty_exposure = crosswalk.get("penaltyExposure")
    if not isinstance(shot_profile, dict) or not isinstance(penalty_exposure, dict):
        raise CrosswalkError(f"{crosswalk_path} carries no shotProfile/penaltyExposure blocks")

    players = _entries(shot_profile, penalty_exposure)
    if not players:
        raise CrosswalkError(f"{crosswalk_path} joined to zero players")

    artifact = {
        "schemaVersion": UNDERSTAT_SCHEMA_VERSION,
        "generatedAt": str(crosswalk.get("generatedAt", "")),
        "season": season,
        "source": str(crosswalk.get("source", "understat")),
        # Published so the page can say how much of the pool it covers rather
        # than leaving a blank axis looking like a bug.
        "coverage": float(crosswalk.get("coverage", 0.0)),
        "players": players,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output} ({len(players)} players, coverage {artifact['coverage']:.2%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
