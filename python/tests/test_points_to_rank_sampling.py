from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import pytest

from fpl_andres.cli import sample_points_to_rank
from fpl_andres.cli.sample_points_to_rank import (
    Progress,
    deterministic_entry_ids,
    run,
)


def arguments(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "frame_max_id": 1_000,
        "sample_size": 10,
        "seed": "rank-v1",
        "rate": 1000.0,
        "max_seconds": None,
        "output": str(tmp_path / "sample.jsonl"),
        "checkpoint": str(tmp_path / "checkpoint.json"),
        "resume": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def history(points: int = 2400, rank: int = 10_000) -> dict[str, object]:
    return {
        "past": [
            {
                "season_name": "2025/26",
                "total_points": points,
                "rank": rank,
                "rank_percentage": 0.1,
            }
        ]
    }


def test_ids_are_deterministic_unique_and_inside_disjoint_strata() -> None:
    first = deterministic_entry_ids(frame_max_id=10_000, sample_size=200, seed="rank-v1")
    second = deterministic_entry_ids(frame_max_id=10_000, sample_size=200, seed="rank-v1")

    assert first == second
    assert len(first) == len(set(first)) == 200
    assert min(first) >= 1
    assert max(first) <= 10_000


def test_resume_refuses_a_different_frozen_frame(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    sample_points_to_rank.save_progress(
        checkpoint,
        Progress(
            frame_max_id=900,
            sample_size=10,
            seed="rank-v1",
            next_ordinal=4,
        ),
    )

    with pytest.raises(ValueError, match="does not match"):
        sample_points_to_rank.load_progress(
            checkpoint,
            frame_max_id=1_000,
            sample_size=10,
            seed="rank-v1",
            resume=True,
        )


@pytest.mark.asyncio
async def test_404_is_terminal_and_advances_the_ordinal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fetch(*_args: object, **_kwargs: object) -> tuple[str, object | None]:
        return "missing", None

    monkeypatch.setattr(sample_points_to_rank, "fetch_history", fetch)

    assert await run(arguments(tmp_path, sample_size=1)) == 0
    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["nextOrdinal"] == 1
    assert saved["missing"] == 1
    assert not (tmp_path / "sample.jsonl").exists()


@pytest.mark.asyncio
async def test_transient_failure_does_not_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fetch(*_args: object, **_kwargs: object) -> tuple[str, object | None]:
        return "transient", None

    monkeypatch.setattr(sample_points_to_rank, "fetch_history", fetch)

    assert await run(arguments(tmp_path, sample_size=1)) == 2
    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["nextOrdinal"] == 0
    assert saved["errors"] == 1


@pytest.mark.asyncio
async def test_a_replayed_success_is_not_appended_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fetch(*_args: object, **_kwargs: object) -> tuple[str, object | None]:
        return "ok", history()

    monkeypatch.setattr(sample_points_to_rank, "fetch_history", fetch)
    args = arguments(tmp_path, sample_size=1)

    assert await run(args) == 0
    checkpoint = tmp_path / "checkpoint.json"
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    saved["nextOrdinal"] = 0
    checkpoint.write_text(json.dumps(saved), encoding="utf-8")
    assert await run(args) == 0

    lines = (tmp_path / "sample.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["seasons"] == [{"season": "2025/26", "points": 2400, "rank": 10_000}]


@pytest.mark.asyncio
async def test_http_failures_are_transient() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("reset")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        outcome, payload = await sample_points_to_rank.fetch_history(client, 1)

    assert outcome == "transient"
    assert payload is None
