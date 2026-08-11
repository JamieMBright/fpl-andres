"""Publish rough completed-season points-to-rank boundaries.

The elite catalogue supplies an immediate seed. A separate deterministic,
unfiltered sample may refine it without changing who belongs to FPL500. The
published artifact contains aggregate boundaries only: no manager identifier,
name or team is shipped with it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres.cohorts.points_to_rank import RANK_CUTOFFS, rank_boundaries
from fpl_andres.holdout import SCORED_SEASONS
from fpl_andres.jsonio import read_json_lines

CATALOGUE = Path("data/cohort/managers.jsonl")
SAMPLE = Path("data/cohort/points-to-rank-sample.jsonl")
DEFAULT_OUTPUT = Path("data/cohort/points-to-rank.json")
SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-points-to-rank")
    parser.add_argument("--catalogue", default=str(CATALOGUE))
    parser.add_argument("--sample", default=str(SAMPLE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--seasons", default=",".join(SCORED_SEASONS))
    return parser


def _fingerprint(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _records(path: Path) -> list[Mapping[str, object]]:
    return [row for row in read_json_lines(path) if isinstance(row, Mapping)]


def _entry_id(row: Mapping[str, object]) -> int | None:
    value = row.get("entryId")
    return value if isinstance(value, int) and value > 0 else None


def _combined(
    catalogue: Sequence[Mapping[str, object]],
    sample: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    by_entry: dict[int, Mapping[str, object]] = {}
    unidentified: list[Mapping[str, object]] = []
    for row in [*catalogue, *sample]:
        entry_id = _entry_id(row)
        if entry_id is None:
            unidentified.append(row)
        else:
            by_entry[entry_id] = row
    return [*by_entry.values(), *unidentified]


def _observation_count(rows: Sequence[Mapping[str, object]], season: str) -> int:
    source_key = season.replace("-", "/")
    count = 0
    for row in rows:
        seasons = row.get("seasons")
        if not isinstance(seasons, list):
            continue
        count += sum(
            1
            for finish in seasons
            if isinstance(finish, Mapping)
            and finish.get("season") == source_key
            and isinstance(finish.get("points"), int)
            and isinstance(finish.get("rank"), int)
        )
    return count


def _boundary_payload(boundary: object) -> dict[str, object]:
    from fpl_andres.cohorts.points_to_rank import RankBoundary

    if not isinstance(boundary, RankBoundary):
        raise TypeError("boundary must be a RankBoundary")
    return {
        "rankCutoff": boundary.rank_cutoff,
        "status": boundary.status,
        "inside": {
            "rank": boundary.inside.rank,
            "points": boundary.inside.points,
        },
        "outside": {
            "rank": boundary.outside.rank,
            "points": boundary.outside.points,
        },
        "rankGap": boundary.rank_gap,
        "pointsGap": boundary.points_gap,
        "sampleSize": boundary.sample_size,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalogue_path = Path(args.catalogue)
    sample_path = Path(args.sample)
    output = Path(args.output)
    seasons = tuple(part.strip() for part in args.seasons.split(",") if part.strip())

    catalogue = _records(catalogue_path)
    sample = _records(sample_path) if sample_path.exists() else []
    combined = _combined(catalogue, sample)

    sources: list[dict[str, object]] = [
        {
            "selection": "outcome_filtered_seed",
            "records": len(catalogue),
            "fingerprint": _fingerprint(catalogue_path),
            "timestampReason": "legacy catalogue did not retain fetch timestamps",
        }
    ]
    if sample_path.exists():
        sources.append(
            {
                "selection": "deterministic_unfiltered_id_sample",
                "records": len(sample),
                "fingerprint": _fingerprint(sample_path),
            }
        )

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(),
        "evidenceLevel": "observed",
        "cutoffSemantics": "overallRank <= cutoff",
        "cutoffs": list(RANK_CUTOFFS),
        "sources": sources,
        "seasons": [
            {
                "season": season,
                "observations": _observation_count(combined, season),
                "boundaries": [
                    _boundary_payload(boundary)
                    for boundary in rank_boundaries(
                        combined,
                        season=season.replace("-", "/"),
                    )
                ],
            }
            for season in seasons
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {len(seasons)} seasons from {len(combined):,} records to {output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
