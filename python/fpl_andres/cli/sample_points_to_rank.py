"""Collect a bounded unfiltered sample for historical points-to-rank bins.

This is deliberately separate from the FPL500 sweep. Every sampled entry is
chosen without looking at performance, and its history is written to a sidecar
that cannot change cohort membership. Transient failures stop the run at the
same ordinal; treating them as exclusions would bias the sample.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from fpl_andres import cliargs, timeouts
from fpl_andres.cohorts.sweep import parse_history
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.timeouts import client_timeout

HISTORY_URL = "https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
DEFAULT_OUTPUT = Path("data/cohort/points-to-rank-sample.jsonl")
DEFAULT_CHECKPOINT = Path("data/cohort/points-to-rank-sample-checkpoint.json")
DEFAULT_FRAME_MAX_ID = 3_782_000
DEFAULT_SAMPLE_SIZE = 12_000
DEFAULT_SEED = "fpl-andres:points-to-rank:v1"
DEFAULT_RATE = 8.0


@dataclass
class Progress:
    frame_max_id: int
    sample_size: int
    seed: str
    next_ordinal: int = 0
    with_history: int = 0
    missing: int = 0
    errors: int = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sample-points-to-rank")
    parser.add_argument("--frame-max-id", type=cliargs.positive_int, default=DEFAULT_FRAME_MAX_ID)
    parser.add_argument("--sample-size", type=cliargs.positive_int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--rate", type=cliargs.positive_float, default=DEFAULT_RATE)
    parser.add_argument("--max-seconds", type=cliargs.positive_float, default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--resume", action="store_true")
    return parser


def deterministic_entry_ids(*, frame_max_id: int, sample_size: int, seed: str) -> tuple[int, ...]:
    """One deterministic ID from each disjoint stratum of the frozen frame."""
    if sample_size > frame_max_id:
        raise ValueError("sample size cannot exceed the frozen ID frame")
    selected: list[int] = []
    for ordinal in range(sample_size):
        start = ordinal * frame_max_id // sample_size + 1
        stop = (ordinal + 1) * frame_max_id // sample_size
        width = stop - start + 1
        digest = hashlib.sha256(f"{seed}\0{ordinal}".encode()).digest()
        selected.append(start + int.from_bytes(digest[:8], "big") % width)
    return tuple(selected)


def save_progress(path: Path, progress: Progress) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "frameMaxId": progress.frame_max_id,
        "sampleSize": progress.sample_size,
        "seed": progress.seed,
        "nextOrdinal": progress.next_ordinal,
        "withHistory": progress.with_history,
        "missing": progress.missing,
        "errors": progress.errors,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_progress(
    path: Path,
    *,
    frame_max_id: int,
    sample_size: int,
    seed: str,
    resume: bool,
) -> Progress:
    expected = (frame_max_id, sample_size, seed)
    if not resume or not path.exists():
        return Progress(frame_max_id=frame_max_id, sample_size=sample_size, seed=seed)
    saved = read_json_file(path)
    progress = Progress(
        frame_max_id=int(saved["frameMaxId"]),
        sample_size=int(saved["sampleSize"]),
        seed=str(saved["seed"]),
        next_ordinal=int(saved.get("nextOrdinal", 0)),
        with_history=int(saved.get("withHistory", 0)),
        missing=int(saved.get("missing", 0)),
        errors=int(saved.get("errors", 0)),
    )
    actual = (progress.frame_max_id, progress.sample_size, progress.seed)
    if actual != expected:
        raise ValueError("saved sample frame does not match this run")
    return progress


async def fetch_history(
    client: httpx.AsyncClient, entry_id: int
) -> tuple[Literal["ok", "missing", "transient"], object | None]:
    try:
        response = await client.get(HISTORY_URL.format(entry_id=entry_id))
    except httpx.HTTPError:
        return "transient", None
    if response.status_code == 404:
        return "missing", None
    if response.status_code == 429 or response.status_code >= 500:
        return "transient", None
    if response.status_code != 200:
        return "transient", None
    try:
        return "ok", response.json()
    except ValueError:
        return "transient", None


def _saved_entry_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    ids: set[int] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = parse_json(line, source=f"{path} line {number}")
        entry_id = row.get("entryId")
        if isinstance(entry_id, int):
            ids.add(entry_id)
    return ids


def _record_payload(entry_id: int, payload: Mapping[str, object]) -> dict[str, object] | None:
    record = parse_history(entry_id, payload)
    if record is None:
        return None
    seasons = [
        {"season": season.season, "points": season.points, "rank": season.rank}
        for season in record.seasons
        if season.start_year >= 2022
    ]
    return None if not seasons else {"entryId": entry_id, "seasons": seasons}


async def run(args: argparse.Namespace) -> int:
    output = Path(args.output)
    checkpoint = Path(args.checkpoint)
    progress = load_progress(
        checkpoint,
        frame_max_id=args.frame_max_id,
        sample_size=args.sample_size,
        seed=args.seed,
        resume=args.resume,
    )
    ids = deterministic_entry_ids(
        frame_max_id=progress.frame_max_id,
        sample_size=progress.sample_size,
        seed=progress.seed,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    already = _saved_entry_ids(output)
    started = time.monotonic()
    interval = 1.0 / args.rate

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=client_timeout(timeouts.FPL_API),
        follow_redirects=True,
    ) as client:
        while progress.next_ordinal < len(ids):
            if args.max_seconds is not None and time.monotonic() - started >= args.max_seconds:
                break
            entry_id = ids[progress.next_ordinal]
            outcome, payload = await fetch_history(client, entry_id)
            if outcome == "transient":
                progress.errors += 1
                save_progress(checkpoint, progress)
                print(f"transient failure at sample ordinal {progress.next_ordinal}; stopping")
                return 2
            if outcome == "missing" or not isinstance(payload, Mapping):
                progress.missing += 1
            else:
                record = _record_payload(entry_id, payload)
                if record is not None and entry_id not in already:
                    with output.open("a", encoding="utf-8") as sink:
                        sink.write(json.dumps(record) + "\n")
                    already.add(entry_id)
                    progress.with_history += 1
            progress.next_ordinal += 1
            save_progress(checkpoint, progress)
            if progress.next_ordinal < len(ids):
                await asyncio.sleep(interval)

    print(
        f"sampled {progress.next_ordinal:,}/{progress.sample_size:,}; "
        f"history {progress.with_history:,}, missing {progress.missing:,}",
        flush=True,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
