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
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres.backtesting.captain_significance import compare_policies
from fpl_andres.backtesting.corpus import SeasonCorpus, load_season
from fpl_andres.backtesting.opening_gameweek import score_opening_gameweek
from fpl_andres.backtesting.projector import project_gameweek
from fpl_andres.backtesting.score import METHOD_LABELS, score_season
from fpl_andres.cohorts.points_to_rank import boundaries_from_artifact, classify_points
from fpl_andres.holdout import SCORED_SEASONS
from fpl_andres.jsonio import read_json_file
from fpl_andres.model_version import MODEL_VERSION
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient
from fpl_andres.positions import Position
from fpl_andres.simulation.minileague import LeagueResult, LeagueSettings, Policy, simulate_league
from fpl_andres.simulation.reach import (
    captaincy_reach,
    first_acquisition,
    giant_reach,
    owned_captain_policy_scores,
)
from fpl_andres.simulation.replay import (
    SEASON_GAMEWEEKS,
    benchmark_against,
    cohort_totals,
    replay_season,
)
from fpl_andres.simulation.season import LineupRules
from fpl_andres.simulation.squad import SquadRules

DEFAULT_OUTPUT = Path("apps/web/src/data/validation.json")
POINTS_TO_RANK = Path("data/cohort/points-to-rank.json")

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

# Annotated rather than inferred: a bare tuple of strings
# widens to `tuple[str, ...]`, so `league.by_policy(policy)` needed a
# `# type: ignore[arg-type]` -- which also silenced the check that a policy
# named here actually exists. Misspell one now and mypy says so.
POLICIES: tuple[Policy, ...] = ("advised", "form_chaser", "crowd", "hold")

# One manager, playing the season as a ledger rather than as a league table.
#
# It starts at gameweek seven, not one. The projector returns nothing for
# gameweeks two to six: with a single week of this season on the books, last
# season's rows fall outside the recency window and there is no evidence left to
# project from. Opening in August therefore fields an arbitrary eleven for a
# sixth of the season and rebuilds on a wildcard it cannot rank, which scores
# about a third of what the model manages once it can see. Until that gap is
# closed the honest replay is the part the model can actually play.
REPLAY = replace(
    LEAGUE,
    managers=1,
    advised_share=1.0,
    hold_share=0.0,
    form_chaser_share=0.0,
    crowd_share=0.0,
)


