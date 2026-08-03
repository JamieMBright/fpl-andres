"""Publish FPL500: the five hundred managers worth following.

Reads the swept catalogue and ranks it on sustained elite finishing, measured in
percentile so seasons from different-sized fields are comparable, weighted
toward the game as it is currently scored.

The output is tracked in git. FPL500 is the input to the cohort portfolio, and a
derived ranking whose source is not in the repository cannot be reproduced or
argued with.

Usage:
    python -m fpl_andres.cli.publish_fpl500
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres import cliargs
from fpl_andres.cohorts.elite import (
    DEFAULT_SETTINGS,
    EliteSettings,
    ManagerSeason,
    SweptManager,
    entries_by_season,
    rank_elite,
)
from fpl_andres.jsonio import parse_json

COHORT_DIR = Path("data/cohort")
MANAGERS = COHORT_DIR / "managers.jsonl"
CHECKPOINT = COHORT_DIR / "sweep-checkpoint.json"
DEFAULT_OUTPUT = COHORT_DIR / "fpl500.json"
SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-fpl500")
    parser.add_argument("--managers", default=str(MANAGERS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--top", type=cliargs.positive_int, default=500)
    parser.add_argument("--decay", type=cliargs.positive_float, default=None)
    parser.add_argument("--minimum-seasons", type=cliargs.positive_int, default=None)
    return parser


def read_catalogue(path: Path) -> list[SweptManager]:
    managers: list[SweptManager] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = parse_json(line, source=f"{path}:{number}")
        managers.append(
            SweptManager(
                entry_id=int(row["entryId"]),
                seasons=tuple(
                    ManagerSeason(
                        season=str(season["season"]),
                        points=int(season["points"]),
                        rank=int(season["rank"]),
                    )
                    for season in row["seasons"]
                    if season.get("rank")
                ),
            )
        )
    return managers


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.managers)
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. Run sweep_managers first; FPL500 is derived "
            f"from the catalogue, not discovered independently."
        )

    managers = read_catalogue(path)
    settings = EliteSettings(
        decay_per_season=args.decay or DEFAULT_SETTINGS.decay_per_season,
        minimum_seasons=args.minimum_seasons or DEFAULT_SETTINGS.minimum_seasons,
    )
    field = entries_by_season(managers)
    ranked = rank_elite(managers, entries=field, settings=settings, top=args.top)

    swept_to = None
    if CHECKPOINT.exists():
        swept_to = parse_json(CHECKPOINT.read_text(encoding="utf-8"), source=str(CHECKPOINT)).get(
            "next_id"
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "catalogueSize": len(managers),
                "sweptTo": swept_to,
                "size": len(ranked),
                "settings": {
                    "decayPerSeason": settings.decay_per_season,
                    "preRulesChangeWeight": settings.pre_rules_change_weight,
                    "rulesChangedIn": settings.rules_changed_in,
                    "shrinkageWeight": settings.shrinkage_weight,
                    "priorPercentile": settings.prior_percentile,
                    "minimumSeasons": settings.minimum_seasons,
                },
                # Published because the percentiles are only as good as this,
                # and it is the largest rank observed rather than a true count.
                "estimatedEntriesBySeason": dict(sorted(field.items())),
                "managers": [
                    {
                        "entryId": row.entry_id,
                        "score": round(row.score, 6),
                        "seasons": row.seasons_counted,
                        "weight": round(row.total_weight, 4),
                        "bestPercentile": round(row.best_percentile, 6),
                        "latestPercentile": (
                            None
                            if row.latest_percentile is None
                            else round(row.latest_percentile, 6)
                        ),
                        "latestSeason": row.latest_season,
                    }
                    for row in ranked
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"wrote {output} — {len(ranked)} of {len(managers)} managers")
    if ranked:
        print(f"  top score {ranked[0].score:.4f}, cut-off {ranked[-1].score:.4f}")
        print(
            f"  seasons held by the top 500: {min(r.seasons_counted for r in ranked)}"
            f"-{max(r.seasons_counted for r in ranked)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
