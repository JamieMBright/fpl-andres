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
from fpl_andres.xstart_validation import evaluate_xstart

DEFAULT_CORRECTION = Path("data/prospective/gw1-2026-27-corrected.json")
DEFAULT_LIVE = Path("data/live/2026-27/gw01.json")
DEFAULT_OUTPUT = Path("apps/web/src/data/xstart-validation.json")
INPUTS_PATH = "apps/web/src/data/season-inputs.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build-xstart-validation")
    parser.add_argument("--correction", type=Path, default=DEFAULT_CORRECTION)
    parser.add_argument("--live", type=Path, default=DEFAULT_LIVE)
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    correction = read_json_file(args.correction)
    live = read_json_file(args.live)
    if not isinstance(correction, Mapping) or not isinstance(live, Mapping):
        raise ValueError("xStart validation inputs must be JSON objects")
    revision = correction.get("recordedCodeRevision")
    model_version = correction.get("canonicalModelVersion")
    if not isinstance(revision, str) or not isinstance(model_version, str):
        raise ValueError("the correction must name its recorded code and model revisions")
    captured_at = live.get("capturedAt")
    if not isinstance(captured_at, str):
        raise ValueError("the settled live snapshot must name its capture time")
    scored = evaluate_xstart(_git_json(revision, INPUTS_PATH), live)
    payload = {
        "schemaVersion": XSTART_VALIDATION_SCHEMA_VERSION,
        "generatedAt": captured_at,
        "season": correction.get("season"),
        "event": correction.get("event"),
        "modelVersion": model_version,
        "evidence": {
            "frozenRevision": revision,
            "frozenAt": correction.get("canonicalFrozenAt"),
            "liveSourceHash": live.get("sourceHash"),
            "liveCapturedAt": live.get("capturedAt"),
            "level": "observed",
        },
        **scored,
    }
    # Deliberately rebuilt rather than write-once: scoring code may change under
    # a new schema version. Immutable inputs plus their capture timestamp make
    # an unchanged evaluator byte-stable, which the workflow verifies by diff.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.output} — {payload['population']['count']} players, "
        f"Brier {payload['population']['brier']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
