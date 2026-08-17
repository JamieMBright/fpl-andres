"""Validate a dated probable XI without feeding it into the production model."""

from __future__ import annotations

import argparse
import json
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres import timeouts
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.models.lineup_validation import (
    LineupCandidate,
    LineupPrior,
    evaluate_lineup_prior,
)

DEFAULT_PRIOR = Path("data/lineup-validation/leeds-gw1-2026-27-prior.json")
DEFAULT_INPUTS = Path("apps/web/src/data/season-inputs.json")
DEFAULT_OUTPUT = Path("data/lineup-validation/leeds-gw1-2026-27-report.json")
LIVE = "https://fantasy.premierleague.com/api/event/{event}/live/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate-lineup-prior")
    parser.add_argument("--prior", default=str(DEFAULT_PRIOR))
    parser.add_argument("--season-inputs", default=str(DEFAULT_INPUTS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--no-live", action="store_true")
    parser.add_argument(
        "--require-actual",
        action="store_true",
        help="Leave the existing report untouched until FPL publishes starters.",
    )
    return parser


def _get(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
        return parse_json(response.read().decode("utf-8"), source=url)


def _actual_starters(event: int, element_ids: set[int]) -> set[int] | None:
    payload = _get(LIVE.format(event=event))
    if not isinstance(payload, Mapping):
        raise ValueError("FPL live response was not an object")
    rows = payload.get("elements")
    if not isinstance(rows, list) or not rows:
        return None
    starters: set[int] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        element_id = row.get("id")
        stats = row.get("stats")
        if (
            isinstance(element_id, int)
            and element_id in element_ids
            and isinstance(stats, Mapping)
            and stats.get("starts") == 1
        ):
            starters.add(element_id)
    return starters


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prior_payload = read_json_file(Path(args.prior))
    inputs = read_json_file(Path(args.season_inputs))
    prior = LineupPrior(
        club=str(prior_payload["club"]),
        fixture_id=int(prior_payload["fixtureId"]),
        cutoff=str(prior_payload["cutoff"]),
        source=str(prior_payload["source"]),
        expected_names=tuple(str(name) for name in prior_payload["expectedNames"]),
        least_confident=tuple(str(name) for name in prior_payload.get("leastConfident", ())),
    )
    candidates = [
        LineupCandidate(
            element_id=int(player["id"]),
            name=str(player["name"]),
            start_probability=float(player["startRate"]),
        )
        for player in inputs["players"]
        if player.get("club") == prior.club
    ]
    if not candidates:
        raise ValueError(f"season inputs carry no players for {prior.club}")
    actual = (
        None
        if args.no_live
        else _actual_starters(
            int(prior_payload["event"]),
            {candidate.element_id for candidate in candidates},
        )
    )
    if args.require_actual and actual is None:
        print("FPL has not published the actual starters; report unchanged")
        return 0
    report = evaluate_lineup_prior(
        prior,
        candidates,
        actual_element_ids=actual,
    )
    output = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "season": str(prior_payload["season"]),
        "event": int(prior_payload["event"]),
        "fixtureId": prior.fixture_id,
        "club": prior.club,
        "cutoff": prior.cutoff,
        "source": prior.source,
        "leastConfident": list(prior.least_confident),
        **asdict(report),
        "players": [
            {
                "elementId": candidate.element_id,
                "name": candidate.name,
                "startProbability": candidate.start_probability,
            }
            for candidate in sorted(candidates, key=lambda row: -row.start_probability)
        ],
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = read_json_file(path)
        comparable_existing = {
            key: value for key, value in existing.items() if key != "generatedAt"
        }
        comparable_output = {key: value for key, value in output.items() if key != "generatedAt"}
        if comparable_existing == comparable_output:
            print(f"{path} unchanged")
            return 0
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {path}: model/prior {report.overlap}/11"
        + (
            "; actual not published"
            if report.actual_overlap is None
            else (
                f"; prior/actual {report.actual_overlap}/11, "
                f"model/actual {report.model_actual_overlap}/11"
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
