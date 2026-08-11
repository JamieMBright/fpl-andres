from __future__ import annotations

import json
from pathlib import Path

from fpl_andres.cli import publish_points_to_rank
from fpl_andres.cohorts.points_to_rank import RANK_CUTOFFS
from fpl_andres.holdout import SCORED_SEASONS


def row(entry_id: int, season: str, points: int, rank: int) -> dict[str, object]:
    return {
        "entryId": entry_id,
        "name": "must not be published",
        "seasons": [{"season": season.replace("-", "/"), "points": points, "rank": rank}],
    }


def test_publishes_each_requested_boundary_without_identifiers(tmp_path: Path) -> None:
    catalogue = tmp_path / "managers.jsonl"
    output = tmp_path / "points-to-rank.json"
    rows: list[dict[str, object]] = []
    entry_id = 1
    for season in SCORED_SEASONS:
        for cutoff in RANK_CUTOFFS:
            points = 3000 - RANK_CUTOFFS.index(cutoff) * 100
            rows.extend(
                [
                    row(entry_id, season, points, cutoff - 1),
                    row(entry_id + 1, season, points - 1, cutoff + 1),
                ]
            )
            entry_id += 2
    catalogue.write_text(
        "".join(json.dumps(entry) + "\n" for entry in rows),
        encoding="utf-8",
    )

    result = publish_points_to_rank.main(
        [
            "--catalogue",
            str(catalogue),
            "--sample",
            str(tmp_path / "missing.jsonl"),
            "--output",
            str(output),
        ]
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    text = output.read_text(encoding="utf-8")

    assert result == 0
    assert payload["schemaVersion"] == 1
    assert payload["cutoffs"] == list(RANK_CUTOFFS)
    assert payload["evidenceLevel"] == "observed"
    assert len(payload["seasons"]) == len(SCORED_SEASONS)
    assert all(len(season["boundaries"]) == len(RANK_CUTOFFS) for season in payload["seasons"])
    assert payload["sources"][0]["selection"] == "outcome_filtered_seed"
    assert payload["sources"][0]["fingerprint"].startswith("sha256:")
    assert "entryId" not in text
    assert "must not be published" not in text


def test_unfiltered_sample_replaces_seed_rows_for_the_same_entry(tmp_path: Path) -> None:
    catalogue = tmp_path / "managers.jsonl"
    sample = tmp_path / "sample.jsonl"
    output = tmp_path / "points-to-rank.json"
    catalogue.write_text(
        json.dumps(row(1, "2025-26", 2500, 900)) + "\n",
        encoding="utf-8",
    )
    sample.write_text(
        "\n".join(
            [
                json.dumps(row(1, "2025-26", 2400, 950)),
                json.dumps(row(2, "2025-26", 2399, 1050)),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    publish_points_to_rank.main(
        [
            "--catalogue",
            str(catalogue),
            "--sample",
            str(sample),
            "--output",
            str(output),
            "--seasons",
            "2025-26",
        ]
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    top_1k = payload["seasons"][0]["boundaries"][0]

    assert top_1k["inside"] == {"rank": 950, "points": 2400}
    assert top_1k["outside"] == {"rank": 1050, "points": 2399}
    assert payload["sources"][1]["selection"] == "deterministic_unfiltered_id_sample"
