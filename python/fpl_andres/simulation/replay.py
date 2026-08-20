"""Replay a completed season week by week, and say where it would have finished.

A season total is a claim nobody can check. This replays the model's own season
from the opening gameweek to the last, keeping the week as it was played --
what came in, what went out, what it cost, who took the armband, which chip was
burned and what the bench was left holding -- so the total can be stepped
through rather than believed.

Two things make the number comparable to a real manager's, and both were absent
from the mini-league the validation page reports:

* It starts at gameweek one. The mini-league opens a seventh of the way in,
  because before that there is not enough of the season to project from. That
  is the right call for comparing policies against each other, and the wrong
  one for comparing a total against somebody who played all thirty-eight. The
  opening weeks are projected off last season instead, exactly as the live
  planner projects an August gameweek.
* It plays the chips the season actually granted. From 2025-26 that is two of
  each rather than one, and a replay on the old allowance leaves three chips
  unused against every real manager it is measured against.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.simulation.minileague import simulate_league
from fpl_andres.simulation.minileague_state import GameweekLedger, LeagueSettings

__all__ = [
    "COHORT_MANAGERS",
    "ManagerBenchmark",
    "SeasonReplay",
    "benchmark_against",
    "cohort_totals",
    "replay_season",
]

COHORT_MANAGERS = Path("data/cohort/managers.jsonl")


@dataclass(frozen=True)
class ManagerBenchmark:
    """Where a season total would have finished among real managers.

    The cohort is the ranked managers already harvested for FPL500, so it is
    not the whole game: it is skewed toward people who finish well, which makes
    it a harder comparison than an overall rank and a more honest one than
    picking a friendly percentile.
    """

    season: str
    #: Real managers in the cohort with a recorded total for this season.
    managers: int
    points: int
    beaten: int
    percentile: float
    best: int
    median_points: int


@dataclass(frozen=True)
class SeasonReplay:
    """One model season, week by week."""

    season: str
    start_gameweek: int
    weeks: tuple[GameweekLedger, ...]
    #: Raw points, before transfer hits. `net_points` is what a league table
    #: would show.
    total_points: int
    hit_points: int
    transfers: int
    chips: dict[str, list[int]]
    final_team_value_tenths: int
    benchmark: ManagerBenchmark | None

    @property
    def net_points(self) -> int:
        return self.total_points - self.hit_points


def replay_season(
    corpus: SeasonCorpus,
    *,
    previous: SeasonCorpus,
    settings: LeagueSettings,
    seed: int = 1,
) -> SeasonReplay:
    """Play one manager through the whole of `corpus`, from gameweek one.

    A single manager rather than a league: the projection is computed once per
    gameweek whatever the roster size, so the cost of this over the existing
    twenty-manager run is one extra pass, and nothing here is asking how
    policies place against each other.
    """
    league = simulate_league(corpus, settings, seed=seed, previous=previous)
    advised = league.by_policy("advised")
    if not advised:
        raise ValueError("the replay settings produced no advised manager")
    manager = advised[0]
    return SeasonReplay(
        season=corpus.season,
        start_gameweek=settings.start_gameweek,
        weeks=tuple(manager.ledger),
        total_points=manager.total_points,
        hit_points=manager.hit_points,
        transfers=manager.transfers_made,
        chips={name: sorted(events) for name, events in manager.chips_played.items()},
        final_team_value_tenths=manager.final_team_value_tenths,
        benchmark=None,
    )


def cohort_totals(season: str, *, path: Path = COHORT_MANAGERS) -> list[int]:
    """Every real season total the cohort recorded for `season`.

    Returns empty rather than raising when the cohort has not been harvested:
    a missing benchmark downgrades the claim to "here is the season" instead of
    inventing a comparison.
    """
    if not path.exists():
        return []
    # The cohort names seasons the way the game does, with a slash.
    wanted = season.replace("-", "/")
    totals: list[int] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            for entry in payload.get("seasons", ()):
                if entry.get("season") != wanted:
                    continue
                points = entry.get("points")
                if isinstance(points, int):
                    totals.append(points)
    return totals


def benchmark_against(season: str, points: int, totals: list[int]) -> ManagerBenchmark | None:
    """Where `points` sits among real totals, or None when there are none."""
    if not totals:
        return None
    beaten = sum(1 for total in totals if points > total)
    return ManagerBenchmark(
        season=season,
        managers=len(totals),
        points=points,
        beaten=beaten,
        percentile=round(100.0 * beaten / len(totals), 1),
        best=max(totals),
        median_points=int(median(totals)),
    )
