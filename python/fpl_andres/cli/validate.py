"""Produce the validation artifact.

Writes a versioned JSON report rather than serving live numbers, because a
validation report is a claim about a specific commit. Committing it means the
page cannot drift from the run that produced it, and any change to the claim
shows up in review as a diff.

Usage:
    python -m fpl_andres.cli.validate --seasons 2022-23,2023-24,2024-25
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres.backtesting.corpus import load_season
from fpl_andres.backtesting.score import score_season
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient
from fpl_andres.simulation.minileague import LeagueSettings, simulate_league
from fpl_andres.simulation.season import LineupRules
from fpl_andres.simulation.squad import SquadRules

DEFAULT_OUTPUT = Path("apps/web/src/data/validation.json")

LEAGUE = LeagueSettings(
    squad_rules=SquadRules(
        budget_tenths=1000, club_limit=3, position_counts={1: 2, 2: 5, 3: 5, 4: 3}
    ),
    lineup_rules=LineupRules(
        starting_size=11,
        minimum_by_position={1: 1, 2: 3, 3: 2, 4: 1},
        maximum_by_position={1: 1, 2: 5, 3: 5, 4: 3},
    ),
    managers=20,
    advised_share=0.25,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate")
    parser.add_argument("--seasons", default="2022-23,2023-24,2024-25")
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    seasons = [part.strip() for part in args.seasons.split(",") if part.strip()]
    seeds = [int(part) for part in args.seeds.split(",") if part.strip()]

    credentials = SupabaseCredentials.from_env(os.environ)
    report: dict[str, object] = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "seasons": [],
        "league": {
            "managers": LEAGUE.managers,
            "advisedShare": LEAGUE.advised_share,
            "seeds": seeds,
        },
    }
    season_reports: list[dict[str, object]] = []

    with SupabaseRestClient(credentials) as client:
        for season in seasons:
            corpus = load_season(client, season)
            scored = score_season(corpus)

            methods = []
            for label in ("model", "recent_mean", "ownership"):
                method = scored.methods[label]
                methods.append(
                    {
                        "label": label,
                        "scored": method.scored,
                        "meanAbsoluteError": _round(method.mean_absolute_error),
                        "rootMeanSquaredError": _round(method.root_mean_squared_error),
                        "bias": _round(method.bias),
                        "spearman": _round(method.mean_spearman),
                        "topNHitRate": _round(method.top_n_hit_rate),
                        "byPosition": {
                            position: _round(value)
                            for position, value in method.position_spearman().items()
                        },
                    }
                )

            advised: list[int] = []
            zombie: list[int] = []
            advised_wins = 0
            for seed in seeds:
                league = simulate_league(corpus, LEAGUE, seed=seed)
                advised.extend(manager.net_points for manager in league.by_policy("advised"))
                zombie.extend(manager.net_points for manager in league.by_policy("zombie"))
                if league.standings()[0].policy == "advised":
                    advised_wins += 1

            season_reports.append(
                {
                    "season": season,
                    "rows": corpus.total_rows,
                    "gameweeks": len(corpus.gameweeks),
                    "elements": len(corpus.position_by_element),
                    "firstScoredGameweek": scored.first_scored_gameweek,
                    "methods": methods,
                    "league": {
                        "advisedMean": round(statistics.mean(advised)),
                        "zombieMean": round(statistics.mean(zombie)),
                        "advisedBest": max(advised),
                        "zombieBest": max(zombie),
                        "advisedWins": advised_wins,
                        "leaguesPlayed": len(seeds),
                    },
                }
            )
            print(f"scored {season}", flush=True)

    report["seasons"] = season_reports

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
