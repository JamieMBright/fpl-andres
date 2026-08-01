"""Publish the swept manager cohort as a site artifact.

Emits what the sweep can honestly support: how many managers clear the bar, how
often, and over which seasons. It deliberately does **not** emit a persistence
or "proven manager" figure. The sweep keeps a manager only if they already have
two qualifying seasons, so the file cannot answer whether past rank predicts
future rank - measured on it, the lift came out below one in every recent
season pair, which is the selection showing through.

Usage:
    python -m fpl_andres.cli.publish_cohort --since 2021
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

SOURCE = Path("data/cohort/managers.jsonl")
CHECKPOINT = Path("data/cohort/sweep-checkpoint.json")
DEFAULT_OUTPUT = Path("apps/web/src/data/cohort.json")
RANK_CEILING = 10_000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-cohort")
    parser.add_argument("--since", type=int, default=2021, help="first season start year")
    parser.add_argument("--source", default=str(SOURCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--complete",
        action="store_true",
        help="the sweep ran past the end of the entry id space",
    )
    return parser


def _start_year(season: str) -> int:
    return int(season.split("/", 1)[0])


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.source)
    if not source.exists():
        print(f"{source} does not exist; run the sweep first")
        return 1

    records = [
        json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()
    ]

    qualifying_counts: Counter[int] = Counter()
    seasons_seen: Counter[str] = Counter()
    best_ranks: list[int] = []
    for record in records:
        recent = [
            season
            for season in record["seasons"]
            if _start_year(season["season"]) >= args.since and season["rank"]
        ]
        good = [season for season in recent if season["rank"] <= RANK_CEILING]
        qualifying_counts[len(good)] += 1
        for season in good:
            seasons_seen[season["season"]] += 1
        if recent:
            best_ranks.append(min(season["rank"] for season in recent))

    swept = 0
    with_history = 0
    missing = 0
    if CHECKPOINT.exists():
        checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        swept = checkpoint.get("next_id", 1) - 1
        with_history = checkpoint.get("with_history", 0)
        missing = checkpoint.get("missing", 0)

    payload = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "rankCeiling": RANK_CEILING,
        "sinceSeasonStartYear": args.since,
        "entriesSwept": swept,
        "entriesWithHistory": with_history,
        "entriesMissing": missing,
        "sweepComplete": args.complete,
        "managers": len(records),
        "qualifyingSeasonCounts": {
            str(count): total for count, total in sorted(qualifying_counts.items())
        },
        "seasonsRepresented": dict(sorted(seasons_seen.items())),
        "bestRankMedian": sorted(best_ranks)[len(best_ranks) // 2] if best_ranks else None,
        # Stated in the artifact so no surface can quietly imply otherwise.
        "persistenceMeasurable": False,
        "persistenceNote": (
            "This catalogue only contains managers who already cleared the bar "
            "twice, so it cannot measure whether a good season predicts the "
            "next one. Measured on it anyway, the elite group repeated less "
            "often than the comparison group, which is the selection showing "
            "through rather than a finding."
        ),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"{len(records)} qualifying managers from {swept:,} entries swept")
    print(f"  median best rank since {args.since}: {payload['bestRankMedian']}")
    for count, total in sorted(qualifying_counts.items()):
        print(f"  {count} qualifying seasons: {total}")
    print(f"\nwrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
