"""Publish xStart scoring from immutable frozen inputs and settled outcomes."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fpl_andres.artifacts import XSTART_VALIDATION_SCHEMA_VERSION
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.prospective import build_correction_manifest
from fpl_andres.xstart_validation import evaluate_xstart

DEFAULT_CORRECTION_DIR = Path("data/prospective")
DEFAULT_LIVE_DIR = Path("data/live/2026-27")
DEFAULT_OUTPUT = Path("apps/web/src/data/xstart-validation.json")
INPUTS_PATH = "apps/web/src/data/season-inputs.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build-xstart-validation")
    parser.add_argument("--correction", type=Path, default=None)
    parser.add_argument("--live", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _git_json(revision: str, path: str) -> Mapping[str, Any]:
    raw = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        check=True,
        capture_output=True,
    ).stdout
    payload = parse_json(raw.decode("utf-8"), source=f"{revision}:{path}")
    if not isinstance(payload, Mapping):
        raise ValueError(f"{revision}:{path} was not a JSON object")
    return payload


def _score_pair(correction_path: Path, live_path: Path) -> dict[str, Any]:
    correction = read_json_file(correction_path)
    live = read_json_file(live_path)
    if not isinstance(correction, Mapping) or not isinstance(live, Mapping):
        raise ValueError("xStart validation inputs must be JSON objects")
    revision = correction.get("recordedCodeRevision")
    model_version = correction.get("canonicalModelVersion")
    if not isinstance(revision, str) or not isinstance(model_version, str):
        raise ValueError("the correction must name its recorded code and model revisions")
    captured_at = live.get("capturedAt")
    if not isinstance(captured_at, str):
        raise ValueError("the settled live snapshot must name its capture time")
    return {
        "generatedAt": captured_at,
        "event": correction.get("event"),
        "modelVersion": model_version,
        "evidence": {
            "frozenRevision": revision,
            "frozenAt": correction.get("canonicalFrozenAt"),
            "liveSourceHash": live.get("sourceHash"),
            "liveCapturedAt": live.get("capturedAt"),
            "level": "observed",
        },
        **evaluate_xstart(_git_json(revision, INPUTS_PATH), live),
    }


def _pairs(correction: Path | None, live: Path | None) -> list[tuple[Path, Path]]:
    if (correction is None) != (live is None):
        raise ValueError("--correction and --live must be supplied together")
    if correction is not None and live is not None:
        return [(correction, live)]
    result: list[tuple[Path, Path]] = []
    for correction_path in sorted(DEFAULT_CORRECTION_DIR.glob("gw*-2026-27-corrected.json")):
        raw = read_json_file(correction_path)
        event = raw.get("event")
        if not isinstance(event, int):
            raise ValueError(f"correction does not name an event: {correction_path}")
        live_path = DEFAULT_LIVE_DIR / f"gw{event:02d}.json"
        if live_path.exists() and read_json_file(live_path).get("roundComplete") is True:
            result.append((correction_path, live_path))
    return result


def _ensure_corrections() -> None:
    for manifest in sorted(DEFAULT_CORRECTION_DIR.glob("gw*-2026-27.json")):
        correction = manifest.with_name(f"{manifest.stem}-corrected.json")
        if correction.exists():
            continue
        canonical = read_json_file(manifest)
        event = canonical.get("event")
        live = DEFAULT_LIVE_DIR / f"gw{event:02d}.json" if isinstance(event, int) else None
        if (
            live is None
            or not live.exists()
            or read_json_file(live).get("roundComplete") is not True
        ):
            continue
        revision = subprocess.run(
            ["git", "log", "--diff-filter=A", "-1", "--format=%H", "--", str(manifest)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not revision:
            raise ValueError(f"prospective manifest is not committed: {manifest}")
        payload = build_correction_manifest(
            canonical,
            manifest_revision=revision,
        )
        correction.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote immutable correction {correction}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.correction is None:
        _ensure_corrections()
    pairs = _pairs(args.correction, args.live)
    if not pairs:
        raise ValueError("no corrected xStart events have settled live outcomes")
    events = [_score_pair(correction, live) for correction, live in pairs]
    seasons = {read_json_file(correction).get("season") for correction, _live in pairs}
    if len(seasons) != 1:
        raise ValueError("xStart validation events must belong to one season")
    payload = {
        "schemaVersion": XSTART_VALIDATION_SCHEMA_VERSION,
        "generatedAt": max(str(event["generatedAt"]) for event in events),
        "season": seasons.pop(),
        "events": events,
    }
    # Deliberately rebuilt rather than write-once: scoring code may change under
    # a new schema version. Immutable inputs plus their capture timestamp make
    # an unchanged evaluator byte-stable, which the workflow verifies by diff.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} — {len(events)} settled events through GW{events[-1]['event']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
