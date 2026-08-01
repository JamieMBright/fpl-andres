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

from fpl_andres.backtesting.corpus import SeasonCorpus, load_season
from fpl_andres.backtesting.score import score_season
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient
from fpl_andres.positions import Position
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
    hold_share=0.25,
    form_chaser_share=0.25,
    crowd_share=0.25,
)

POLICIES = ("advised", "form_chaser", "crowd", "hold")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate")
    parser.add_argument("--seasons", default="2022-23,2023-24,2024-25,2025-26")
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _squad_rows(league: object, policy: str, corpus: object) -> list[dict[str, object]]:
    """The fifteen a policy finished with, named, so the run can be inspected.

    A validation page that only reports totals asks the reader to trust four
    numbers. Showing the teams is what makes it checkable, and it is how the two
    worst bugs in this simulation would have been spotted immediately.
    """
    from fpl_andres.simulation.minileague import LeagueResult

    if not isinstance(league, LeagueResult):
        return []
    holder = next(
        (entry for entry in league.squad_snapshots if entry[0] == policy),
        None,
    )
    if holder is None:
        return []
    names = getattr(corpus, "name_by_element", {})
    positions = getattr(corpus, "position_by_element", {})
    codes = {position.value: position.code for position in Position}
    return [
        {
            "elementId": element_id,
            "name": names.get(element_id, f"#{element_id}"),
            "position": codes.get(positions.get(element_id, 0), "?"),
            "priceTenths": price,
        }
        for element_id, price in holder[1]
    ]


def _expected_goals_coverage(corpus: SeasonCorpus) -> float:
    """FPL published no expected values before 2022-23.

    Coverage is 0.0 for those seasons and 1.0 after, so a reader comparing
    across the boundary is comparing two different models. Reported rather
    than assumed, because the rate model silently falls back to actuals.
    """
    rows = [row for block in corpus.rows_by_gameweek.values() for row in block]
    if not rows:
        return 0.0
    with_expected = sum(1 for row in rows if row.expected_goals is not None)
    return round(with_expected / len(rows), 4)


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

            totals: dict[str, list[int]] = {policy: [] for policy in POLICIES}
            chips: dict[str, dict[str, int]] = {}
            squads: dict[str, list[dict[str, object]]] = {}
            value: dict[str, int] = {}
            wins: dict[str, int] = {policy: 0 for policy in POLICIES}
            gameweeks_played = 0

            for seed in seeds:
                league = simulate_league(corpus, LEAGUE, seed=seed)
                for policy in POLICIES:
                    cohort = league.by_policy(policy)  # type: ignore[arg-type]
                    totals[policy].extend(manager.net_points for manager in cohort)
                    if cohort and seed == seeds[0]:
                        first = cohort[0]
                        gameweeks_played = len(first.weekly_points)
                        chips[policy] = dict(first.chips_played)
                        value[policy] = first.final_team_value_tenths
                        squads[policy] = _squad_rows(league, policy, corpus)
                winner = league.standings()[0].policy
                if winner in wins:
                    wins[winner] += 1

            season_reports.append(
                {
                    "season": season,
                    "rows": corpus.total_rows,
                    "gameweeks": len(corpus.gameweeks),
                    "gameweeksPlayed": gameweeks_played,
                    "elements": len(corpus.position_by_element),
                    "firstScoredGameweek": scored.first_scored_gameweek,
                    "expectedGoalsCoverage": _expected_goals_coverage(corpus),
                    "missingGameweeks": list(corpus.missing_gameweeks),
                    # Names the corpus state every metric below was measured
                    # over, so a moved number can be told from a moved model.
                    "corpusFingerprint": corpus.fingerprint,
                    "methods": methods,
                    "league": {
                        "policies": {
                            policy: {
                                "mean": round(statistics.mean(totals[policy]))
                                if totals[policy]
                                else 0,
                                "best": max(totals[policy]) if totals[policy] else 0,
                                "wins": wins[policy],
                                "chips": chips.get(policy, {}),
                                "teamValueTenths": value.get(policy, 0),
                                "squad": squads.get(policy, []),
                            }
                            for policy in POLICIES
                        },
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
