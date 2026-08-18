"""Freeze the pre-deadline model revision, parameters and planning artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from fpl_andres.prospective import build_prospective_manifest

DEFAULT_OUTPUT = Path("data/prospective/gw1-2026-27.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="freeze-prospective")
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--event", type=int, default=1)
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--frozen-at", required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_prospective_manifest(
        Path.cwd(),
        season=args.season,
        event=args.event,
        deadline=datetime.fromisoformat(args.deadline.replace("Z", "+00:00")),
        frozen_at=datetime.fromisoformat(args.frozen_at.replace("Z", "+00:00")),
        code_revision=args.code_revision,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
