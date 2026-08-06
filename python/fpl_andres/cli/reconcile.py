"""Reconcile realised points against the scoring table this project prices with.

Reports, per season: how many player-gameweeks rebuild exactly, the signed
residual, the absolute residual, which positions the disagreement sits in, and
the worst individual rows by name.

The signed and absolute residuals are both printed on purpose. A season summing
to within a point of FPL's own total sounds conclusive and is not: offsetting
errors cancel. The absolute residual is the one that cannot be flattered.

Needs the history corpus, so it runs where the corpus is -- see
`.github/workflows/validate-model.yml`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_andres.backtesting.corpus import load_season
from fpl_andres.backtesting.reconcile import Reconciliation, reconcile_season
from fpl_andres.model_version import MODEL_VERSION
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient
from fpl_andres.positions import Position

__all__ = ["build_parser", "main", "render"]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = REPO_ROOT / "apps" / "web" / "src" / "data" / "reconciliation.json"
DEFAULT_SEASONS = "2022-23,2023-24,2024-25,2025-26"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", default=DEFAULT_SEASONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--worst",
        type=int,
        default=25,
        help="How many disagreeing rows to name per season.",
    )
    return parser


def _position_code(position: int) -> str:
    for entry in Position:
        if entry.value == position:
            return entry.code
    # A historical season legitimately holds an element type this package does
    # not know: Assistant Manager was type 5 in 2024/25 and is gone again.
    return f"type-{position}"


def render(outcome: Reconciliation) -> dict[str, Any]:
    return {
        "season": outcome.season,
        "rows": outcome.rows,
        "exact": outcome.exact,
        "exactShare": round(outcome.exact_share, 5) if outcome.exact_share else None,
        "awarded": outcome.awarded,
        "rebuilt": outcome.rebuilt,
        "residual": outcome.residual,
        "absoluteResidual": outcome.absolute,
        "byPosition": {
            _position_code(position): gap for position, gap in sorted(outcome.by_position.items())
        },
        "worst": [
            {
                "gameweek": row.gameweek,
                "name": row.name,
                "position": _position_code(row.position),
                "awarded": row.awarded,
                "rebuilt": row.rebuilt,
                "residual": row.residual,
                "routes": {route: value for route, value in row.routes.items() if value},
            }
            for row in outcome.worst
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    seasons = [part.strip() for part in args.seasons.split(",") if part.strip()]

    credentials = SupabaseCredentials.from_env(os.environ)
    report: dict[str, Any] = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "modelVersion": MODEL_VERSION,
        "seasons": [],
    }

    with SupabaseRestClient(credentials) as client:
        for season in seasons:
            corpus = load_season(client, season)
            outcome = reconcile_season(
                corpus.rows_by_gameweek,
                corpus.position_by_element,
                corpus.name_by_element,
                season=season,
                keep_worst=args.worst,
            )
            report["seasons"].append(render(outcome))
            print(
                f"{season}: {outcome.exact}/{outcome.rows} exact, "
                f"residual {outcome.residual:+d}, absolute {outcome.absolute}",
                file=sys.stderr,
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"reconciliation written to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