def _replay_payload(
    corpus: SeasonCorpus,
    previous: SeasonCorpus,
    names: Mapping[int, str],
) -> dict[str, object]:
    """One season replayed week by week, and where the total would have placed."""
    replay = replay_season(corpus, previous=previous, settings=REPLAY)
    # Pro-rated, because the replay covers the weeks the model can project and
    # a real manager played all thirty-eight. Named as an estimate everywhere it
    # is shown rather than passed off as a season total.
    benchmark = benchmark_against(
        corpus.season, replay.prorated_points, cohort_totals(corpus.season)
    )
    return {
        "season": replay.season,
        "startGameweek": replay.start_gameweek,
        "gameweeksPlayed": len(replay.weeks),
        "seasonGameweeks": SEASON_GAMEWEEKS,
        "totalPoints": replay.total_points,
        "hitPoints": replay.hit_points,
        "netPoints": replay.net_points,
        "proratedPoints": replay.prorated_points,
        "transfers": replay.transfers,
        "chips": replay.chips,
        "finalTeamValueTenths": replay.final_team_value_tenths,
        "transferReturn": (
            None
            if replay.transfer_return is None
            else {
                "horizon": replay.transfer_return.horizon,
                "freeMoves": replay.transfer_return.free_moves,
                "freeGain": _round(replay.transfer_return.free_gain, 1),
                "hitMoves": replay.transfer_return.hit_moves,
                "hitGain": _round(replay.transfer_return.hit_gain, 1),
                "hitNetGain": _round(replay.transfer_return.hit_net_gain, 1),
            }
        ),
        "benchmark": (
            None
            if benchmark is None
            else {
                "managers": benchmark.managers,
                "beaten": benchmark.beaten,
                "percentile": benchmark.percentile,
                "best": benchmark.best,
                "medianPoints": benchmark.median_points,
            }
        ),
        "weeks": [
            {
                "event": week.event,
                "points": week.points,
                "runningTotal": week.running_total,
                "chip": week.chip,
                "captain": week.captain,
                "captainName": names.get(week.captain or 0),
                "captainPoints": week.captain_points,
                "benchPoints": week.bench_points,
                "hitPoints": week.hit_points,
                "transfers": [
                    {
                        "out": out,
                        "outName": names.get(out),
                        "in": incoming,
                        "inName": names.get(incoming),
                    }
                    for out, incoming in week.transfers
                ],
                "teamValueTenths": week.team_value_tenths,
                "bankTenths": week.bank_tenths,
                "starters": list(week.starters),
            }
            for week in replay.weeks
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate")
    parser.add_argument("--seasons", default=",".join(SCORED_SEASONS))
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _overall_rank_payload(
    rank_artifact: object,
    *,
    season: str,
    mean: int,
    gameweeks_played: int,
) -> dict[str, object]:
    prorated = round(mean * 38 / gameweeks_played) if gameweeks_played else 0
    boundaries = boundaries_from_artifact(rank_artifact, season=season)
    estimate = classify_points(boundaries, points=prorated)
    boundary = estimate.boundary if estimate is not None else None
    return {
        "prorated38Gameweeks": prorated,
        "overallRankBin": (
            None
            if estimate is None
            else {
                "rankCutoff": estimate.rank_cutoff,
                "status": estimate.status,
                "inside": (
                    None
                    if boundary is None
                    else {
                        "rank": boundary.inside.rank,
                        "points": boundary.inside.points,
                    }
                ),
                "outside": (
                    None
                    if boundary is None
                    else {
                        "rank": boundary.outside.rank,
                        "points": boundary.outside.points,
                    }
                ),
                "rankGap": None if boundary is None else boundary.rank_gap,
                "pointsGap": None if boundary is None else boundary.points_gap,
                "sampleSize": None if boundary is None else boundary.sample_size,
            }
        ),
        "rankReason": None if estimate is not None else "boundary_unavailable",
    }


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


def _reach_payload(corpus: SeasonCorpus, league: object) -> dict[str, object]:
    """What the advised squad could actually get at.

    Two claims the rest of this report cannot make, because everything else is
    scored against the whole game. A ranking is graded over the pool and a
    captain is picked from the crowd's twenty-five most owned; neither is a set
    anybody owns. These are scored against the fifteen the method was holding
    at the deadline.
    """
    from fpl_andres.simulation.minileague import LeagueResult

    if not isinstance(league, LeagueResult):
        return {}
    giant = giant_reach(league)
    armband = captaincy_reach(corpus, league)
    names = corpus.name_by_element
    return {
        "giant": {
            "gameweeks": giant.gameweeks,
            "owned": giant.owned,
            "started": giant.started,
            "captained": giant.captained,
            "ownedShare": _round(giant.owned_share),
            "startedShare": _round(giant.started_share),
            "captainedShare": _round(giant.captained_share),
            # Who held top spot, and for how long. The suspicion under test is
            # that one player holds it for most of the season, which is what
            # makes "just buy him" a strategy rather than a shrug.
            "leaders": [
                {
                    "elementId": element_id,
                    "name": names.get(element_id, f"#{element_id}"),
                    "gameweeks": weeks,
                }
                for element_id, weeks in sorted(
                    giant.weeks_at_the_top.items(),
                    key=lambda entry: (-entry[1], entry[0]),
                )[:10]
            ],
        },
        "captaincy": {
            "gameweeks": armband.gameweeks,
            "meanChosen": _round(armband.mean_chosen),
            "meanOwnedCeiling": _round(armband.mean_owned_ceiling),
            "meanGameCeiling": _round(armband.mean_game_ceiling),
            "ownedRegret": _round(armband.owned_regret),
            "reachGap": _round(armband.reach_gap),
        },
    }


def _giant_first_payload(
    corpus: SeasonCorpus,
    seeds: Sequence[int],
) -> dict[str, object]:
    """Is starting with the best player in the game worth it?

    The claim is that getting to a premium later is harder than opening with
    him: the transfer costs most of the bank in one move and the money has to
    be found by downgrading somewhere else. That is an opinion until the same
    season is played twice from the same seeds, with the only difference being
    whether he was in the opening fifteen.

    Who "he" is comes from the projection at the start gameweek, which is
    public before that deadline. Naming the season's eventual top scorer would
    be hindsight and would guarantee the answer.
    """
    start = LEAGUE.start_gameweek
    projected = {
        projection.element_id: projection.expected_points
        for projection in project_gameweek(corpus, start)
    }
    if not projected:
        return {}
    giant = max(projected, key=lambda element: (projected[element], -element))

    plain: list[int] = []
    forced: list[int] = []
    waits: list[float] = []
    never = 0
    for seed in seeds:
        without = simulate_league(corpus, LEAGUE, seed=seed)
        with_him = simulate_league(corpus, replace(LEAGUE, open_with=(giant,)), seed=seed)
        plain.extend(manager.net_points for manager in without.by_policy("advised"))
        forced.extend(manager.net_points for manager in with_him.by_policy("advised"))
        got = first_acquisition(without, giant)
        never += got.never
        if got.never < got.managers:
            waits.append(got.mean_wait)

    if not plain or not forced:
        return {}
    plain_mean = statistics.mean(plain)
    forced_mean = statistics.mean(forced)
    return {
        "elementId": giant,
        "name": corpus.name_by_element.get(giant, f"#{giant}"),
        "startGameweek": start,
        "seasons": len(seeds),
        "meanWithout": round(plain_mean),
        "meanOpeningWithHim": round(forced_mean),
        "gain": round(forced_mean - plain_mean),
        # Gameweeks played before he was first owned, for the managers who did
        # not open with him. The cost of arriving late, in weeks.
        "meanGameweeksBeforeOwned": _round(statistics.mean(waits) if waits else 0.0),
        "neverOwned": never,
    }


def _significance_rows(weekly: Mapping[str, Sequence[int]]) -> list[dict[str, object]]:
    """The paired-bootstrap verdicts, in the shape the artifact publishes."""
    if len(weekly) < 2:
        return []
    return [
        {
            "label": verdict.label,
            "weeks": verdict.weeks,
            "meanPoints": _round(verdict.mean),
            "baselineMeanPoints": _round(verdict.baseline_mean),
            "improvement": _round(verdict.improvement),
            "lower": _round(verdict.lower),
            "upper": _round(verdict.upper),
            "better": verdict.better,
            "reasonCodes": list(verdict.reason_codes),
            "familySize": verdict.family_size,
            "confidence": _round(verdict.confidence, 4),
        }
        for verdict in compare_policies(weekly)
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


def _previous_season(season: str) -> str:
    start_text, _, end_text = season.partition("-")
    if len(start_text) != 4 or len(end_text) != 2:
        raise ValueError(f"invalid season label: {season}")
    start = int(start_text)
    return f"{start - 1}-{str(start)[-2:]}"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    seasons = [part.strip() for part in args.seasons.split(",") if part.strip()]
    seeds = [int(part) for part in args.seeds.split(",") if part.strip()]
    rank_artifact = read_json_file(POINTS_TO_RANK)

    credentials = SupabaseCredentials.from_env(os.environ)
    report: dict[str, object] = {
        "generatedAt": datetime.now(UTC).isoformat(),
        # Two runs are only comparable if something says whether the model
        # between them moved. `scripts/model-version-gate.mjs` keeps it honest.
        "modelVersion": MODEL_VERSION,
        "captainEvidenceScope": "model_owned_xi",
        "seasons": [],
        "league": {
            "managers": LEAGUE.managers,
            "advisedShare": LEAGUE.advised_share,
            "seeds": seeds,
        },
    }
    season_reports: list[dict[str, object]] = []
    # Every scored gameweek from every season, in order, per policy. A single
    # season is ~35 paired weeks, which is barely more than the floor the
    # bootstrap will accept. Pooled, the same comparison has four times the
    # weeks and is the only one worth quoting.
    pooled_weekly: dict[str, list[int]] = {}

    with SupabaseRestClient(credentials) as client:
        corpora: dict[str, SeasonCorpus] = {}

        def corpus_for(label: str) -> SeasonCorpus:
            if label not in corpora:
                corpora[label] = load_season(client, label)
            return corpora[label]

        for season in seasons:
            corpus = corpus_for(season)
            previous_corpus = corpus_for(_previous_season(season))
            opening = score_opening_gameweek(
                previous_corpus,
                corpus,
            )
            scored = score_season(corpus)

            methods = []
            for label in METHOD_LABELS:
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
                        # What players projected into each band actually scored.
                        # The pooled error is dominated by players projected near
                        # zero; a captain pick lives in the top band alone.
                        "calibration": [
                            {
                                "label": band.label,
                                "lower": band.lower,
                                "upper": band.upper,
                                "count": band.count,
                                "meanPredicted": _round(band.mean_predicted),
                                "meanActual": _round(band.mean_actual),
                            }
                            for band in method.calibration()
                        ],
                    }
                )

            totals: dict[str, list[int]] = {policy: [] for policy in POLICIES}
            chips: dict[str, dict[str, list[int]]] = {}
            squads: dict[str, list[dict[str, object]]] = {}
            value: dict[str, int] = {}
            wins: dict[str, int] = {policy: 0 for policy in POLICIES}
            gameweeks_played = 0
            reach: dict[str, object] = {}
            leagues: list[LeagueResult] = []

            for seed in seeds:
                league = simulate_league(corpus, LEAGUE, seed=seed)
                leagues.append(league)
                for policy in POLICIES:
                    cohort = league.by_policy(policy)
                    totals[policy].extend(manager.net_points for manager in cohort)
                    if cohort and seed == seeds[0]:
                        first = cohort[0]
                        gameweeks_played = len(first.weekly_points)
                        chips[policy] = {
                            name: sorted(events) for name, events in first.chips_played.items()
                        }
                        value[policy] = first.final_team_value_tenths
                        squads[policy] = _squad_rows(league, policy, corpus)
                if seed == seeds[0]:
                    reach = _reach_payload(corpus, league)
                winner = league.standings()[0].policy
                if winner in wins:
                    wins[winner] += 1

            owned_scores = owned_captain_policy_scores(
                corpus,
                leagues,
                scored.captain_candidates,
            )
            owned_captain_policies = [
                {
                    "label": label,
                    "gameweeks": pick.gameweeks,
                    "meanChosenPoints": _round(pick.mean_points),
                    "meanReachableCeiling": _round(pick.mean_best_points),
                    "ownedSquadRegret": _round(pick.regret),
                    "shareOfReachableCeiling": _round(pick.share_of_ceiling),
                    "perfectWeeks": pick.perfect_weeks,
                    "blankRate": _round(pick.blank_rate),
                }
                for label, pick in owned_scores.items()
            ]
            weekly = {label: pick.weekly for label, pick in owned_scores.items() if pick.weekly}
            for label, series in weekly.items():
                pooled_weekly.setdefault(label, []).extend(series)
            captain_significance = _significance_rows(weekly)

            season_reports.append(
                {
                    "season": season,
                    "rows": corpus.total_rows,
                    "gameweeks": len(corpus.gameweeks),
                    "gameweeksPlayed": gameweeks_played,
                    "elements": len(corpus.position_by_element),
                    "firstScoredGameweek": scored.first_scored_gameweek,
                    "openingGameweek": {
                        "previousSeason": opening.previous_season,
                        "event": 1,
                        "scored": opening.scored,
                        "meanAbsoluteError": _round(opening.mean_absolute_error),
                        "rootMeanSquaredError": _round(opening.root_mean_squared_error),
                        "bias": _round(opening.bias),
                        "spearman": _round(opening.spearman),
                    },
                    "expectedGoalsCoverage": _expected_goals_coverage(corpus),
                    "missingGameweeks": list(corpus.missing_gameweeks),
                    "replay": _replay_payload(corpus, previous_corpus, corpus.name_by_element),
                    # Names the corpus state every metric below was measured
                    # over, so a moved number can be told from a moved model.
                    "corpusFingerprint": corpus.fingerprint,
                    "methods": methods,
                    "ownedCaptainPolicies": owned_captain_policies,
                    "captainSignificance": captain_significance,
                    "reach": reach,
                    "giantFirst": _giant_first_payload(corpus, seeds),
                    "league": {
                        "policies": {
                            policy: (
                                lambda mean: {
                                    "mean": mean,
                                    "best": max(totals[policy]) if totals[policy] else 0,
                                    "wins": wins[policy],
                                    "chips": chips.get(policy, {}),
                                    "teamValueTenths": value.get(policy, 0),
                                    "squad": squads.get(policy, []),
                                    **_overall_rank_payload(
                                        rank_artifact,
                                        season=season,
                                        mean=mean,
                                        gameweeks_played=gameweeks_played,
                                    ),
                                }
                            )(round(statistics.mean(totals[policy])) if totals[policy] else 0)
                            for policy in POLICIES
                        },
                        "leaguesPlayed": len(seeds),
                    },
                }
            )
            print(f"scored {season}", flush=True)

    report["seasons"] = season_reports
    # The headline comparison: every scored week of every season, paired.
    report["captainSignificance"] = _significance_rows(pooled_weekly)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
