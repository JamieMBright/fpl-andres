"""Is the published ceiling actually a ceiling?

`xCeil` is the projection scaled by a player's own ceiling ratio, and that ratio
comes from the ninetieth percentile of his realised scores. If the derivation is
sound, a player should beat his own published ceiling about one appearance in
ten. Measure it rather than assume it: a ratio that is systematically too low
turns every chip note into an advertisement.

    python -m fpl_andres.cli.backtest_ceiling --season 2025-26
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from collections.abc import Sequence

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus, load_season
from fpl_andres.backtesting.reliability import describe_shape
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient

# The ceiling is the ninetieth percentile, so this is what "hit it" should cost.
TARGET_HIT_RATE = 0.10
# Below this a percentile is a rumour rather than a measurement.
MINIMUM_APPEARANCES = 10
# How far the first half is trusted to describe the second.
SPLIT_EVENT = 19


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backtest-ceiling")
    parser.add_argument("--season", default="2025-26")
    return parser


def _split(corpus: SeasonCorpus) -> tuple[float, float, int]:
    """Fit each player's ceiling on the first half, score it on the second.

    Fitting and scoring on the same matches would report the percentile back to
    itself, which is not a test of anything.
    """
    by_element: dict[int, list[ElementRow]] = {}
    for rows in corpus.rows_by_gameweek.values():
        for row in rows:
            by_element.setdefault(row.element_id, []).append(row)

    hits: list[float] = []
    ratios: list[float] = []
    measured = 0
    for rows in by_element.values():
        early = [row for row in rows if row.gameweek <= SPLIT_EVENT and row.minutes > 0]
        late = [row for row in rows if row.gameweek > SPLIT_EVENT and row.minutes > 0]
        if len(early) < MINIMUM_APPEARANCES or len(late) < MINIMUM_APPEARANCES:
            continue

        shape = describe_shape(early)
        if not shape.is_measured or shape.mean <= 0:
            continue
        measured += 1
        ratios.append(shape.ceiling_ratio)

        # Scale the fitted ratio onto what he actually averaged later, so the
        # test is of the *shape* rather than of the level, which is exactly how
        # the projection uses it.
        later_mean = statistics.fmean(row.total_points for row in late)
        ceiling = later_mean * shape.ceiling_ratio
        beat = sum(1 for row in late if row.total_points > ceiling)
        hits.append(beat / len(late))

    if not hits:
        return 0.0, 0.0, 0
    return statistics.fmean(hits), statistics.fmean(ratios), measured


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    credentials = SupabaseCredentials.from_env(os.environ)
    with SupabaseRestClient(credentials) as client:
        corpus = load_season(client, args.season)

    hit_rate, mean_ratio, measured = _split(corpus)
    if measured == 0:
        print(
            f"no player in {args.season} has {MINIMUM_APPEARANCES} appearances "
            f"in both halves, so the ceiling cannot be tested",
            file=sys.stderr,
        )
        return 1

    print(f"season {args.season}, {measured} players with both halves measured")
    print(f"mean ceiling ratio  {mean_ratio:.3f}x their average")
    print(f"beat their ceiling  {hit_rate:.1%} of appearances")
    print(f"target              {TARGET_HIT_RATE:.0%}")
    drift = hit_rate - TARGET_HIT_RATE
    if abs(drift) <= 0.03:
        print("calibrated: the ceiling is a ceiling")
    elif drift > 0:
        print(f"too low by {drift:.1%}: players clear it more often than a p90 should")
    else:
        print(f"too high by {-drift:.1%}: it is being cleared less often than a p90 should")
    return 0


if __name__ == "__main__":
    sys.exit(main())
