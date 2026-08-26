"""Publish the immutable GW1 review from frozen and settled public evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_andres import cliargs
from fpl_andres.cli.capture_live_gameweek import _get_bytes
from fpl_andres.gw1_review import build_review_artifact
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.prospective import build_correction_manifest

CANONICAL_MANIFEST_REVISION = "916de48afecfa174c58d759c3de4a5262dad140c"
MANIFEST_PATH = "data/prospective/gw1-2026-27.json"
INPUTS_PATH = "apps/web/src/data/season-inputs.json"
PICKS = "https://fantasy.premierleague.com/api/entry/{entry}/event/1/picks/"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build-gw1-review")
    parser.add_argument("--entry", type=cliargs.positive_int, default=2_822_737)
    parser.add_argument("--live", type=Path, default=Path("data/live/2026-27/gw01.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("apps/web/src/data/gw1-review.json"),
    )
    parser.add_argument(
        "--correction-output",
        type=Path,
        default=Path("data/prospective/gw1-2026-27-corrected.json"),
    )
    parser.add_argument("--manifest-revision", default=CANONICAL_MANIFEST_REVISION)
    return parser


def _git_bytes(revision: str, path: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision must be a forty-character lowercase Git SHA")
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        check=True,
        capture_output=True,
    ).stdout


def _git_json(revision: str, path: str) -> Mapping[str, Any]:
    payload = parse_json(_git_bytes(revision, path).decode("utf-8"), source=f"{revision}:{path}")
    if not isinstance(payload, Mapping):
        raise ValueError(f"{revision}:{path} was not a JSON object")
    return payload


def write_once(path: Path, payload: Mapping[str, Any]) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output.exists() and args.correction_output.exists():
        print(f"kept {args.correction_output}; kept {args.output}")
        return 0
    canonical = _git_json(args.manifest_revision, MANIFEST_PATH)
    correction = build_correction_manifest(
        canonical,
        manifest_revision=args.manifest_revision,
    )
    recorded_revision = correction["recordedCodeRevision"]
    model_version = correction["canonicalModelVersion"]
    deadline = correction["canonicalDeadline"]
    frozen_at = correction["canonicalFrozenAt"]
    if not all(
        isinstance(value, str) for value in (recorded_revision, model_version, deadline, frozen_at)
    ):
        print("canonical manifest did not name its model, deadline and revisions", file=sys.stderr)
        return 1
    assert isinstance(recorded_revision, str)
    assert isinstance(model_version, str)
    assert isinstance(deadline, str)
    assert isinstance(frozen_at, str)
    inputs = _git_json(recorded_revision, INPUTS_PATH)
    live = read_json_file(args.live)
    if not isinstance(live, Mapping):
        print(f"{args.live} was not a live snapshot object", file=sys.stderr)
        return 1
    picks_url = PICKS.format(entry=args.entry)
    picks_raw = _get_bytes(picks_url)
    if picks_raw is None:
        print("the public GW1 picks could not be read", file=sys.stderr)
        return 1
    picks = parse_json(picks_raw.decode("utf-8"), source=picks_url)
    if not isinstance(picks, Mapping):
        print("the public GW1 picks were not an object", file=sys.stderr)
        return 1
    now = datetime.now(UTC)
    review = build_review_artifact(
        inputs,
        live,
        picks,
        entry_id=args.entry,
        generated_at=now,
        canonical_manifest_revision=args.manifest_revision,
        recorded_code_revision=recorded_revision,
        canonical_model_version=model_version,
        canonical_deadline=deadline,
        canonical_frozen_at=frozen_at,
        live_source_hash=str(live.get("sourceHash")),
        picks_source_hash=f"sha256:{hashlib.sha256(picks_raw).hexdigest()}",
    )
    wrote_correction = write_once(args.correction_output, correction)
    wrote_review = write_once(args.output, review)
    print(
        f"{'wrote' if wrote_correction else 'kept'} {args.correction_output}; "
        f"{'wrote' if wrote_review else 'kept'} {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
