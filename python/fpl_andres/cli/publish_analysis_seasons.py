"""Season aggregates for the analysis scatter, one file per season.

The scatter reads FPL's live bootstrap, which carries exactly one season of
totals and rewrites them the moment a new one starts. That is fine for "who is
worth buying now" and useless for "what did this look like in 2022-23", so the
same aggregates are published from the corpus for every season held.

Prices are the closing price of the window, not today's: comparing what a player
did in 2021-22 against what he costs in 2026-27 is a category error, and the
window slider makes it easy to ask for.

    python -m fpl_andres.cli.publish_analysis_seasons --seasons 2023-24,2024-25
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from fpl_andres.artifacts import ANALYSIS_SEASONS_SCHEMA_VERSION
from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus, load_season
from fpl_andres.backtesting.reliability import describe_shape
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient
from fpl_andres.positions import Position

# Served as a static asset rather than bundled: at a megabyte and a half this is
# a download the analysis page asks for when it needs it, not weight on every
# first paint.
DEFAULT_OUTPUT = Path("apps/web/public/analysis-seasons.json")
# Every season the corpus holds. 2019-20 ran to gameweek 47 after the shutdown,
# which the gameweek window has to tolerate rather than clamp.
DEFAULT_SEASONS = "2021-22,2022-23,2023-24,2024-25,2025-26"
MINUTES_PER_90 = 90.0
# Below this a per-90 rate is a small sample wearing a big number.
MINIMUM_MINUTES = 90
# A player nobody could have picked is a row nobody will plot. Five matches is
# the floor the scatter itself defaults above, so anything under it is weight
# without information.
PUBLISHED_MINUTES_FLOOR = 450

POSITION_CODES = {position.value: position.code for position in Position}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-analysis-seasons")
    parser.add_argument("--seasons", default=DEFAULT_SEASONS)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def _aggregate(rows: Sequence[ElementRow]) -> dict[str, float | int | None]:
    """One player's season, summed over the gameweeks in the window."""
    played = [row for row in rows if row.minutes > 0]
    minutes = sum(row.minutes for row in rows)
    nineties = minutes / MINUTES_PER_90
    shape = describe_shape(rows)

    def total(field: str) -> int:
        return sum(int(getattr(row, field) or 0) for row in rows)

    def optional_total(field: str) -> int | None:
        """Summed only where the archive published it, and None where it did not."""
        seen = [getattr(row, field) for row in rows]
        if all(value is None for value in seen):
            return None
        return sum(int(value or 0) for value in seen)

    expected_goals = sum(row.expected_goals or 0.0 for row in rows)
    expected_assists = sum(row.expected_assists or 0.0 for row in rows)
    defcon = sum(row.defensive_contribution or 0 for row in rows)

    return {
        "minutes": minutes,
        "appearances": len(played),
        "totalPoints": total("total_points"),
        "goals": total("goals"),
        "assists": total("assists"),
        "bonus": total("bonus"),
        "cleanSheets": total("clean_sheets"),
        "saves": total("saves"),
        "goalsConceded": total("goals_conceded"),
        "yellowCards": total("yellow_cards"),
        "redCards": total("red_cards"),
        "expectedGoals": round(expected_goals, 3),
        "expectedAssists": round(expected_assists, 3),
        "expectedGoalInvolvements": round(expected_goals + expected_assists, 3),
        "defensiveContribution": defcon,
        # The three counts behind that sum. Published separately because the sum
        # cannot say whether a player clears the bar by defending his own box or
        # by winning the ball back in the opposition half. Null before 2025/26,
        # where the archive has nothing to give and a zero would read as a
        # defender who made no tackles all year.
        "clearancesBlocksInterceptions": optional_total("clearances_blocks_interceptions"),
        "tackles": optional_total("tackles"),
        "recoveries": optional_total("recoveries"),
        # Withheld rather than zeroed: a rate over no minutes is not zero, it is
        # unmeasured, and a dot on the origin says something false.
        "defensiveContributionPer90": (
            round(defcon / nineties, 3) if minutes >= MINIMUM_MINUTES else None
        ),
        "ceiling": shape.ceiling if shape.is_measured else None,
        "ceilingRatio": round(shape.ceiling_ratio, 3) if shape.is_measured else None,
        # The closing price of the window. Today's price belongs to today.
        "priceTenths": next((row.price_tenths for row in reversed(rows) if row.price_tenths), None),
    }


def _season(corpus: SeasonCorpus) -> dict[str, object]:
    by_element: dict[int, list[ElementRow]] = {}
    for rows in corpus.rows_by_gameweek.values():
        for row in rows:
            by_element.setdefault(row.element_id, []).append(row)

    players: list[dict[str, object]] = []
    for element_id, rows in sorted(by_element.items()):
        position = corpus.position_by_element.get(element_id)
        code = corpus.code_by_element.get(element_id)
        team = corpus.team_by_element.get(element_id)
        if position is None or code is None or team is None:
            continue
        if position not in POSITION_CODES:
            continue
        if sum(row.minutes for row in rows) < PUBLISHED_MINUTES_FLOOR:
            continue
        players.append(
            {
                "code": code,
                "name": corpus.name_by_element.get(element_id, ""),
                "position": POSITION_CODES[position],
                "club": corpus.short_name_by_team.get(team, ""),
                # Gameweek, minutes, points, price. Tuples rather than objects:
                # the same numbers with the key names repeated thirty-eight
                # times a player is four megabytes of the word "minutes".
                "byEvent": [
                    [row.gameweek, row.minutes, row.total_points, row.price_tenths or 0]
                    for row in sorted(rows, key=lambda each: each.gameweek)
                    if row.minutes > 0
                ],
                **_aggregate(rows),
            }
        )

    return {
        "season": corpus.season,
        "events": sorted(corpus.rows_by_gameweek),
        "players": players,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    wanted = [name.strip() for name in str(args.seasons).split(",") if name.strip()]
    if not wanted:
        print("no seasons requested", file=sys.stderr)
        return 1

    credentials = SupabaseCredentials.from_env(os.environ)
    seasons: list[dict[str, object]] = []
    with SupabaseRestClient(credentials) as client:
        for name in wanted:
            corpus = load_season(client, name)
            if not corpus.rows_by_gameweek:
                print(f"no rows for {name}, skipping", file=sys.stderr)
                continue
            seasons.append(_season(corpus))

    if not seasons:
        print("no season produced any rows", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schemaVersion": ANALYSIS_SEASONS_SCHEMA_VERSION,
                "seasons": seasons,
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    total = sum(len(season["players"]) for season in seasons if isinstance(season["players"], list))
    size = output.stat().st_size / 1000
    print(f"wrote {output} — {len(seasons)} seasons, {total} rows, {size:.1f} kB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
