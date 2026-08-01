"""Score our projection against a rival's, on a week that has already happened.

The rival column is not fetched. FPL Review's robots.txt carries
`User-agent: ClaudeBot / Disallow: /` and `Content-Signal: ai-train=no`, which
is an explicit refusal, and fplkiwi.com does not resolve. Export your own
account's projections and point this at the file.

The CSV needs a column of FPL player codes and a column of projected points:

    code,points
    154561,4.2

Usage:
    python -m fpl_andres.cli.benchmark --season 2025-26 --gameweek 20 \
        --rival data/rival/review-gw20.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from fpl_andres import cliargs
from fpl_andres.backtesting.corpus import load_season
from fpl_andres.backtesting.projector import project_horizon
from fpl_andres.models.benchmark import BenchmarkUnavailable, compare_projections
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="benchmark")
    parser.add_argument("--season", type=cliargs.season, required=True)
    parser.add_argument("--gameweek", type=cliargs.event_id, required=True)
    parser.add_argument("--rival", required=True, help="CSV of code,points")
    parser.add_argument("--code-column", default="code")
    parser.add_argument("--points-column", default="points")
    parser.add_argument("--top-n", type=cliargs.positive_int, default=30)
    return parser


def _rival(path: Path, code_column: str, points_column: str) -> dict[int, float]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise BenchmarkUnavailable(f"{path} has no header row")
        missing = {code_column, points_column} - set(reader.fieldnames)
        if missing:
            raise BenchmarkUnavailable(
                f"{path} is missing {sorted(missing)}; saw {reader.fieldnames}"
            )
        return {
            int(row[code_column]): float(row[points_column])
            for row in reader
            if row[code_column] and row[points_column]
        }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        rival = _rival(Path(args.rival), args.code_column, args.points_column)
    except (BenchmarkUnavailable, ValueError) as error:
        print(f"rival file unusable: {error}", file=sys.stderr)
        return 2

    credentials = SupabaseCredentials.from_env(os.environ)
    with SupabaseRestClient(credentials) as client:
        corpus = load_season(client, args.season)

    code_of = corpus.code_by_element
    ours = {
        code_of[projection.element_id]: projection.points_over(1)
        for projection in project_horizon(corpus, args.gameweek, horizons=(1,))
        if projection.element_id in code_of
    }
    actual: dict[int, float] = {}
    for row in corpus.rows_by_gameweek.get(args.gameweek, []):
        code = code_of.get(row.element_id)
        if code is not None:
            actual[code] = actual.get(code, 0.0) + row.total_points

    try:
        comparison = compare_projections(ours=ours, theirs=rival, actual=actual, top_n=args.top_n)
    except BenchmarkUnavailable as error:
        print(f"cannot compare: {error}", file=sys.stderr)
        return 1

    print(f"{args.season} GW{args.gameweek}, {comparison.players} shared players\n")
    print(f"  {'model':8s} {'MAE':>7s} {'bias':>7s} {'spearman':>9s} {'top-N':>7s}")
    for score in (comparison.ours, comparison.theirs):
        print(
            f"  {score.label:8s} {score.mean_absolute_error:7.3f} "
            f"{score.bias:+7.3f} {score.spearman:9.3f} {score.top_n_hit_rate:7.1%}"
        )

    verdict = "we are closer" if comparison.we_win else "they are closer"
    print(f"\n  {verdict} by {abs(comparison.error_gap):.3f} points per player")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
