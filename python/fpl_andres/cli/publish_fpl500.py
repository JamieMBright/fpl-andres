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
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres import cliargs
from fpl_andres.cohorts.elite import (
    DEFAULT_SETTINGS,
    EliteScore,
    EliteSettings,
    ManagerSeason,
    SweptManager,
    entries_by_season,
    rank_elite,
    season_start_year,
)
from fpl_andres.cohorts.portfolio import MINIMUM_COVERAGE
from fpl_andres.jsonio import parse_json

COHORT_DIR = Path("data/cohort")
MANAGERS = COHORT_DIR / "managers.jsonl"
CHECKPOINT = COHORT_DIR / "sweep-checkpoint.json"
#: Where `capture_cohort_picks` writes a gameweek's squads. Empty until the
#: season starts: the fund cannot hold anything before anybody has picked.
PORTFOLIO_DIR = COHORT_DIR / "portfolio"
DEFAULT_OUTPUT = COHORT_DIR / "fpl500.json"
DEFAULT_WEB_OUTPUT = Path("apps/web/src/data/fpl500.json")
SCHEMA_VERSION = 1

#: How many of the ranking the site lists by name. The whole five hundred is a
#: hundred kilobytes of entry ids nobody scrolls; what a reader needs is the
#: shape of the cut and enough of the head to see what clearing it looks like.
#: The distribution below carries the rest.
WEB_LISTED = 50

#: Where the score distribution is sampled, so a reader can see the curve
#: without shipping five hundred points to draw it with.
WEB_QUANTILES = (1, 10, 25, 50, 100, 200, 300, 400, 500)

#: FPL's live entry count, read from the register rather than assumed: the
#: sweep's own estimate of the largest rank in the season just finished.
LATEST_SEASON_KEY = "latestSeasonEntries"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-fpl500")
    parser.add_argument("--managers", default=str(MANAGERS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--web-output",
        default=str(DEFAULT_WEB_OUTPUT),
        help=(
            "The trimmed copy the site reads. Written beside the full ranking "
            "so the two can never describe different sweeps."
        ),
    )
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

    web = Path(args.web_output)
    web.parent.mkdir(parents=True, exist_ok=True)
    web.write_text(
        json.dumps(_web_payload(ranked, managers, field, settings, swept_to), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {web} — {min(WEB_LISTED, len(ranked))} listed, {len(ranked)} counted")
    return 0


def _web_payload(
    ranked: Sequence[EliteScore],
    managers: Sequence[SweptManager],
    field: Mapping[str, int],
    settings: EliteSettings,
    swept_to: object,
) -> dict[str, object]:
    """What the site needs, without the hundred kilobytes it does not.

    The ranking is a hundred and five kilobytes of entry ids. A page that lists
    all of them is a page nobody reads to the end, and the browser pays for it
    on every visit. So the head is listed by name, the curve is sampled at
    fixed depths, and the totals that let a reader check both are carried in
    full.
    """
    latest = max(field, key=lambda season: season_start_year(season)) if field else None
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "catalogueSize": len(managers),
        "sweptTo": swept_to,
        "size": len(ranked),
        "listed": min(WEB_LISTED, len(ranked)),
        "settings": {
            "decayPerSeason": settings.decay_per_season,
            "preRulesChangeWeight": settings.pre_rules_change_weight,
            "rulesChangedIn": settings.rules_changed_in,
            "shrinkageWeight": settings.shrinkage_weight,
            "priorPercentile": settings.prior_percentile,
            "minimumSeasons": settings.minimum_seasons,
        },
        "latestSeason": latest,
        LATEST_SEASON_KEY: field.get(latest) if latest else None,
        "estimatedEntriesBySeason": dict(sorted(field.items())),
        # The reconciler's own floor, so the page describing the fund quotes
        # the number that will refuse a snapshot rather than one typed beside it.
        "minimumCoverage": MINIMUM_COVERAGE,
        "portfolioEvents": sorted(
            int(path.stem.removeprefix("gw"))
            for path in sorted(PORTFOLIO_DIR.glob("gw*.json"))
            if path.stem.removeprefix("gw").isdigit()
        ),
        # The score at fixed depths, so the shape of the cut is visible without
        # shipping five hundred points to draw it from.
        "scoreAtRank": {
            str(depth): round(ranked[depth - 1].score, 6)
            for depth in WEB_QUANTILES
            if depth <= len(ranked)
        },
        "seasonsCounted": _histogram(row.seasons_counted for row in ranked),
        "managers": [
            {
                "rank": position,
                "entryId": row.entry_id,
                "score": round(row.score, 6),
                "seasons": row.seasons_counted,
                "bestPercentile": round(row.best_percentile, 6),
                "latestPercentile": (
                    None if row.latest_percentile is None else round(row.latest_percentile, 6)
                ),
                "latestSeason": row.latest_season,
            }
            for position, row in enumerate(ranked[:WEB_LISTED], 1)
        ],
    }


def _histogram(values: Iterable[int]) -> dict[str, int]:
    counts: dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return {str(key): counts[key] for key in sorted(counts)}


if __name__ == "__main__":
    raise SystemExit(main())
